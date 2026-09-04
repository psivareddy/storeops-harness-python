# Skill: architecture-principles

**Purpose.** The five non-negotiable StoreOps architecture rules, each stated against real code in
this repository, with the correct pattern, the rejected pattern, the failure mode it prevents, what
breaks without it, and the exact command that detects a violation.

**Read by:** Planner, Generator, Evaluator (all three acting agents).

Every rule below cites real symbols from `app/`. **If a sentence in this file would read identically
for a generic REST API, it is a defect in this file** — delete it or make it specific.

---

## The four failure modes

These were observed in this client's prior AI-assisted development experiment. Every rule and every
hard gate traces to one of them.

| ID | Failure mode |
|---|---|
| **FM-1** | Direct imports from another module's repository, bypassing the service boundary |
| **FM-2** | Raw error throws bypassing the typed `AppError` hierarchy |
| **FM-3** | Tests asserting HTTP status codes without verifying business rule compliance |
| **FM-4** | Missing event bus integration — state changes written directly to sibling repositories |

---

## Rule 1 — Module boundary

> **No module may import another module's `repository`. Cross-module reads go through the target
> module's `service` layer only.**

Prevents **FM-1**. Enforced by the `lint-imports` contracts
`activities-no-cross-module-repository` and its four sibling equivalents.

### Correct — `app/programmes/service.py`

Enrolling a staff member requires validating that the user exists. It calls the **staff service**:

```python
from app.staff.service import StaffService, staff_service

class ProgrammesService:
    def add_member(self, project_id: str, payload: ProjectMemberCreate) -> Project:
        project = self.get_project(project_id)
        # Cross-module read through the staff SERVICE layer. Raises USER_NOT_FOUND if unknown.
        user = self._staff.get_user(payload.user_id)
```

### Rejected

```python
from app.staff.repository import user_repository        # FM-1 — hard gate HG-1 failure

class ProgrammesService:
    def add_member(self, project_id: str, payload: ProjectMemberCreate) -> Project:
        user = user_repository.get(payload.user_id)      # bypasses StaffService entirely
        if user is None:
            raise ValidationError("no such user")        # and invents a different error code
```

### What breaks without it

`staff` owns the definition of "a valid user" — currently existence, and plausibly `is_active` next
(the field already exists on `User`). The rejected version freezes today's definition into
`programmes`. When staff adds a deactivation rule, enrolment silently keeps accepting deactivated
staff, and the bug surfaces as a rota problem weeks later. It also swaps `USER_NOT_FOUND` (404) for
`VALIDATION_ERROR` (422), so a client branching on the error code breaks.

### The permitted service-to-service reads in this codebase

| Caller | Callee | Purpose |
|---|---|---|
| `app/programmes/service.py` | `StaffService.get_user` | validate an enrolment |
| `app/reports/service.py` | `ActivitiesService.tasks_for_store`, `known_store_ids` | aggregate tasks |
| `app/reports/service.py` | `ProgrammesService.projects_for_store` | count active programmes |
| `app/reports/service.py` | `StaffService.users_for_store` | count staff |

Anything not on this list is new coupling. A new entry needs a line in the sprint contract stating
why the read cannot be an event instead.

---

## Rule 2 — Event bus only

> **Side effects that cross a module boundary are raised via `app/shared/events.py`, never by a
> direct service-to-service call or a sibling repository write.**

Prevents **FM-4**. Enforced by `lint-imports` (the `*-no-cross-module-repository` contracts) plus
Evaluator review of the publish path.

### Correct — `app/activities/service.py` publishes; `app/alerts/service.py` subscribes

Neither module imports the other. The wiring lives in `app/main.py`.

```python
# app/activities/service.py — the producer knows nothing about alerts
self._bus.publish(
    EventName.ACTIVITY_STATUS_CHANGED,
    {
        "taskId": updated.id, "storeId": updated.store_id,
        "previousStatus": previous.value, "newStatus": requested.value,
        "priority": updated.priority.value, "assigneeId": updated.assignee_id,
    },
)
```

