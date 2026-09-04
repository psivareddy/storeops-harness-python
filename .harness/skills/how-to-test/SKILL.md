# Skill: how-to-test

**Purpose.** What a StoreOps test must assert to count as a test. The four required assertions, the
fixtures that already exist, and why a status-only assertion is a hard-gate failure rather than a
weak test.

**Read by:** Generator only.

**Prevents Failure Mode 3** — tests asserting HTTP status codes without verifying business rule
compliance.

---

## 1. The four required assertions

Every test of business behaviour asserts **all four that apply**. This is HG-3.

| # | Assert | How |
|---|---|---|
| 1 | **Resulting state** | read it back; do not trust the response body alone |
| 2 | **Error code** | `AppError.code` or `response.json()["error"]["code"]` — not the HTTP status |
| 3 | **Published events** | type **and count**, via `bus.published_of(name)` |
| 4 | **Audit entries** | **count**, via `sink.count_for(name)` |

On a failure path, 3 and 4 assert **zero**. That is not padding: "a failed item produces neither an
event nor an audit entry" is the invariant a partial-failure endpoint lives or dies by, and nothing
else detects a partial write.

### Why status-only assertion is rejected outright

```python
def test_bulk_status(client):
    response = client.patch("/api/activities/bulk-status", json={...})
    assert response.status_code == 207          # REJECTED — HG-3 FAIL
```

This passes against an implementation that updates nothing, publishes nothing, writes no audit
entries, and returns a hardcoded 207. It is worse than having no test: it produces a green suite
that certifies nothing, which is exactly the failure the client observed. A `409` also cannot
distinguish `INVALID_STATUS_TRANSITION` from `DUPLICATE_MEMBER`, and a `404` cannot distinguish
`TASK_NOT_FOUND` from `USER_NOT_FOUND` — so the status is not even a proxy for the behaviour.

Asserting the status **alongside** the other three is correct and expected. The rule is
*status is never the only assertion*.

---

## 2. Layout and naming

```
tests/
  conftest.py                 fixtures (see §3)
  __init__.py                 required — tests is a package
  activities/  alerts/  programmes/  reports/  shared/  staff/
                              each with __init__.py
  test_architecture.py        rule enforcement at source level
  test_main.py                wiring, endpoint inventory
```

`tests/` mirrors `app/`. Every directory needs `__init__.py` — tests import `tests.conftest`, and
without the package markers mypy reports *"Source file found twice under different module names"*.

**File:** `tests/<module>/test_<feature>.py`
**Function:** `test_<behaviour_being_asserted>` — the behaviour, not the mechanism.

| Rejected | Accepted |
|---|---|
| `test_bulk_status` | `test_partial_failure_returns_207_and_updates_only_valid_tasks` |
| `test_error_case` | `test_done_task_in_batch_yields_invalid_status_transition_and_no_event` |
| `test_service` | `test_all_success_publishes_one_event_per_task` |

The sprint contract names these. **Create the test with the exact name the AC specifies** — the
Evaluator checks that named test exists and passes.

Every test needs a return annotation (`-> None`); mypy runs strict over `tests/` too.

---

## 3. Fixtures that already exist — use them

From `tests/conftest.py`:

| Fixture | Gives |
|---|---|
| `reset_state` | **autouse.** Re-seeds all five repositories, clears the bus log and audit sink around every test |
| `client` | `TestClient` over a fresh `create_app()` |
| `activities` | `ActivitiesHarness(service, repository, bus, audit)` — fully isolated |
| `alerts` | `AlertsHarness(service, repository, bus)` with handlers registered |

Helpers: `api_endpoints(client, prefix="/api/")` → `{(METHOD, path)}` read from the OpenAPI schema;
`endpoint_tags(client)` → the set of operation tags.

### Isolated harness vs. the shared process bus

Use the **`activities` / `alerts` harness** when asserting *"nothing was published"*. A private
`EventBus` makes `len(bus.published) == 0` meaningful; against the process bus it only holds
because `reset_state` cleared it, which is a weaker guarantee.

