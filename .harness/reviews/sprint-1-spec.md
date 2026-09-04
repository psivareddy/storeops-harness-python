# Specification: Shift handover bulk update

## Originating prompt

> Shift handover bulk update — PATCH /api/activities/bulk-status marking multiple
> activities DONE or BLOCKED in one request, with partial-failure handling, one event per
> successful update, and one audit entry per updated task.

Source: `PROMPT.md` §3

## Problem

At shift change, an outgoing department lead at `store-101` has a handful of operational
activities to close out — a restocking run finished, a planogram reset stuck behind a delivery.
Today the only write path is `PATCH /api/tasks/{task_id}/status`, one request per activity. A
lead with six activities makes six calls, each of which can fail independently, and there is no
single response telling them which ones landed. The practical cost is that handover is done
badly or not at all: activities are left in `IN_PROGRESS` overnight, so the incoming shift
cannot tell what is genuinely outstanding, and `store-101`'s overdue count in
`GET /api/reports/store/store-101` overstates the real backlog.

This sprint gives the lead one request that closes out many activities and reports honestly, per
item, what happened.

## Why this decomposition

**One sprint.** Per [sprint-decomposition](../skills/sprint-decomposition/SKILL.md) §1 this fits
inside a single reviewable unit on every measure: one endpoint added, one module written
(`activities`), **no new event type** — it reuses `ACTIVITY_STATUS_CHANGED` — and six acceptance
criteria.

More importantly, the boundaries §1 tells us *not* to cut on are the ones that matter here:

- **The failure paths cannot be deferred.** Partial failure *is* the feature. A sprint 1 that
  implemented the all-success path and left `TASK_NOT_FOUND` to sprint 2 would ship an endpoint
  whose behaviour under the condition it exists to handle is undefined.
- **The audit entry cannot be split from the event.** The audit entry *is* the published
  `ACTIVITY_STATUS_CHANGED` reaching `AuditSink` (Rule 2). One behaviour, not two.

The producer/consumer cut in §1 *is* applied: this sprint publishes. It does not touch
`AlertsService.handle_activity_status_changed`, which already reacts to `BLOCKED` and will now
fire once per blocked activity in a batch as an existing, unchanged consequence.

## Sprint breakdown

| Sprint | Scope | Endpoint(s) | Module written | Contract |
|---|---|---|---|---|
| sprint-1 | Bulk status transition to DONE or BLOCKED with per-item partial-failure reporting | `PATCH /api/activities/bulk-status` (new) | `app/activities/` | `sprint-1-contract.md` |

No sprint 2 is proposed. The enrichments a second sprint would carry — batch-size limits,
pagination of results, a `SHIFT_HANDOVER` notification, bulk reassignment — are listed under
[Out of scope](#out-of-scope-for-this-feature) and are not required for the feature to be
usable.

## Module impact map

| Module | Written | Read | Via |
|---|---|---|---|
| `activities` | **yes** | yes | own service and repository |
| `alerts` | no | no | reacts to `ACTIVITY_STATUS_CHANGED` via the existing subscriber wired in `app/main.py` — not called |
| `staff` | no | no | — |
| `programmes` | no | no | — |
| `reports` | no | no | its `store-101` summary changes as a consequence of task state, with no code change |
| `app/shared/` | no | yes | `events.py`, `errors.py`, `audit.py` — existing symbols only, no new `AppError` subclass |

Exactly one module is written to, so a boundary breach in this sprint is unambiguously
attributable.

## Architecture rules engaged

| Rule | How this feature engages it | Failure mode guarded |
|---|---|---|
| **1 Module boundary** | The batch touches only `activities`. No sibling repository is needed or permitted; `alerts` learns of blocked activities through the bus | FM-1 |
| **2 Event bus only** | One `ACTIVITY_STATUS_CHANGED` per **successful** item, published after the repository write. The audit entry is that event reaching `AuditSink` — never written directly | FM-4 |
| **3 Error contract** | Per-item failures are `TaskNotFoundError` and `InvalidStatusTransitionError`; request-level rejection is `ValidationError`. All three already exist — no new code is invented | FM-2 |
| **4 Layer separation** | The route validates the request schema and delegates. The batch rule — iterate, isolate each item's failure, aggregate — is service logic, so it stays reusable and testable below HTTP | FM-1, FM-4 |
| **5 Read-only reports** | Not engaged. `app/reports/` is untouched; its output changes only because the task state it reads changed | FM-1, FM-4 |

### The one novel construct this sprint introduces

Every other write path in StoreOps fails the whole request on the first error. This one must
**continue past a failed item**, which means the service catches `AppError` per item — the only
place in the codebase permitted to do so. That is a deliberate, contract-level decision, not an
implementation detail, because a `except Exception` in that position would silently convert
Rule 3 into nothing. The contract states the narrow form required.

## Endpoint path — a deviation the approver must confirm

The prompt and capstone PDF §3.4 both name the path `PATCH /api/activities/bulk-status`. The
`activities` module's existing router is `APIRouter(prefix="/api/tasks", ...)`
(`app/activities/routes.py:17`), so no existing router can host that path.

| Option | Result |
|---|---|
| Add to the existing router | path becomes `/api/tasks/bulk-status` — **contradicts the prompt and the PDF** |
| **Add a second router with `prefix="/api/activities"` inside `app/activities/routes.py`** | path is exactly `/api/activities/bulk-status`; module ownership and Rule 4 unchanged |

**Decision: the second router.** The PDF is source-of-truth priority 1 (`PROMPT.md` §1), and the
prompt states the path explicitly. Two routers in one module is a routing detail; a path that
does not match the approved feature request is a contract breach.

**Consequence the approver must accept:** the REST endpoint inventory goes from **9 to 10**, so
`tests/test_main.py::EXPECTED_ENDPOINTS` must gain `("PATCH", "/api/activities/bulk-status")`.
[app-context](../skills/app-context/SKILL.md) §3 states that test is deliberate, not incidental —
which makes it a required, in-scope edit rather than collateral damage. See the contract's
Dependencies and Risks.

## Out of scope for this feature

Feature-level exclusions, distinct from the sprint-level exclusions in the contract:

- **Bulk reassignment.** Changing `assignee_id` in the same call. Handover marks work finished or
  stuck; who picks it up next is a separate decision with a separate authorisation question.
- **Bulk transition to `TODO` or `IN_PROGRESS`.** Deliberately excluded from the target-status
  allow-list; reopening work is not handover.
- **A `SHIFT_HANDOVER` notification.** `AlertType.SHIFT_HANDOVER` exists and is unused. Emitting
  it would mean changing what `alerts` subscribes to, which is a consumer-side sprint under the
  producer/consumer cut.
- **Bulk create or bulk delete.** A different risk profile entirely.
- **Persisting a handover `Report`.** Would engage Rule 5 and needs its own contract.