```python
# app/alerts/service.py — the consumer knows nothing about activities
def handle_activity_status_changed(self, event: Event) -> None:
    if event.payload.get("newStatus") != "BLOCKED":
        return
    self._repository.add(Notification(alert_type=AlertType.ESCALATION, ...))
```

```python
# app/main.py — the composition root, the only file that knows both
def wire_event_handlers() -> None:
    audit_sink.attach(event_bus)
    alerts_service.register_event_handlers(event_bus)
```

### Rejected

```python
# app/activities/service.py
from app.alerts.repository import notification_repository   # FM-4 — HG-1 and HG-4 failure

def update_status(self, task_id: str, requested: TaskStatus) -> Task:
    ...
    if requested is TaskStatus.BLOCKED:
        notification_repository.add(Notification(...))       # writes a sibling's store directly
```

Also rejected, and subtler because no repository is imported:

```python
from app.alerts.service import alerts_service               # still FM-4
alerts_service.raise_escalation(task_id)                    # a cross-module SIDE EFFECT by call
```

Calling a sibling service is permitted for **reads** (Rule 1) and forbidden for **writes**. The
distinction is the direction of state change, not the layer reached.

### What breaks without it

Three things, none visible at the call site:

1. **The audit trail loses the event.** `AuditSink.record` is subscribed to the bus, so an
   unpublished side effect produces no `AuditEntry`.
   `tests/shared/test_audit.py::test_an_unpublished_side_effect_leaves_no_audit_entry` states this
   directly. The notification exists but operations cannot see why.
2. **A second consumer becomes impossible to add** without editing `ActivitiesService`. When the
   client asks for an SMS escalation, the change lands in `activities` — a module that should not
   know escalation exists.
3. **`activities` can no longer be tested in isolation**, because exercising a status change now
   requires the alerts repository to be present and reset.

### Deciding: event or service read?

| Question | Answer → mechanism |
|---|---|
| Does the caller need a value back? | yes → sibling **service** read (Rule 1) |
| Does another module's state change? | yes → **event** |
| Would a second consumer plausibly care? | yes → **event** |
| Must it appear in the audit trail? | yes → **event** |

---

## Rule 3 — Error contract

> **No raw exceptions in services or routes. Every failure is an `AppError` subclass carrying
> `code`, `message` and `status_code`.**

Prevents **FM-2**. Enforced by `ruff` (`TRY002`, `TRY301`, `BLE001`), the source-level AST check in
`tests/test_architecture.py::test_services_raise_no_bare_exceptions`, and Evaluator review.

### Correct — `app/activities/service.py`

```python
from app.shared.errors import InvalidStatusTransitionError, TaskNotFoundError

def update_status(self, task_id: str, requested: TaskStatus) -> Task:
    task = self.get_task(task_id)                     # raises TaskNotFoundError (404)
    if not can_transition(task.status, requested):
        raise InvalidStatusTransitionError(task_id, task.status.value, requested.value)  # 409
```

The repository returns `None`; the **service** decides that absence is an error:

```python
# app/activities/service.py
task = self._repository.get(task_id)
if task is None:
    raise TaskNotFoundError(task_id)
```

That split is what lets the Phase 5 bulk-status endpoint treat one missing task as a *partial*
failure rather than failing the whole request.

### Rejected

```python
raise Exception(f"task {task_id} not found")          # ruff TRY002
raise ValueError("bad status")                        # untyped, becomes a 500
raise HTTPException(status_code=404, detail="...")    # HTTP concern leaking into a service
return {"error": "not found"}                         # error as a return value: caller won't check
except Exception:                                     # ruff BLE001
    pass
```

### The available subclasses — use one, do not invent a code

Defined in `app/shared/errors.py`. Codes must be unique;
`tests/test_architecture.py::test_every_app_error_subclass_declares_a_distinct_code` enforces it.