Use the **`client` fixture** for end-to-end behaviour, importing `event_bus` and `audit_sink`
directly to assert counts — `reset_state` has already cleared them.

`reset_state` deliberately does **not** reset subscriptions. Dropping them would make the
event-driven alert tests pass for the wrong reason.

### Do not construct your own reset logic

Repository singletons are shared. A test that mutates `task_repository` without `reset_state`
leaks into the next test. If you need pristine state *and* isolation, construct
`TaskRepository()` directly — as the `activities` fixture does.

---

## 4. Worked patterns

### Success path — service level

```python
def test_update_status_changes_state_publishes_one_event_and_writes_one_audit_entry(
    activities: ActivitiesHarness,
) -> None:
    before = activities.service.get_task("task-1")
    assert before.status is TaskStatus.TODO

    updated = activities.service.update_status("task-1", TaskStatus.DONE)

    # 1. resulting state — read back, not just the return value
    assert updated.status is TaskStatus.DONE
    assert activities.service.get_task("task-1").status is TaskStatus.DONE

    # 3. exactly one event, carrying both statuses
    events = activities.bus.published_of(EventName.ACTIVITY_STATUS_CHANGED)
    assert len(events) == 1
    assert events[0].payload["previousStatus"] == "TODO"
    assert events[0].payload["newStatus"] == "DONE"

    # 4. exactly one audit entry
    assert activities.audit.count_for(EventName.ACTIVITY_STATUS_CHANGED) == 1
```

### Failure path — all four, with zeros

```python
def test_transition_from_done_raises_conflict_and_leaves_state_and_logs_untouched(
    activities: ActivitiesHarness,
) -> None:
    with pytest.raises(InvalidStatusTransitionError) as caught:
        activities.service.update_status("task-4", TaskStatus.TODO)

    # 2. error code and status, plus the identifying details
    assert caught.value.code == "INVALID_STATUS_TRANSITION"
    assert caught.value.status_code == 409
    assert caught.value.details["currentStatus"] == "DONE"

    # 1. state unchanged
    assert activities.service.get_task("task-4").status is TaskStatus.DONE

    # 3 + 4. no event, no audit entry for a rejected change
    assert len(activities.bus.published) == 0
    assert len(activities.audit.entries) == 0
```

### Route level — status alongside the rest

```python
def test_patch_status_updates_state_publishes_one_event_and_audits_once(
    client: TestClient,
) -> None:
    response = client.patch("/api/tasks/task-1/status", json={"status": "DONE"})

    assert response.status_code == 200                                    # never alone
    assert response.json()["status"] == "DONE"
    assert client.get("/api/tasks/task-1").json()["status"] == "DONE"     # read back

    events = event_bus.published_of(EventName.ACTIVITY_STATUS_CHANGED)
    assert len(events) == 1
    assert audit_sink.count_for(EventName.ACTIVITY_STATUS_CHANGED) == 1
```

### Error envelope

```python
response = client.patch("/api/tasks/task-4/status", json={"status": "TODO"})

assert response.status_code == 409
error = response.json()["error"]
assert error["code"] == "INVALID_STATUS_TRANSITION"
assert error["statusCode"] == 409                      # the camelCase WIRE field
assert error["details"]["currentStatus"] == "DONE"
assert client.get("/api/tasks/task-4").json()["status"] == "DONE"
assert len(event_bus.published_of(EventName.ACTIVITY_STATUS_CHANGED)) == 0
```

### Counting invariant for a bulk operation

The assertion a partial-failure AC exists for:

