# Sprint 1 Contract: Shift handover bulk update

**Spec:** `.harness/output/spec.md`
**Feature prompt:** `PROMPT.md` §3
**Module written:** `app/activities/`
**Endpoints added or changed:** `PATCH /api/activities/bulk-status` (new). The REST endpoint
inventory goes **9 → 10**, so `tests/test_main.py::EXPECTED_ENDPOINTS` **must** be updated to
include `("PATCH", "/api/activities/bulk-status")`. This is a required in-scope edit, not
collateral damage — see Dependencies D-7 and Risk R-5.

> **Generation is forbidden until the final line of this file reads `STATUS: APPROVED`.**
> The Generator's first action is to read that line. If it reads anything else — including
> `STATUS: AWAITING APPROVAL` — the Generator stops immediately and writes nothing. Only a human
> may change it. No agent may, the Planner least of all, because a contract approved by its own
> author is not governance.

---

## Request and response shape

Stated here because the acceptance criteria assert against it.

**Request body**

| Field | Type | Constraint |
|---|---|---|
| `task_ids` | `list[str]` | at least 1 element (AC-6) |
| `status` | `TaskStatus` | must be `DONE` or `BLOCKED` (AC-4) |

**Response body** — the same shape for HTTP 200 and 207:

| Field | Meaning |
|---|---|
| `updated` | count of items that transitioned |
| `failed` | count of items that did not |
| `results` | one entry per element of `task_ids`, **in request order** |

Each `results` entry carries `taskId`, `outcome` (`UPDATED` or `FAILED`), the task's `status`
after the call, and for a failure an `error` object in the existing `AppError.to_payload()`
envelope — `code`, `message`, `statusCode`, `details`. Successful entries carry `error: null`.

**HTTP status selection**

| Condition | Status |
|---|---|
| Every item transitioned | **200** |
| At least one item failed and at least one transitioned | **207** |
| Every item failed | **207** |
| Request-level rejection (empty list, or target status not `DONE`/`BLOCKED`) | **422**, nothing is processed |

---

## Acceptance criteria

**AC-1:** GIVEN seeded `task-1` (TODO) and `task-2` (IN_PROGRESS)
WHEN `PATCH /api/activities/bulk-status` runs with `task_ids: ["task-1", "task-2"]` and
`status: DONE`
THEN both tasks read back as `DONE`, HTTP **200** is returned, `updated == 2` and `failed == 0`,
`results` has 2 entries both `UPDATED` in request order, **exactly 2**
`ACTIVITY_STATUS_CHANGED` events are published, AND **exactly 2** audit entries exist for
`ACTIVITY_STATUS_CHANGED`.

- **Modules:** `activities` (writes); none (reads)
- **Architecture rules:** Layer separation, Event bus only
- **Tests:** `tests/activities/test_activities_bulk_status.py::test_all_success_publishes_one_event_per_task`

**AC-2:** GIVEN seeded `task-1` (TODO) and `task-2` (IN_PROGRESS), and the id `task-999` which
does not exist
WHEN `PATCH /api/activities/bulk-status` runs with `task_ids: ["task-1", "task-999", "task-2"]`
and `status: DONE`
THEN `task-1` and `task-2` read back as `DONE`, the `task-999` entry is `FAILED` with
`error.code == "TASK_NOT_FOUND"` and `error.statusCode == 404`, HTTP **207** is returned,
`updated == 2` and `failed == 1`, `results` preserves request order,
**exactly 2** `ACTIVITY_STATUS_CHANGED` events are published, AND **exactly 2** audit entries
exist — **no event and no audit entry for `task-999`**.

- **Modules:** `activities` (writes); none (reads)
- **Architecture rules:** Layer separation, Error contract, Event bus only
- **Tests:** `tests/activities/test_activities_bulk_status.py::test_partial_failure_returns_207_and_updates_only_valid_tasks`

