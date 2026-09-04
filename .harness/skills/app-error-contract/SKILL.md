# Skill: app-error-contract

**Purpose.** How to raise, extend and test StoreOps errors. Includes the exhaustive list of
prohibited raw-exception patterns and the tool that catches each one.

**Read by:** Generator only.

**Prevents Failure Mode 2** — raw error throws bypassing the typed `AppError` hierarchy.

> **Boundary with [architecture-principles](../architecture-principles/SKILL.md) Rule 3.** That file
> states the rule and the consequence. This file is the working reference: which subclass to pick,
> how to add one, where the raise goes, and how to assert it.

---

## 1. The contract in one paragraph

Every failure a StoreOps service or route surfaces is an instance of `AppError` from
`app/shared/errors.py`, carrying `code` (a stable machine-readable string), `message` (human text)
and `status_code` (HTTP). Subclasses set `code` and `status_code` as **class attributes** so a raise
site never restates them — that is what keeps codes stable enough for a client to branch on.
`AppError.to_payload()` renders the wire format, and the handler registered by
`register_error_handlers()` turns any escaping `AppError` into that envelope.

```json
{"error": {"code": "TASK_NOT_FOUND", "message": "Task 'task-999' does not exist",
           "statusCode": 404, "details": {"taskId": "task-999"}}}
```

**`status_code` in Python, `statusCode` on the wire.** The attribute is snake_case so `ruff N815`
passes; the JSON key is camelCase per the capstone brief. `to_payload()` is the only bridge — never
hand-build an error dict.

---

## 2. Pick an existing subclass — do not invent a code

All defined in `app/shared/errors.py`. Codes must be unique, and
`tests/test_architecture.py::test_every_app_error_subclass_declares_a_distinct_code` enforces it.

| Class | Constructor | `code` | HTTP |
|---|---|---|---|
| `TaskNotFoundError` | `(task_id)` | `TASK_NOT_FOUND` | 404 |
| `ProjectNotFoundError` | `(project_id)` | `PROJECT_NOT_FOUND` | 404 |
| `UserNotFoundError` | `(user_id)` | `USER_NOT_FOUND` | 404 |
| `NotificationNotFoundError` | `(notification_id)` | `NOTIFICATION_NOT_FOUND` | 404 |
| `StoreNotFoundError` | `(store_id)` | `STORE_NOT_FOUND` | 404 |
| `ValidationError` | `(message, details=...)` | `VALIDATION_ERROR` | 422 |
| `ConflictError` | `(message, details=...)` | `CONFLICT` | 409 |
| `InvalidStatusTransitionError` | `(task_id, current, requested)` | `INVALID_STATUS_TRANSITION` | 409 |
| `DuplicateMemberError` | `(project_id, user_id)` | `DUPLICATE_MEMBER` | 409 |
| `ForbiddenWriteError` | `(module, operation)` | `FORBIDDEN_WRITE` | 403 |

`NotFoundError` (404) and `ConflictError` (409) are family bases. Catch a base to handle a family
without enumerating codes:

```python
except NotFoundError:      # catches TaskNotFound, UserNotFound, StoreNotFound, ...
```

### Choosing between 422 and 409

- **422 `ValidationError`** — the request is structurally fine but violates a rule about *its own
  content*. Example: `add_member` on a `CLOSED` programme.
- **409 `ConflictError`** and subclasses — the request conflicts with *existing state*. Example:
  `task-4` is already `DONE`, so it cannot move to `TODO`.

If both readings fit, prefer the subclass that already exists over a generic one: the client gets a
specific code for free.

---

## 3. Where the raise goes

The **service** raises. The repository returns `None`; the route raises nothing.

```python
# app/activities/service.py — correct
def get_task(self, task_id: str) -> Task:
    task = self._repository.get(task_id)      # repository returns None, does not raise
    if task is None:
        raise TaskNotFoundError(task_id)      # the SERVICE decides absence is an error
    return task
```

```python
# app/activities/service.py — correct: rule violation raised before any write
if not can_transition(task.status, requested):
    raise InvalidStatusTransitionError(task_id, task.status.value, requested.value)
```

**Every raise must precede every `publish`.** Raising after a publish means an audit entry exists
for a change that was then rejected. See `component-patterns` §4 (validate → persist → publish).

---

## 4. Prohibited patterns — exhaustive, with the tool that catches each

| Rejected | Why | Caught by |
|---|---|---|
| `raise Exception("...")` | untyped; becomes a 500 with `INTERNAL_ERROR` | `ruff TRY002` |
| `raise ValueError("...")` | untyped; caller cannot branch | `ruff` + AST test |
| `raise RuntimeError("...")` | same | `ruff` + AST test |
| `raise KeyError(task_id)` | leaks a dict-access detail as an API failure | AST test |
| `raise HTTPException(404, "...")` **from a service** | HTTP concern in the business layer; unreachable from an event handler | AST test, Evaluator review |
| `raise AppError("...")` (the base directly) | no specific `code`; client sees `APP_ERROR` | Evaluator review |
| `return {"error": "not found"}` | a caller that forgets to check proceeds on bad data | Evaluator review |
| `return None` to signal failure **from a service** | indistinguishable from "no result"; loses the reason | Evaluator review |
| `except Exception:` / bare `except:` | swallows defects, including the ones the gate exists to find | `ruff BLE001` |
| `except Exception: pass` | as above, silently | `ruff BLE001` |
| `raise` inside a `try` that the same function catches | control flow via exceptions | `ruff TRY301` |
| A new code invented at a raise site | duplicate/unstable codes; breaks clients | duplicate-code test |