```python
def test_partial_failure_returns_207_and_updates_only_valid_tasks(client: TestClient) -> None:
    response = client.patch(
        "/api/activities/bulk-status",
        json={"task_ids": ["task-1", "task-2", "task-999"], "status": "DONE"},
    )

    assert response.status_code == 207
    body = response.json()
    assert {t["id"] for t in body["succeeded"]} == {"task-1", "task-2"}
    assert [f["code"] for f in body["failed"]] == ["TASK_NOT_FOUND"]

    # state: the two valid tasks moved, the missing one did not exist to move
    assert client.get("/api/tasks/task-1").json()["status"] == "DONE"
    assert client.get("/api/tasks/task-2").json()["status"] == "DONE"

    # counts: two successes -> exactly two events and two audit entries, not three
    assert len(event_bus.published_of(EventName.ACTIVITY_STATUS_CHANGED)) == 2
    assert audit_sink.count_for(EventName.ACTIVITY_STATUS_CHANGED) == 2
```

`== 2`, not `>= 1`. An implementation that publishes per *requested* id rather than per *successful*
update passes a `>= 1` check and fails this one.

---

## 5. Coverage

`pyproject.toml` sets `fail_under = 80` with `branch = true`, so `pytest --cov` fails the gate below
80%. The Phase 1 baseline is **99.63% over 160 tests**; a change that drops it needs a stated
reason, not silence.

**Coverage is necessary, not sufficient.** A status-only test executes the whole endpoint and
reports high coverage while asserting nothing. That is why HG-3 checks the four assertions
*separately* from the coverage number — the two together are the gate, and coverage alone is
precisely the metric the original failure mode gamed.

Prefer parametrising over the transition table, the enum members, or the seed fixtures to cover
branches meaningfully:

```python
@pytest.mark.parametrize("current", [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED])
def test_same_status_is_never_a_valid_transition(current: TaskStatus) -> None:
    assert can_transition(current, current) is False
```

---

## 6. Seed fixtures — build on them, do not rebuild them

| Need | Use |
|---|---|
| a `TODO` task with an assignee | `task-1` (HIGH, RESTOCKING, store-101, user-3) |
| an `IN_PROGRESS` task | `task-2` |
| a `BLOCKED`, overdue task | `task-3` (CRITICAL, COMPLIANCE) |
| **a `DONE` task — the invalid-transition case** | `task-4` |
| **a task with no assignee** | `task-5` |
| a non-existent task | `task-999` |
| **a `CLOSED` programme** | `project-3` |
| an existing member (duplicate case) | `user-2` on `project-1` |
| a non-existent user / store | `user-999` / `store-999` |

> **Trap.** `notification-1` is seeded against `task-1`, so "one notification exists for task-1" is
> already true before anything happens. Filter by `alert_type`, or compare before/after counts.
> This cost two failing tests in Phase 1.

Time-sensitive assertions must inject the clock rather than using wall time:
`reports_service.get_store_summary("store-101", now=NOW)` with a module-level fixed `NOW`. Seed
`due_at` values are relative to `2026-08-31T08:00:00Z`, so a real-time comparison changes answers
between runs.

---

## 7. Architecture tests are part of the suite

`tests/test_architecture.py` parses `app/**` with `ast` and enforces what a dependency analyser
cannot: routes importing no repository, services raising no builtins, `app.shared` importing no
business module, every module having all four layers, and `AppError` codes being unique. If a
sprint adds a module or a layer, these parametrised tests must still pass — they iterate over the
`MODULES` tuple, so a new module is picked up automatically once added there.

---

## 8. Generator checklist for this skill

- [ ] Every business test asserts state, error code, event count, audit count — all that apply
- [ ] **No test asserts an HTTP status as its only assertion**
- [ ] Failure-path tests assert **zero** events and **zero** audit entries
- [ ] Side-effect assertions use `==` with an exact count, never `>=`
- [ ] Resulting state is read back, not inferred from the response body
- [ ] Error tests assert `code`, not just the status
- [ ] Test names match the contract's AC mapping exactly
- [ ] Existing fixtures used; no bespoke reset logic
- [ ] `-> None` on every test function
- [ ] `__init__.py` present in any new `tests/` subdirectory
- [ ] Coverage ≥ 80% and not materially below the 99.63% baseline
- [ ] Time-dependent behaviour injects a clock
