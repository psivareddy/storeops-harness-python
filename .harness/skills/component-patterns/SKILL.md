# Skill: component-patterns

**Purpose.** The mechanics of writing a StoreOps vertical slice: which file gets which code, the
exact signatures and idioms this codebase uses, and the checklist for adding an endpoint to an
existing module.

**Read by:** Generator only.

> **Boundary with [architecture-principles](../architecture-principles/SKILL.md).** That file states
> *the rule and why it exists* — it is read by the Planner and Evaluator too. This file is *how you
> type the code that obeys it*. To learn whether routes may import a repository, read that file. To
> learn what a route body should look like, read this one.

---

## 1. The four files of a module

Every module under `app/<module>/` has exactly these, and nothing else:

| File | Contains | Imports it may make |
|---|---|---|
| `models.py` | Pydantic models, `StrEnum`s, pure predicate functions | stdlib, pydantic |
| `repository.py` | in-memory dict store, seed data, filters | `models`, stdlib |
| `service.py` | business rules, raises `AppError`, publishes events | `models`, own `repository`, `app.shared.*`, **sibling services** |
| `routes.py` | `APIRouter`, HTTP binding, delegation | `models`, own `service` |

`routes.py` must never import `repository` — not even its own. That is layer skipping (HG-5).

---

## 2. `models.py`

Frozen models, `StrEnum` for every closed set, validation in `Field`.

```python
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    BLOCKED = "BLOCKED"


class Task(BaseModel):
    model_config = ConfigDict(frozen=True)          # entities are immutable

    id: str
    title: str
    store_id: str
    status: TaskStatus = TaskStatus.TODO
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

### Conventions that are not optional here

- **`model_config = ConfigDict(frozen=True)` on every entity.** Mutation is
  `entity.model_copy(update={...})`, returning a new instance. This is why the repository has
  `replace()` rather than mutating in place.
- **`StrEnum`, not `str` plus constants.** FastAPI then rejects an unknown value with 422 *before*
  the service is reached, which is what makes "an invalid target status returns 422 and publishes
  nothing" true with no service-layer code at all.
- **Separate input schemas.** `Task` is the entity; `TaskCreate` and `TaskStatusUpdate` are request
  bodies. Never accept the entity as a request body — that would let a caller set `id` and
  `created_at`.
- **Business predicates live here, not in the service.** `ALLOWED_TRANSITIONS` and
  `can_transition()` sit in `app/activities/models.py` so the service *and* any future event
  handler apply the same rule.
- **`datetime.now(UTC)`**, never `utcnow()`. Ruff `UP017` requires `UTC` over `timezone.utc`.

---

## 3. `repository.py`

```python
class TaskRepository:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self.reset()

    def reset(self) -> None:                        # re-seed; the test fixture calls this
        self._tasks = {task.id: task for task in _seed_tasks()}

    def get(self, task_id: str) -> Task | None:     # returns None; does NOT raise
        return self._tasks.get(task_id)

    def replace(self, task: Task) -> Task:          # caller has confirmed existence
        self._tasks[task.id] = task
        return task

    def next_id(self) -> str:
        return f"task-{len(self._tasks) + 1}"


task_repository = TaskRepository()                  # module-level singleton
```

### `get()` returns `None` and never raises — this carries weight

The repository does not know that absence is an error; the **service** decides. Keeping that
decision in the service is precisely what lets a bulk endpoint treat one missing id as a *per-item*
partial failure rather than failing the whole request. A repository that raised
`TaskNotFoundError` would force the bulk service into a `try/except` per item — which `ruff TRY301`
flags — and would blur "not found" against "not allowed".

**Never** put in a repository: a domain error, an event publish, a call to another module, or an
HTTP concern.

---

## 4. `service.py`

Constructor injection with singleton defaults. This shape is required, not stylistic.

```python
class ActivitiesService:
    def __init__(
        self, repository: TaskRepository | None = None, bus: EventBus | None = None
    ) -> None:
        self._repository = repository if repository is not None else task_repository
        self._bus = bus if bus is not None else event_bus


