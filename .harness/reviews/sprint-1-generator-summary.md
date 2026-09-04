# Generator Summary — Sprint 1, Iteration 1

**Sprint ID:** sprint-1
**Contract:** `.harness/output/sprint-1-contract.md`
**Contract status read:** STATUS: APPROVED
**Iteration:** 1 of max 3
**Allowed scope used:** `app/activities/models.py`, `app/activities/service.py`,
`app/activities/routes.py`, `tests/activities/test_activities_bulk_status.py`,
`tests/test_main.py`. Nothing in `app/shared/**` needed changing (no new `AppError` subclass —
contract A-6). **`app/main.py` was not modified** — see Known gaps note 1.

## AC self-check

| AC | Statement (abbrev.) | Implemented | Implementation `file:line` | Test | Result |
|---|---|---|---|---|---|
| AC-1 | all ids valid → 200, 2 events, 2 audit | yes | `app/activities/service.py:163` (loop), `app/activities/routes.py:64` (200 selection) | `tests/activities/test_activities_bulk_status.py::test_all_success_publishes_one_event_per_task` | PASS |
| AC-2 | one absent id → 207, `TASK_NOT_FOUND`, 2 events | yes | `app/activities/service.py:166` (per-item catch), `app/activities/routes.py:64` | `tests/activities/test_activities_bulk_status.py::test_partial_failure_returns_207_and_updates_only_valid_tasks` | PASS |
| AC-3 | `task-4` DONE → `INVALID_STATUS_TRANSITION`, 207, 1 event | yes | `app/activities/service.py:113` (existing rule, reused via `:165`) | `tests/activities/test_activities_bulk_status.py::test_done_task_in_batch_yields_invalid_status_transition_and_no_event` | PASS |
| AC-4 | target not DONE/BLOCKED → 422, 0 events | yes | `app/activities/service.py:153` | `tests/activities/test_activities_bulk_status.py::test_target_status_outside_done_or_blocked_is_rejected_before_any_write` | PASS |
| AC-5 | every item fails → 207, 0 events, 0 audit | yes | `app/activities/service.py:166` (no publish on the failure branch) | `tests/activities/test_activities_bulk_status.py::test_all_items_failing_publishes_no_event_and_writes_no_audit_entry` | PASS |
| AC-6 | empty list → 422, 0 events | yes | `app/activities/service.py:148` | `tests/activities/test_activities_bulk_status.py::test_empty_task_id_list_is_rejected_with_422_and_no_events` | PASS |