| Class | `code` | HTTP |
|---|---|---|
| `TaskNotFoundError(task_id)` | `TASK_NOT_FOUND` | 404 |
| `ProjectNotFoundError(project_id)` | `PROJECT_NOT_FOUND` | 404 |
| `UserNotFoundError(user_id)` | `USER_NOT_FOUND` | 404 |
| `NotificationNotFoundError(notification_id)` | `NOTIFICATION_NOT_FOUND` | 404 |
| `StoreNotFoundError(store_id)` | `STORE_NOT_FOUND` | 404 |
| `ValidationError(message)` | `VALIDATION_ERROR` | 422 |
| `ConflictError(message)` | `CONFLICT` | 409 |
| `InvalidStatusTransitionError(task_id, current, requested)` | `INVALID_STATUS_TRANSITION` | 409 |
| `DuplicateMemberError(project_id, user_id)` | `DUPLICATE_MEMBER` | 409 |
| `ForbiddenWriteError(module, operation)` | `FORBIDDEN_WRITE` | 403 |

`NotFoundError` (404) and `ConflictError` (409) are family bases — catch them to handle a family
without enumerating codes.

A genuinely new failure needs a **new subclass** in `app/shared/errors.py`, not a reused code with a
different message. Adding one is a contract change and belongs in the sprint contract.

### Wire format

The Python attribute is `status_code` (snake_case, so `ruff N815` passes). The JSON field is
`statusCode`, per the capstone brief. `AppError.to_payload()` bridges the two:

```json
{"error": {"code": "TASK_NOT_FOUND", "message": "Task 'task-999' does not exist",
           "statusCode": 404, "details": {"taskId": "task-999"}}}
```

### What breaks without it

A `ValueError` from a service reaches `unhandled_exception_handler` and returns
`{"error": {"code": "INTERNAL_ERROR", ...}}` with HTTP 500. The store manager sees "an unexpected
internal error occurred" for what was really "that activity is already done", and the client app
cannot branch on it. Reaching that handler is a defect, which is why it logs at `exception` level —
so the Monitor can spot it in a run log.

---

## Rule 4 — Layer separation

> **Routes → Service → Repository, no skipping. Routes hold no business logic. Repositories call no
> services and no external systems.**

Prevents **FM-1** and **FM-4** at source. Enforced by `lint-imports`
(`routes-never-import-repositories`, `module-layers`) and
`tests/test_architecture.py::test_routes_never_import_a_repository`.

### Layer responsibilities

| Layer | Does | Must not |
|---|---|---|
| `routes.py` | HTTP binding, Pydantic schema validation, delegate to the service | import a repository; contain a business rule; catch `AppError` |
| `service.py` | business rules, transition validation, raise `AppError`, publish events | know about HTTP status codes or `Request` |
| `repository.py` | in-memory persistence, filtering, id generation | import a service; raise a domain error; publish an event |

### Correct — `app/activities/routes.py`

Two lines of body. Schema validation is the Pydantic model's job; the rule is the service's.

```python
@router.patch("/{task_id}/status", response_model=Task)
def update_task_status(task_id: str, payload: TaskStatusUpdate) -> Task:
    """Change an activity's status, publishing one ACTIVITY_STATUS_CHANGED event."""
    return activities_service.update_status(task_id, payload.status)
```

### Rejected

```python
from app.activities.repository import task_repository        # HG-5 failure

@router.patch("/{task_id}/status")
def update_task_status(task_id: str, payload: TaskStatusUpdate) -> Task:
    task = task_repository.get(task_id)                      # skips the service
    if task is None:
        raise HTTPException(404, "not found")                 # and the error contract
    if task.status == TaskStatus.DONE:                        # business rule in the route
        raise HTTPException(409, "already done")
    return task_repository.replace(task.model_copy(update={"status": payload.status}))
```

### What breaks without it

The transition rule now lives in the route, so `AlertsService.handle_activity_status_changed`
cannot reuse it — an event-driven status change would bypass validation entirely. It is also
untestable below HTTP: `tests/activities/test_activities_service.py` exercises the transition table
directly against the service, and none of those cases would be reachable. And no event is
published, so the change never reaches the audit sink or alerts.

> **Note on `lint-imports` semantics.** The `module-layers` contract does **not** forbid
> `routes → repository`: in a layers contract a higher layer may import any lower layer. Layer
> skipping is caught only by the explicit `routes-never-import-repositories` forbidden contract.
> Deleting that contract silently removes the protection.