activities_service = ActivitiesService()
```

**Why both halves.** The `None` default lets `routes.py` use the process singleton without
constructing a repository — constructing one in a route would be a layer violation. The override
lets a test build an isolated `ActivitiesService(repository=TaskRepository(), bus=EventBus())` and
assert *"zero events were published"*, which is impossible against a shared bus other tests have
written to. See the `activities` fixture in `tests/conftest.py`.

### The write-method shape

```python
def update_status(self, task_id: str, requested: TaskStatus) -> Task:
    task = self.get_task(task_id)                    # 1. resolve, raising AppError if absent
    if not can_transition(task.status, requested):   # 2. validate the business rule
        raise InvalidStatusTransitionError(task_id, task.status.value, requested.value)

    previous = task.status
    updated = task.model_copy(update={"status": requested, "updated_at": datetime.now(UTC)})
    self._repository.replace(updated)                # 3. persist
    self._bus.publish(                               # 4. publish AFTER the write succeeds
        EventName.ACTIVITY_STATUS_CHANGED,
        {"taskId": updated.id, "previousStatus": previous.value, "newStatus": requested.value},
    )
    return updated
```

**The order is the contract: validate → persist → publish.** Publishing before the write lets a
subscriber observe an event for a change that did not happen. Publishing on a validation failure
writes an audit entry for a change that was rejected. Every early `raise` must occur before any
`publish`.

### Read methods siblings may call

A module's public read methods *are* its cross-module API (Rule 1). Name them for the caller's
intent — `tasks_for_store(store_id)`, `known_store_ids()` — not `list_all(**filters)`. A narrow
named method is a boundary you can maintain; a generic filter method becomes a de-facto repository
exposed across the boundary.

---

## 5. `routes.py`

```python
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.activities.models import Task, TaskCreate, TaskStatus, TaskStatusUpdate
from app.activities.service import activities_service   # the SERVICE singleton, never the repo

router = APIRouter(prefix="/api/tasks", tags=["activities"])


@router.patch("/{task_id}/status", response_model=Task)
def update_task_status(task_id: str, payload: TaskStatusUpdate) -> Task:
    """Change an activity's status, publishing one ACTIVITY_STATUS_CHANGED event."""
    return activities_service.update_status(task_id, payload.status)


@router.get("", response_model=list[Task])
def list_tasks(
    store_id: Annotated[str | None, Query(description="Filter by store")] = None,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
) -> list[Task]:
    return activities_service.list_tasks(store_id=store_id, status=task_status)
```

### Conventions

- **`Annotated[T, Query(...)]`, never `Query(...)` as a default value.** The bare form trips
  `ruff B008` (function call in a default argument).
- **Never catch `AppError` in a route.** The handler registered by `register_error_handlers()` maps
  it to the envelope. A `try/except` around a service call in a route is a defect.
- **`tags=["<module>"]`** — `tests/test_main.py::test_all_five_modules_contribute_routes` asserts
  all five module tags are present.
- **`status_code=status.HTTP_201_CREATED`** on creates; default 200 otherwise.
- **A route body is 1–2 lines.** A branch on domain state in a route is a business rule in the
  wrong layer.

### Rejected — layer skipping

```python
from app.activities.repository import task_repository        # HG-5 failure: routes -> repository

@router.patch("/{task_id}/status")
def update_task_status(task_id: str, payload: TaskStatusUpdate) -> Task:
    task = task_repository.get(task_id)                      # skips the service
    if task is None:
        raise HTTPException(404, "not found")                 # and the error contract (HG-2)
    if task.status == TaskStatus.DONE:                        # business rule in the route
        raise HTTPException(409, "already done")
    return task_repository.replace(task.model_copy(update={"status": payload.status}))