**AC-3:** GIVEN seeded `task-1` (TODO) and `task-4` (**DONE** — terminal, per
`ALLOWED_TRANSITIONS[TaskStatus.DONE] == frozenset()`)
WHEN `PATCH /api/activities/bulk-status` runs with `task_ids: ["task-1", "task-4"]` and
`status: DONE`
THEN `task-1` reads back as `DONE`, `task-4` is `FAILED` with
`error.code == "INVALID_STATUS_TRANSITION"` and `error.statusCode == 409`, `task-4` is unchanged
(still `DONE`, `updated_at` not advanced), HTTP **207** is returned, `updated == 1` and
`failed == 1`, **exactly 1** `ACTIVITY_STATUS_CHANGED` event is published, AND **exactly 1**
audit entry exists.

- **Modules:** `activities` (writes); none (reads)
- **Architecture rules:** Error contract, Event bus only, Layer separation
- **Tests:** `tests/activities/test_activities_bulk_status.py::test_done_task_in_batch_yields_invalid_status_transition_and_no_event`

**AC-4:** GIVEN seeded `task-1` (TODO) and `task-2` (IN_PROGRESS)
WHEN `PATCH /api/activities/bulk-status` runs with `task_ids: ["task-1", "task-2"]` and
`status: IN_PROGRESS` — a member of `TaskStatus` that is not a permitted handover target
THEN HTTP **422** is returned with `error.code == "VALIDATION_ERROR"`, **no** `results` body is
produced, `task-1` still reads back as `TODO` and `task-2` as `IN_PROGRESS`, **exactly 0** events
are published, AND **exactly 0** audit entries are added. The rejection happens before any
repository write.

- **Modules:** `activities` (writes attempted, none performed); none (reads)
- **Architecture rules:** Error contract, Layer separation
- **Tests:** `tests/activities/test_activities_bulk_status.py::test_target_status_outside_done_or_blocked_is_rejected_before_any_write`

**AC-5:** GIVEN seeded `task-4` (DONE) and the id `task-999` which does not exist — a batch in
which **every** item fails
WHEN `PATCH /api/activities/bulk-status` runs with `task_ids: ["task-4", "task-999"]` and
`status: BLOCKED`
THEN HTTP **207** is returned, `updated == 0` and `failed == 2`, `task-4` is unchanged (still
`DONE`), the two entries carry `INVALID_STATUS_TRANSITION` and `TASK_NOT_FOUND` respectively,
**exactly 0** `ACTIVITY_STATUS_CHANGED` events are published, AND **exactly 0** audit entries are
added. A failed item produces **neither** an event nor an audit entry — asserted here in
isolation because it is the likeliest defect in the whole sprint.

- **Modules:** `activities` (writes attempted, none performed); none (reads)
- **Architecture rules:** Event bus only, Error contract
- **Tests:** `tests/activities/test_activities_bulk_status.py::test_all_items_failing_publishes_no_event_and_writes_no_audit_entry`

**AC-6:** GIVEN no state change of any kind
WHEN `PATCH /api/activities/bulk-status` runs with `task_ids: []` and `status: DONE`
THEN HTTP **422** is returned, `updated`/`failed`/`results` are absent, **exactly 0** events are
published, AND **exactly 0** audit entries are added. An empty batch is a client error, not a
successful no-op — a naive loop returns HTTP 200 with `updated == 0` and passes every other
criterion in this contract.

- **Modules:** `activities` (writes attempted, none performed); none (reads)
- **Architecture rules:** Error contract, Layer separation
- **Tests:** `tests/activities/test_activities_bulk_status.py::test_empty_task_id_list_is_rejected_with_422_and_no_events`

### Assertion standard for every test above

Per [how-to-test](../skills/how-to-test/SKILL.md) and HG-3, each named test asserts every one of
these that applies, and **a test asserting only `response.status_code` is an automatic HG-3
FAIL**:

1. **Resulting state** — each task read back via `GET /api/tasks/{task_id}` or the service, not
   inferred from the response body
2. **Error code** — `error.code` on the per-item entry, not just the HTTP status
3. **Published events** — type **and exact count**, using `==`, never `>=`
4. **Audit entries** — exact count via `audit_sink.count_for("ACTIVITY_STATUS_CHANGED")`

Counts must be compared **before and after**, or filtered by event name. `audit_sink` is cleared
by the autouse `reset_state` fixture, so a bare `count_for` is safe here — but the equivalent
trap in `alerts` is real: `notification-1` already targets `task-1`
([app-context](../skills/app-context/SKILL.md) §5).

