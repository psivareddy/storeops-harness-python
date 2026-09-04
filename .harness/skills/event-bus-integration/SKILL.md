# Skill: event-bus-integration

**Purpose.** How to publish a StoreOps domain event, how the audit subscription works, how to add a
subscriber, and the exact wrong turns that produce a cross-module write without an event.

**Read by:** Generator only.

**Prevents Failure Mode 4** — missing event bus integration; state changes written directly to
sibling module repositories.

> **Boundary with [architecture-principles](../architecture-principles/SKILL.md) Rule 2.** That file
> states the rule and the event-vs-read decision. This file is the working reference: the call
> shape, payload key conventions, the wiring point, and how to assert counts.

---

## 1. What is already wired

`app/shared/events.py` provides `EventBus` with `publish` / `subscribe`, the `Event` record, and
the `EventName` catalogue. `app/shared/audit.py` provides `AuditSink`. `app/main.py` wires them:

```python
def wire_event_handlers() -> None:
    audit_sink.attach(event_bus)                        # audits the WHOLE catalogue
    alerts_service.register_event_handlers(event_bus)   # alerts subscribes to what it needs
```

Current catalogue — three types, every one audited:

| Event | Published by | Consumed by |
|---|---|---|
| `ACTIVITY_CREATED` | `ActivitiesService.create_task` | audit sink |
| `ACTIVITY_STATUS_CHANGED` | `ActivitiesService.update_status` | audit sink, `AlertsService.handle_activity_status_changed` |
| `PROGRAMME_MEMBER_ADDED` | `ProgrammesService.add_member` | audit sink |

`AuditSink.attach(bus)` with no event list subscribes to **all** of `EventName`, so a new event
type is audited automatically — nobody has to remember to add it.

---

## 2. Publishing

```python
from app.shared.events import EventBus, EventName, event_bus

self._bus.publish(
    EventName.ACTIVITY_STATUS_CHANGED,
    {
        "taskId": updated.id,
        "storeId": updated.store_id,
        "previousStatus": previous.value,
        "newStatus": requested.value,
        "priority": updated.priority.value,
        "assigneeId": updated.assignee_id,
    },
)
```

### Payload rules

- **Plain mappings only — never a domain model.** `app.shared` may not import a business module, so
  a payload containing a `Task` would invert the dependency and put the event bus in the business
  of knowing the domains it exists to decouple.
- **camelCase keys.** `taskId`, not `task_id`. Payloads are wire-shaped, like `AppError.details`.
- **`.value` on every enum.** Pass `updated.priority.value`, not the enum member. A `StrEnum` member
  serialises fine but a consumer comparing `payload["newStatus"] == "BLOCKED"` should compare
  strings to strings — that comparison is exactly what `AlertsService` does.
- **Include identifiers a consumer needs to act, not the whole entity.** `assigneeId` is present
  because the alerts subscriber must know who to notify. If a consumer needs more, it calls the
  owning module's **service** (Rule 1) rather than the payload growing.
- **Publish once per state change.** N successful updates publish N events, never N+1. This is the
  invariant every side-effect test asserts.

### Where the publish goes

Last, after the write succeeds:

```python
self._repository.replace(updated)          # persist first
self._bus.publish(EventName.ACTIVITY_STATUS_CHANGED, {...})   # then publish
return updated
```

Publishing before the write lets a subscriber act on a change that has not happened. Publishing on a
failure path writes an audit entry for a change that was rejected. Every `raise` in the method must
come before the `publish`.

---

## 3. Subscribing

A consuming module exposes a registration method and a handler. The handler takes an `Event` and
returns `None`.