All six `Implemented` = `yes`. One supplementary test was added beyond the contract's mapping —
`test_non_handover_target_raises_validation_error_below_http` (`:161`), parametrised over `TODO`
and `IN_PROGRESS` — asserting AC-4's rule at the service layer against an isolated bus, per
contract A-3 ("the allow-list belongs in the service, not the route schema, so the rule stays
testable below HTTP").

## Files created

| Path | Layer | Purpose |
|---|---|---|
| `tests/activities/test_activities_bulk_status.py` | tests | the six contract-named AC tests + one below-HTTP test for AC-4 |

## Files modified

| Path | Layer | Change |
|---|---|---|
| `app/activities/models.py` | models | added `HANDOVER_TARGET_STATUSES` (`:93`), `is_handover_target` (`:98`), `BulkItemOutcome` (`:107`), `BulkStatusUpdate` (`:114`), `BulkStatusItemResult` (`:126`), `BulkStatusResult` (`:137`) |
| `app/activities/service.py` | service | added `bulk_update_status` (`:133`) and the private `_current_status` helper (`:195`) |
| `app/activities/routes.py` | routes | added `bulk_router` (`:25`) and `bulk_update_task_status` (`:56`); `router` (`:73`) is now an aggregate including both sub-routers |
| `tests/test_main.py` | tests | `EXPECTED_ENDPOINTS` gained `("PATCH", "/api/activities/bulk-status")` (`:25`); count assertion 9 → 10 (`:54`); test renamed `test_exactly_the_nine_...` → `test_exactly_the_expected_rest_endpoints_are_routed` (`:49`) |

`app/activities/repository.py` is **unchanged**, per `component-patterns` §6 step 2 — the bulk
operation loops over the existing `get()` and `replace()` and needs no `replace_many()`.

## Tests added

| Test | Asserts state | Asserts error code | Asserts event count | Asserts audit count |
|---|---|---|---|---|
| `::test_all_success_publishes_one_event_per_task` | yes (`:49-50`, read back via GET) | n/a (no failure path) | yes (`== 2`, `:54`) | yes (`== 2`, `:58`) |
| `::test_partial_failure_returns_207_and_updates_only_valid_tasks` | yes (`:86-88`) | yes (`TASK_NOT_FOUND`, `:80`) | yes (`== 2`, `:92`) | yes (`== 2`, `:94`) |
| `::test_done_task_in_batch_yields_invalid_status_transition_and_no_event` | yes (`:122-124`, incl. `updated_at` unchanged) | yes (`INVALID_STATUS_TRANSITION`, `:117`) | yes (`== 1`, `:128`) | yes (`== 1`, `:130`) |
| `::test_target_status_outside_done_or_blocked_is_rejected_before_any_write` | yes (`:152-153`) | yes (`VALIDATION_ERROR`, `:145`) | yes (`== 0`, `:156`) | yes (`== 0`, `:157`) |
| `::test_non_handover_target_raises_validation_error_below_http` | yes (`:174`) | yes (`VALIDATION_ERROR`, `:172`) | yes (`== 0`, `:175`, isolated bus) | yes (`== 0`, `:176`, isolated sink) |
| `::test_all_items_failing_publishes_no_event_and_writes_no_audit_entry` | yes (`:204-205`) | yes (both codes, `:198-201`) | yes (`== 0`, `:208`) | yes (`== 0`, `:209`) |
| `::test_empty_task_id_list_is_rejected_with_422_and_no_events` | n/a (no state to change) | yes (`VALIDATION_ERROR`, `:220`) | yes (`== 0`, `:229`) | yes (`== 0`, `:230`) |

Every count assertion uses `==` with an exact number. **No `>=` appears anywhere in the file** —
contract R-3 identifies `>=` as the assertion that would let a publish-per-requested-id
implementation through. No test asserts an HTTP status as its only assertion.

## Architecture rules touched

| Rule | How this sprint engages it | Compliance evidence |
|---|---|---|
| **Module boundary** | batch touches only `activities` | `lint-imports` 8 kept / 0 broken (below). `grep` for `app.alerts`/`app.staff`/`app.programmes`/`app.reports` across `app/activities/` returns nothing |
| **Event bus only** | one `ACTIVITY_STATUS_CHANGED` per successful update, published after the write | `bulk_update_status` contains **no `publish` call of its own**: it delegates to `update_status`, where `replace` is `service.py:117` and `publish` is `:118`. The ordering invariant is inherited, not restated — and so cannot be re-broken here. `audit_sink` is never referenced in `app/activities/` |
| **Error contract** | reuses `TaskNotFoundError`, `InvalidStatusTransitionError`, `ValidationError`; no new subclass | both request-level raises (`service.py:149`, `:155`) precede the loop at `:163`, so no publish can occur on a rejection. The one `except AppError` (`:166`) is the permitted bulk-aggregator form — not `except Exception` |
| **Layer separation** | route body is 3 lines: delegate, pick a status code, return | `routes.py:56-68`. No repository import; `ruff`, `lint-imports` and `tests/test_architecture.py::test_routes_never_import_a_repository` all pass |
| **Read-only reports** | not engaged — `app/reports/` untouched by this diff | no `app/reports/` path in Files modified |

## Events published or consumed

| Event | Published by | New? | Payload keys | Consumers affected |
|---|---|---|---|---|
| `ACTIVITY_STATUS_CHANGED` | `ActivitiesService.update_status` (`service.py:118`), reached per successful item from `bulk_update_status` | **no** — reused, per contract Exclusion 4 | `taskId`, `storeId`, `previousStatus`, `newStatus`, `priority`, `assigneeId` (unchanged) | `AuditSink` (already attached), `AlertsService.handle_activity_status_changed` (already subscribed) |

No new event type, so the audit surface is unchanged and `wire_event_handlers()` needed no edit.
A successful bulk transition to `BLOCKED` will raise one `ESCALATION` per blocked item through
the **existing** subscriber — contract Exclusion 3 states this is unchanged behaviour and not a
new side effect of this sprint.

## Known gaps

1. **`app/main.py` was outside the allowed scope, and a second router would normally be
   registered there.** Rather than write outside scope, `app/activities/routes.py:73` keeps the
   exported name `router` as an aggregate `APIRouter()` that includes `tasks_router` and
   `bulk_router`. `app/main.py:15` imports `router as activities_router`, so the new path is
   routed with **zero** change to the composition root and all four existing `/api/tasks` paths
   are byte-identical. Flagging it because it is a structural choice the contract did not
   specify, not because it is a gap in the ACs.
2. **The response shape in the contract differs from the shape in two skill files.** The
   contract (Request/response shape, and AC-1…AC-6) specifies `updated` / `failed` / `results`
   with per-item `taskId` / `outcome` / `status` / `error`. `component-patterns` §6 and
   `how-to-test` §4 both show `succeeded` / `failed` **arrays** instead, and `how-to-test`'s
   worked example asserts `body["succeeded"]`. **I implemented the contract**, per
   `generator.agent.md` §2 ("the contract is the only source of what to build"). Recording it as
   a skill-file drift signal for the Monitor. I may not edit `.harness/skills/**`.
3. **`component-patterns` §6's status-code example contradicts contract A-2.** It shows
   `207 if (result.failed and result.succeeded) else 200`, which returns **200** when every item
   fails. Contract A-2 requires **207** for an all-fail batch, and AC-5 asserts it. Implemented
   as `207 if result.failed else 200` (`routes.py:64`), following the contract. Second drift
   signal, same cause.
4. **Pre-existing test warning, not introduced here.** `pytest` reports one
   `StarletteDeprecationWarning` from `.venv/.../fastapi/testclient.py:1` ("Using `httpx` with
   `starlette.testclient` is deprecated"). Third-party, present at the Phase 1 baseline, and
   outside the allowed scope to address.

No acceptance criterion is unimplemented. Nothing in the contract's Exclusions list was built.

## Commands executed

Real, pasted, from this invocation, after the one `ruff --fix` pass described below.

    $ mypy .
    Success: no issues found in 55 source files

    $ ruff check .
    All checks passed!

    $ lint-imports
    Contracts: 8 kept, 0 broken.

    $ pytest --cov
    168 passed, 1 warning in 2.61s
    Required test coverage of 80.0% reached. Total coverage: 99.66%

    $ echo "GATE_EXIT=$?"
    GATE_EXIT=0

One intermediate failure, disclosed: the first `ruff check .` reported `I001` (unsorted imports)
at `app/activities/service.py:8` — `HANDOVER_TARGET_STATUSES` must precede the CamelCase names in
the `from app.activities.models import (...)` block. Fixed with `ruff check --fix .`, which is a
formatting correction inside the allowed scope, not a suppression. Re-ran the full gate
afterwards; the output above is the post-fix run.

## Validation results

| Check | Result | Evidence |
|---|---|---|
| `mypy .` | pass | 55 files (54 at baseline + the new test module), 0 errors |
| `ruff check .` | pass | 0 findings |
| `lint-imports` | pass | 8 kept, 0 broken — same 8 contracts, none added or removed |
| `pytest --cov` | pass | 168 passed (160 baseline + 8 new), 0 failed |
| Coverage ≥ 80% | pass | 99.66% — **above** the 99.63% baseline |
| Endpoint inventory updated | yes | `tests/test_main.py:25`, count assertion 9 → 10 at `:54` |
| Six contract-named tests exist and pass | yes | `pytest tests/activities/test_activities_bulk_status.py` → 8 passed (6 named + 2 parametrised cases of the below-HTTP test) |
| No gate weakened | yes | `fail_under` unchanged at 80; no `.importlinter` contract touched; no `# noqa` or `# type: ignore` added |

## Statement

No approved acceptance criterion was altered. No verdict is issued by this document.