```

Four violations in seven lines: a route imports a repository, the service is bypassed, the
transition rule is now unreachable from any other caller, and **no event is published** — so the
audit sink and the alerts subscriber never learn the status changed.

---

## 6. Adding an endpoint to an existing module — the checklist

This is the Phase 5 shape: a new endpoint on `activities`, no new module.

1. **`models.py`** — add the request/response schemas (e.g. `BulkStatusUpdate`,
   `BulkStatusResult`). Put any new predicate beside the existing `can_transition`.
2. **`repository.py`** — usually **no change**. A bulk operation loops over the existing `get()`
   and `replace()`; it does not need a `replace_many()`.
3. **`service.py`** — add one method. Reuse the existing single-item rule rather than
   reimplementing it: a bulk update calls the same `can_transition` check per item.
4. **`routes.py`** — add one decorated function with a 1–2 line body.
5. **`app/main.py`** — **no change** unless a new event type needs wiring. The router is already
   included.
6. **`tests/<module>/test_<feature>.py`** — new file, named per the contract's AC mapping.
7. **`tests/test_main.py`** — **add the endpoint to `EXPECTED_ENDPOINTS`.** This is the step that
   gets missed. That set is asserted for exact equality, so a new endpoint fails the suite until
   the set is updated, and the failure message reads as though something unrelated broke.

### Partial-failure endpoints

When one request performs N independent operations, the service returns a per-item result instead
of raising:

```python
def bulk_update_status(self, task_ids: Sequence[str], requested: TaskStatus) -> BulkStatusResult:
    succeeded: list[Task] = []
    failed: list[BulkItemFailure] = []
    for task_id in task_ids:
        try:
            succeeded.append(self.update_status(task_id, requested))
        except AppError as exc:               # permitted ONLY in a bulk aggregator in the service
            failed.append(BulkItemFailure(task_id=task_id, code=exc.code, message=exc.message))
    return BulkStatusResult(succeeded=succeeded, failed=failed)
```

Two points. First, catching `AppError` is permitted **in a bulk aggregator in the service layer and
nowhere else** — its entire purpose is converting a per-item failure into a per-item result. It
remains forbidden in routes. Second, it delegates to `update_status`, so each successful item
publishes exactly one event and each failed item publishes none, with no extra code: the counting
invariant falls out of reuse rather than being re-established (and re-broken).

The route then picks the status code from the result shape, which is presentation, not a business
rule:

```python
@router.patch("/bulk-status", response_model=BulkStatusResult)
def bulk_update_status(payload: BulkStatusUpdate, response: Response) -> BulkStatusResult:
    result = activities_service.bulk_update_status(payload.task_ids, payload.status)
    response.status_code = 207 if (result.failed and result.succeeded) else 200
    return result
```

---

## 7. Adding a whole new module — rare

Only when a sprint contract says so. Create all four files, then add `app.<module>` to **every**
`forbidden` contract in `.importlinter` (its own, plus an entry in the other five), add a container
to `module-layers`, add the module to `app.shared`'s forbidden list, include the router in
`app/main.py`, and add `tests/<module>/__init__.py`. Omitting the `.importlinter` entries leaves
the new module **unguarded while the contract report still reads "0 broken"**.

---

## 8. Generator checklist for this skill

- [ ] No `routes.py` imports a `repository`
- [ ] Every route body delegates in 1–2 lines with no branching on domain state
- [ ] Services take `repository`/`bus` with `None` defaults resolving to the singletons
- [ ] Order in every write path: validate → persist → publish
- [ ] Entities frozen; mutation via `model_copy(update=...)`
- [ ] Closed sets are `StrEnum`; request bodies are separate types from entities
- [ ] Repository `get()` returns `None`, raises nothing, publishes nothing
- [ ] New endpoint added to `EXPECTED_ENDPOINTS` in `tests/test_main.py`
- [ ] `Annotated[...]` used for every query parameter
- [ ] Bulk operations reuse the single-item service method