```python
# app/alerts/service.py
def register_event_handlers(self, bus: EventBus | None = None) -> None:
    target = bus if bus is not None else self._bus
    target.subscribe(EventName.ACTIVITY_STATUS_CHANGED, self.handle_activity_status_changed)

def handle_activity_status_changed(self, event: Event) -> None:
    new_status = event.payload.get("newStatus")
    if new_status != "BLOCKED":          # not our concern; return quietly
        return

    recipient_id = event.payload.get("assigneeId")
    if not isinstance(recipient_id, str) or not recipient_id:
        logger.warning("... has no assignee; no alert raised")
        return                            # degrade, do not raise

    self._repository.add(Notification(alert_type=AlertType.ESCALATION, ...))
```

### Handler rules

- **A handler is subscribed to every occurrence of its event, so it must tolerate the cases it does
  not care about.** `handle_activity_status_changed` fires on every status change and returns early
  for all but `BLOCKED`.
- **Never raise from a handler.** `publish` invokes subscribers synchronously inside the publisher's
  call, so an exception would propagate into `ActivitiesService.update_status` and fail an
  already-persisted write. Missing or malformed payload fields are logged and skipped —
  `tests/alerts/test_alerts_event_driven.py::test_handler_tolerates_a_payload_with_missing_fields`
  asserts this with an empty payload.
- **Write only through your own repository.** `AlertsService` writes `notification_repository`.
  It must not touch `app.activities.repository`.
- **Treat the payload as untrusted.** Use `.get()` and `isinstance` checks; it is a plain mapping,
  not a validated model.

### Registering a new subscriber

Add the `subscribe` call in the module's `register_event_handlers`, then call that method from
`wire_event_handlers()` in `app/main.py`. **Wiring belongs in the composition root** — never at
module import time, because then the subscription depends on whether the module happened to be
imported, making cross-module behaviour import-order-dependent.

`EventBus.subscribe` is **idempotent**: re-registering the same bound method is a no-op. This is
what makes `create_app()` safe to call per test without multiplying side effects. Do not "simplify"
that guard away — `tests/shared/test_events.py::test_subscribe_is_idempotent_so_wiring_twice_does_not_double_side_effects`
protects it.

### Adding a new event type

1. Add the member to `EventName` in `app/shared/events.py`, value identical to the name
   (`tests/shared/test_events.py::test_event_catalogue_values_match_their_names` asserts this).
2. Publish it from the owning service.
3. The audit sink picks it up automatically via `attach(bus)`.
4. Only add a subscriber if a module must react.

A new event type changes the audit surface, so the sprint contract should name it explicitly.

---

## 4. Rejected patterns

### Rejected — direct sibling repository write

```python
# app/activities/service.py
from app.alerts.repository import notification_repository     # FM-4; HG-1 and HG-4 FAIL

def update_status(self, task_id: str, requested: TaskStatus) -> Task:
    task = self.get_task(task_id)
    updated = task.model_copy(update={"status": requested})
    self._repository.replace(updated)
    if requested is TaskStatus.BLOCKED:
        notification_repository.add(                          # writes a sibling's store directly
            Notification(alert_type=AlertType.ESCALATION, recipient_id=task.assignee_id, ...)
        )
    return updated
```

Caught by `lint-imports` (`activities-no-cross-module-repository`). Three consequences, none visible
at the call site:

1. **No audit entry.** `AuditSink` is subscribed to the *bus*; nothing was published, so nothing was
   recorded. The notification exists and operations cannot see why.
   `tests/shared/test_audit.py::test_an_unpublished_side_effect_leaves_no_audit_entry` states this.
2. **A second consumer cannot be added** without editing `ActivitiesService` — a module that should
   not know escalation exists.
3. **`activities` can no longer be tested alone**, because a status change now requires the alerts
   repository present and reset.

### Rejected — cross-module side effect by service call

```python
from app.alerts.service import alerts_service                 # still FM-4
alerts_service.raise_escalation(task_id)                      # no repository imported, still wrong
```

`lint-imports` does **not** catch this — no repository is imported. It is caught by Evaluator
review, which is why the Evaluator is required to read the publish path rather than trust a green
contract report. Calling a sibling service is permitted for **reads** and forbidden for **writes**.