The AST test is `tests/test_architecture.py::test_services_raise_no_bare_exceptions`, which parses
each `app/<module>/service.py` and rejects a `raise` whose name is in
`{Exception, ValueError, RuntimeError, KeyError, TypeError, HTTPException}`.

### The one permitted `except AppError`

A **bulk aggregator in the service layer** may catch `AppError` to convert a per-item failure into a
per-item result. Nowhere else, and never in a route:

```python
for task_id in task_ids:
    try:
        succeeded.append(self.update_status(task_id, requested))
    except AppError as exc:                    # permitted here only
        failed.append(BulkItemFailure(task_id=task_id, code=exc.code, message=exc.message))
```

Note it re-surfaces `exc.code` — the per-item failure keeps its specific code rather than being
flattened to a generic message.

---

## 5. Adding a new subclass

Only when a sprint contract calls for a genuinely new failure. **A new code is a contract change**:
clients branch on it, so it belongs in the contract before any code is written. Reusing an existing
code with a different message is worse than adding one — it makes the code unreliable.

```python
class BulkRequestTooLargeError(ValidationError):     # inherit the family, get its status
    code = "BULK_REQUEST_TOO_LARGE"

    def __init__(self, submitted: int, limit: int) -> None:
        super().__init__(
            f"Bulk request contains {submitted} items; the limit is {limit}",
            details={"submitted": submitted, "limit": limit},
        )
```

Rules for a new subclass:

1. **Inherit the nearest family base** (`NotFoundError`, `ConflictError`, `ValidationError`) so the
   status code comes for free and family catches keep working.
2. **Set `code` as a class attribute**, upper snake case, unique.
3. **Take identifiers as constructor arguments** and put them in `details` with camelCase keys
   (`taskId`, `projectId`) — `details` is part of the wire contract.
4. **Do not override `status_code`** unless the family base is genuinely wrong for it.
5. Add it to the table in this file and in `architecture-principles` Rule 3.

`details` keys are camelCase because they are JSON. Python attribute names stay snake_case. This
asymmetry is deliberate and matches `to_payload()`.

---

## 6. The last-resort handler is a defect detector, not a control path

`app/shared/errors.py` registers two handlers:

```python
application.add_exception_handler(AppError, app_error_handler)
application.add_exception_handler(Exception, unhandled_exception_handler)
```

`unhandled_exception_handler` returns `INTERNAL_ERROR` / 500 and logs at `exception` level.
**Reaching it means a service raised outside the hierarchy — Failure Mode 2 in production.** It
exists so a client always receives the envelope shape, not to make raw raises acceptable.

It also deliberately does **not** echo the original message:
`tests/shared/test_errors.py::test_unhandled_exception_is_converted_to_the_envelope_without_leaking_detail`
raises with a fake connection string and asserts the secret is absent from the response. If you
ever extend that handler, keep that property.

---

## 7. Testing errors — assert the code, not just the status

An HTTP status is a coarse signal: `404` cannot distinguish `TASK_NOT_FOUND` from
`USER_NOT_FOUND`, and `409` cannot distinguish `INVALID_STATUS_TRANSITION` from
`DUPLICATE_MEMBER`. **Asserting status alone is Failure Mode 3** and fails HG-3.

### Service-level

```python
with pytest.raises(InvalidStatusTransitionError) as caught:
    activities.service.update_status("task-4", TaskStatus.TODO)

assert caught.value.code == "INVALID_STATUS_TRANSITION"
assert caught.value.status_code == 409
assert caught.value.details["currentStatus"] == "DONE"
# and the side-effect guarantee:
assert len(activities.bus.published) == 0
assert len(activities.audit.entries) == 0
```

### Route-level

```python
response = client.patch("/api/tasks/task-4/status", json={"status": "TODO"})

assert response.status_code == 409
error = response.json()["error"]
assert error["code"] == "INVALID_STATUS_TRANSITION"
assert error["statusCode"] == 409
assert error["details"]["currentStatus"] == "DONE"
# state unchanged:
assert client.get("/api/tasks/task-4").json()["status"] == "DONE"
```

Every error-path test asserts **four** things: the status, the `code`, that state did not change,
and that no event or audit entry was written. The last is the one most often omitted and the one
that catches a partial write.

### Fixtures that already exist

`task-4` is `DONE` (invalid transition), `task-999` does not exist (`TASK_NOT_FOUND`),
`user-999` does not exist (`USER_NOT_FOUND`), `project-3` is `CLOSED` (`VALIDATION_ERROR`),
`user-2` is already on `project-1` (`DUPLICATE_MEMBER`), `store-999` does not exist
(`STORE_NOT_FOUND`). Use them rather than building state.

---

## 8. Generator checklist for this skill

- [ ] Every failure raises an `AppError` **subclass**, never the base and never a builtin
- [ ] No `HTTPException` anywhere in `app/**/service.py`
- [ ] No `except Exception` / bare `except` in `app/**`
- [ ] No error returned as a dict or as `None` from a service
- [ ] Every raise precedes every `publish` in the same method
- [ ] Routes contain no `try`/`except` and no `raise`
- [ ] Any new subclass inherits a family base, sets a unique `code`, and is named in the contract
- [ ] `details` keys are camelCase
- [ ] Every error test asserts `code` — not the HTTP status alone
- [ ] Every error test asserts zero events and zero audit entries