---

## Assumptions

| # | Assumption | If it is wrong |
|---|---|---|
| A-1 | The path is `/api/activities/bulk-status` exactly, hosted by a second `APIRouter` inside `app/activities/routes.py`. The PDF and the prompt both name it; the module's existing router is `prefix="/api/tasks"` | If the approver prefers `/api/tasks/bulk-status`, edit this contract's endpoint line and AC-1…AC-6 before approving. The ACs are otherwise unaffected |
| A-2 | A batch in which **every** item fails returns **207**, not 400 or 422. The request was well-formed; the items were not. 422 is reserved for request-level rejection (AC-4, AC-6) | AC-5's expected status changes. The event and audit counts — zero — do not |
| A-3 | Permitted target statuses are exactly `DONE` and `BLOCKED`. `TODO` and `IN_PROGRESS` are rejected at 422 even though both are valid `TaskStatus` members | AC-4's trigger value changes; the allow-list belongs in the service, not the route schema, so the rule stays testable below HTTP |
| A-4 | Repeated ids in one request are **not** de-duplicated. Each occurrence is processed in order, so a second occurrence of a successfully-updated task fails with `INVALID_STATUS_TRANSITION` (`DONE` is terminal). Counts therefore stay honest | If de-duplication is required it needs its own AC and its own count assertion; do not add it silently |
| A-5 | `results` preserves request order, so a client can zip it against its own input | Clients must key by `taskId`; AC-1 and AC-2's ordering clauses would be dropped |
| A-6 | No new `AppError` subclass is needed. `TaskNotFoundError`, `InvalidStatusTransitionError` and `ValidationError` cover every failure in this contract | A new subclass is a change to the shared error contract and requires a new sprint contract, not a Generator decision |
| A-7 | Existing per-item ordering is: validate the request, then for each id validate and write, then publish. A partial batch leaves the successful writes in place — there is no transaction and none is expected of an in-memory repository | If atomicity is required this becomes a different feature with a rollback design |

---

## Dependencies

Existing symbols this sprint relies on. **The Generator must reuse these, not reimplement them.**

| # | Symbol | Path | Used for |
|---|---|---|---|
| D-1 | `ActivitiesService.update_status` | `app/activities/service.py:84` | the single-item transition, including its validate → write → publish ordering. The batch iterates this rule; it does not restate it |
| D-2 | `can_transition`, `ALLOWED_TRANSITIONS` | `app/activities/models.py:36,44` | the transition table. `DONE` is terminal, which is what makes `task-4` the AC-3 fixture |
| D-3 | `TaskNotFoundError`, `InvalidStatusTransitionError`, `ValidationError` | `app/shared/errors.py` | per-item and request-level failures. `AppError.to_payload()` produces the `error` envelope |
| D-4 | `EventName.ACTIVITY_STATUS_CHANGED`, `event_bus.publish` | `app/shared/events.py` | the one event per successful update. Payload keys are fixed: `taskId`, `storeId`, `previousStatus`, `newStatus`, `priority`, `assigneeId` |
| D-5 | `audit_sink.count_for` | `app/shared/audit.py:58` | the audit-count assertions. `AuditSink` is already attached to the bus in `wire_event_handlers()` — no new subscription is needed or permitted |
| D-6 | `TaskStatus`, `Task`, `TaskStatusUpdate` | `app/activities/models.py` | enums and the single-status precedent for the new request schema |
| D-7 | `EXPECTED_ENDPOINTS` | `tests/test_main.py:13` | **must gain** `("PATCH", "/api/activities/bulk-status")`. Without this edit the inventory test fails and HG-7 fails with it |
| D-8 | `reset_state`, `client`, `activities` fixtures | `tests/conftest.py` | per-test isolation; `reset_state` re-seeds all five repositories and clears the bus log and audit sink |

---

## Risks