### Rejected — publishing before persisting

```python
self._bus.publish(EventName.ACTIVITY_STATUS_CHANGED, {...})   # subscriber runs now
self._repository.replace(updated)                             # ... before this
```

The alerts subscriber creates an escalation for a task whose status has not yet changed. If the
write then fails, the notification and the audit entry describe a change that never happened.

### Rejected — publishing on a failure path

```python
if not can_transition(task.status, requested):
    self._bus.publish(EventName.ACTIVITY_STATUS_CHANGED, {...})   # audit entry for a rejected change
    raise InvalidStatusTransitionError(...)
```

Breaks the invariant every partial-failure AC depends on: **a failed item produces neither an event
nor an audit entry.**

### Rejected — a domain model in the payload

```python
self._bus.publish(EventName.ACTIVITY_STATUS_CHANGED, {"task": updated})   # a Task instance
```

Couples every consumer to the `activities` schema, so a field rename in `Task` silently changes the
event contract.

---

## 5. Asserting events and audit entries

**Counts, not existence.** "An event was published" is satisfied by publishing three.

### Isolated (preferred for "nothing was published")

The `activities` fixture in `tests/conftest.py` gives a private bus, repository and audit sink:

```python
def test_update_publishes_exactly_one_event(activities: ActivitiesHarness) -> None:
    activities.service.update_status("task-1", TaskStatus.DONE)

    events = activities.bus.published_of(EventName.ACTIVITY_STATUS_CHANGED)
    assert len(events) == 1
    assert events[0].payload["previousStatus"] == "TODO"
    assert events[0].payload["newStatus"] == "DONE"
    assert activities.audit.count_for(EventName.ACTIVITY_STATUS_CHANGED) == 1
```

### Through the application

The `reset_state` autouse fixture clears the shared log before each test, so the process bus is
assertable:

```python
from app.shared.audit import audit_sink
from app.shared.events import EventName, event_bus

client.patch("/api/tasks/task-1/status", json={"status": "DONE"})

assert len(event_bus.published_of(EventName.ACTIVITY_STATUS_CHANGED)) == 1
assert audit_sink.count_for(EventName.ACTIVITY_STATUS_CHANGED) == 1
```

### Cross-boundary

To prove producer and consumer connect without importing each other, put both on one bus:

```python
def test_blocking_raises_an_escalation(alerts: AlertsHarness) -> None:
    ActivitiesService(bus=alerts.bus).update_status("task-1", TaskStatus.BLOCKED)

    escalations = [n for n in alerts.service.notifications_for_task("task-1")
                   if n.alert_type is AlertType.ESCALATION]
    assert len(escalations) == 1
```

> **Trap.** `notification-1` is seeded against `task-1`, so a raw count of notifications for
> `task-1` is 1 before anything happens. Filter by `alert_type`, or compare before/after counts.
> This cost two failing tests in Phase 1.

### Useful API surface

`bus.published` (all), `bus.published_of(name)`, `bus.subscriber_count(name)`, `bus.clear_log()`,
`bus.reset()`; `sink.entries`, `sink.entries_for(name)`, `sink.count_for(name)`, `sink.clear()`.

---

## 6. Generator checklist for this skill

- [ ] Every cross-module side effect goes through `bus.publish` — no sibling repository import
- [ ] No cross-module **write** performed by calling a sibling service
- [ ] `publish` is the last step, after the repository write succeeds
- [ ] No `publish` on any failure path
- [ ] Exactly one event per state change; N updates produce N events
- [ ] Payload is a plain mapping with camelCase keys and `.value` on enums
- [ ] New event types added to `EventName` with value identical to name
- [ ] New subscribers registered via `register_event_handlers`, called from `wire_event_handlers()`
- [ ] Handlers tolerate irrelevant events and malformed payloads, and never raise
- [ ] Tests assert event **count** and audit **count**, including zero on failure paths