---

## Rule 5 — Read-only reports

> **`app/reports/` aggregates from activities, programmes and staff. It never writes to them,
> publishes no events, and creates no rows.**

Prevents **FM-1** and **FM-4**. Enforced by `lint-imports` (`reports-reads-only-via-services`) and
`tests/reports/test_reports_read_only.py`.

### Correct — `app/reports/service.py`

Reads three sibling services, computes, returns. Nothing persists.

```python
tasks = self._activities.tasks_for_store(store_id)          # sibling SERVICE
programmes = self._programmes.projects_for_store(store_id)  # sibling SERVICE
staff = self._staff.users_for_store(store_id)               # sibling SERVICE
return StoreSummary(store_id=store_id, total_tasks=len(tasks), ...)   # computed, not stored
```

`ReportRepository` exposes exactly `list_all`, `get`, `count`, `reset` — **there is no `add`**. The
guarantee is enforced by the shape of the class: a Generator cannot call an API that does not exist.
`FORBIDDEN_WRITE_METHODS` in `app/reports/repository.py` names the banned method names, and
`test_report_repository_exposes_no_write_method` asserts their absence by introspection.

### Rejected

```python
from app.activities.repository import task_repository        # HG-6 failure

def get_store_summary(self, store_id: str) -> StoreSummary:
    for task in task_repository.list_all(store_id=store_id):
        task_repository.replace(task.model_copy(update={"reported": True}))   # reports writing
    self._repository.add(Report(...))                          # persisting a read
    self._bus.publish("REPORT_GENERATED", {...})               # a read emitting a mutation event
```

### What breaks without it

`reports` becomes a second source of truth for task state. Two code paths now mutate `Task`, and a
reporting bug can corrupt operational data — the failure mode where *running a summary changes the
thing being summarised*. Persisting a row per read also makes the endpoint non-idempotent:
refreshing a dashboard inflates the `Report` store, and the audit trail fills with state changes
that never happened.

**If a future feature genuinely must persist a `Report`** — PDF section 3.4's regional rollup
"triggers a REGIONAL_ROLLUP Report record via the event bus" — the write does **not** move into
`reports`. `reports` publishes nothing; the owning module publishes an event and a subscriber
persists it. That design decision belongs in the sprint contract before any code is written.

---

## Enforcement summary

| Rule | FM | Automated check | Command |
|---|---|---|---|
| 1 Module boundary | FM-1 | 5 × `*-no-cross-module-repository` contracts | `lint-imports` |
| 2 Event bus only | FM-4 | contracts + Evaluator review of the publish path | `lint-imports` |
| 3 Error contract | FM-2 | `TRY002` / `TRY301` / `BLE001` + AST test | `ruff check .` |
| 4 Layer separation | FM-1, FM-4 | `routes-never-import-repositories`, `module-layers` | `lint-imports` |
| 5 Read-only reports | FM-1, FM-4 | `reports-reads-only-via-services` + introspection tests | `lint-imports` |

All five are covered by the single gate:

```
mypy . && ruff check . && lint-imports && pytest --cov
```

**A violation of any rule is a hard-gate FAIL, never a scored deduction.** A boundary breach at 95%
code quality is still a boundary breach: it cannot be safely merged, so there is no score that
should let it through.

### Known coverage limit — state this honestly rather than implying total coverage

The `forbidden` contracts set `allow_indirect_imports = True`, i.e. they check **direct** imports
only. This is required for correctness, not laziness: checking transitively reports the mandated
chain `routes → service → repository` as a violation and makes the gate unpassable (see
`JOURNAL.md` D-06). PDF section 3.5's wording — "no module may import *directly* from another
module's repository" — matches.

The residual gap: a breach laundered through an intermediary, e.g.
`activities.service → some_helper → alerts.repository`, passes `lint-imports`. Two compensating
controls: the AST checks in `tests/test_architecture.py`, and the Evaluator's obligation to **read
the publish path** rather than trust the contract report alone.