| # | Risk | Failure mode | Detected by |
|---|---|---|---|
| R-1 | Writing the audit entry directly instead of letting the published event reach `AuditSink` — the tempting shortcut, because "one audit entry per updated task" reads like an instruction to write one | **FM-4** | `lint-imports` (`activities-no-cross-module-repository`) if it imports a sibling repository → **HG-1, HG-4 FAIL**. If it calls `audit_sink.record` directly, `lint-imports` sees nothing: caught by the Evaluator reading the publish path top to bottom, per [how-to-review](../skills/how-to-review/SKILL.md) §3 blind spot 3 |
| R-2 | Catching too broadly to keep the loop going — `except Exception` around each item. This sprint is the **only** place in StoreOps permitted to catch per item, and the permitted form is narrow: `except AppError`, nothing wider | **FM-2** | `ruff` `BLE001` and `TRY302`; `tests/test_architecture.py::test_services_raise_no_bare_exceptions` → **HG-2 FAIL** |
| R-3 | Publishing per **requested id** rather than per **successful update** — the defect AC-5 exists to catch. It passes "an event was published" and fails a count | **FM-4** | AC-1/2/3/5 count assertions using `==` → **HG-3, HG-4 FAIL**. An assertion written `>= 2` would let this through, which is why the assertion standard above forbids `>=` |
| R-4 | Putting the batch loop and the target-status allow-list in the route, because the route already has the request schema | **FM-1** | `lint-imports` (`routes-never-import-repositories`), `tests/test_architecture.py::test_routes_never_import_a_repository`, and Evaluator review of the route body → **HG-5 FAIL** |
| R-5 | Adding the endpoint without updating `EXPECTED_ENDPOINTS`, or updating it while the Generator's allowed scope excludes `tests/test_main.py` | all four, via a red gate | `pytest` — `test_exactly_the_nine_required_rest_endpoints_are_routed` fails → **HG-7 FAIL**. **The Generator's allowed scope for this sprint must include `tests/test_main.py`** |
| R-6 | Asserting only `response.status_code == 207` for AC-2, which is the single easiest way to make this whole sprint look done while verifying nothing | **FM-3** | Evaluator opens each named test and looks for the four assertions → **HG-3 FAIL** |
| R-7 | Coverage drifting below the 80% floor because the all-fail and empty-list branches are implemented but not exercised | — | `pytest --cov`, `fail_under = 80` → **HG-7 FAIL**. Baseline is 99.63%; a material drop needs justification, not silence |

---

## Exclusions

**The Evaluator must NOT record any of these as a gap or a finding.** They are deliberate.

1. **No bulk reassignment.** `assignee_id` is untouched by this endpoint.
2. **No bulk transition to `TODO` or `IN_PROGRESS`.** Rejected at 422 by design (AC-4).
3. **No `SHIFT_HANDOVER` notification.** `AlertType.SHIFT_HANDOVER` stays unused. `alerts` already
   raises an `ESCALATION` for each `BLOCKED` transition through the existing subscriber; that
   behaviour is unchanged and is **not** a new side effect of this sprint.
4. **No new event type.** `ACTIVITY_STATUS_CHANGED` is reused. The audit surface does not change.
5. **No de-duplication of repeated task ids** (A-4).
6. **No batch-size limit, no pagination, no partial-result streaming.**
7. **No atomicity or rollback.** A partial batch leaves successful writes in place (A-7).
8. **No authorisation check** on who may perform a handover. StoreOps has `AuthToken` and
   `StaffRole` but no route-level authorisation anywhere; introducing it here would be the first
   instance and belongs in its own sprint.
9. **No change to `app/reports/`.** Its `store-101` summary will differ after a handover because
   the task state it reads changed. That is Rule 5 working, not a modification.
10. **No persisted handover `Report`.**

---

## Definition of done

- [ ] Every AC has an implementation reference and a named passing test
- [ ] `mypy . && ruff check . && lint-imports && pytest --cov` green with pasted output
- [ ] Coverage ≥ 80%
- [ ] No new `lint-imports` contract broken
- [ ] `generator-summary.md` written to schema
- [ ] `tests/test_main.py::EXPECTED_ENDPOINTS` updated to 10 endpoints (D-7)
- [ ] Exactly one module written to: `app/activities/`

---
STATUS: APPROVED
