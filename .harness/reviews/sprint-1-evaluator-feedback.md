# Evaluator Feedback — Sprint 1, Iteration 1

**Sprint ID:** sprint-1
**Contract:** `.harness/output/sprint-1-contract.md`
**Generator summary:** `.harness/output/generator-summary.md`
**Iteration:** 1 of max 3
**Contract status verified:** STATUS: APPROVED (final line, read directly — `tail -1`)
**Exclusions acknowledged:** 10 — no bulk reassignment; no bulk transition to `TODO`/`IN_PROGRESS`;
no `SHIFT_HANDOVER` notification; no new event type; no de-duplication of repeated ids; no
batch-size limit/pagination/streaming; no atomicity or rollback; no authorisation check; no change
to `app/reports/`; no persisted handover `Report`.
**These are NOT reported as gaps.** Read before reviewing anything, per `how-to-review` §1.

Gates evaluated: **HG-1…HG-8**. The invocation prompt said HG-1…HG-7; `evaluation-criteria` §2
defines eight, and HG-8 (every AC has an accurate `file:line` and a named passing test) is the gate
that makes contract fidelity deterministic. Omitting it would have skipped the only check that
opens the Generator's claims. All eight were evaluated.

## Hard gate results

| Gate | → FM | Result | Evidence |
|---|---|---|---|
| **HG-1** zero cross-module repository imports | FM-1 | **PASS** | `lint-imports`: 5 `*-no-cross-module-repository` contracts KEPT, 8/8 overall. Every import in `app/activities/*.py` enumerated by hand: stdlib, `pydantic`, own module, `app.shared` only — no sibling module referenced anywhere |
| **HG-2** typed `AppError` contract | FM-2 | **PASS** | `ruff` clean (`TRY002`/`TRY301`/`BLE001`). Repo-wide grep for `raise Exception`/`ValueError`/`RuntimeError`/`KeyError`/`TypeError`/`HTTPException`/`except Exception`/bare `except`/`raise AppError(` across `app/` → **zero matches**. `tests/test_architecture.py::test_services_raise_no_bare_exceptions` passes. The single `except` in the diff is `service.py:166 except AppError as exc:` — the permitted bulk-aggregator form |
| **HG-3** business-rule test quality | FM-3 | **PASS** | All 6 contract-named tests opened and parsed. Each asserts resulting state, `.code`, event count and audit count where applicable; **no test asserts a status alone** (minimum 8 assertions each). Coverage 99.66% ≥ 80% |
| **HG-4** event-bus integration | FM-4 | **PASS** | Publish path read top to bottom. `bulk_update_status` contains **no `publish` call of its own** — it delegates to `update_status`, where `replace` is `service.py:117` and `publish` is `:118`, in that order. Both request-level raises (`:149`, `:155`) precede the loop at `:163`, so no failure path can publish. `audit_sink` is never referenced in `app/activities/` |
| **HG-5** layer separation | FM-1, FM-4 | **PASS** | `routes-never-import-repositories` KEPT, `module-layers` KEPT, `tests/test_architecture.py::test_routes_never_import_a_repository` passes. `routes.py:63-67` body is 3 statements: delegate, select status code, return. No branch on domain state |
| **HG-6** read-only reports | FM-1, FM-4 | **PASS** | `reports-reads-only-via-services` KEPT; `app/reports/` absent from the diff (`git diff 12ebdb4 --name-only` = 4 files, none under `app/reports/`); `tests/reports/test_reports_read_only.py` passes |
| **HG-7** deterministic suite | all four | **PASS** | Exit 0. Output pasted below, from this invocation |
| **HG-8** every AC has `file:line` + named passing test | FM-3 | **PASS** | 6/6 ACs. All 7 implementation `file:line` claims opened and confirmed; all 6 named tests exist and appear in the passing run |

**Gate summary: 8 of 8 passed.** Scoring performed.

## Command output

Real, pasted, from this invocation. Counts cross-checked against the summary — `mypy` 55 files,
`pytest` 168 tests, coverage 99.66%, `lint-imports` 8/8 all match, so the summary's paste is not
stale.

    $ mypy .
    Success: no issues found in 55 source files

    $ ruff check .
    All checks passed!

    $ lint-imports
    Analyzed 33 files, 59 dependencies.
    -----------------------------------
    activities must not import a sibling module's repository KEPT
    programmes must not import a sibling module's repository KEPT
    staff must not import a sibling module's repository KEPT
    alerts must not import a sibling module's repository KEPT
    reports must aggregate via sibling services, never sibling repositories KEPT
    routes must never import any repository (no layer skipping) KEPT
    Routes -> Service -> Repository ordering inside every StoreOps module KEPT
    app.shared must not depend on any business module KEPT

    Contracts: 8 kept, 0 broken.

    $ pytest --cov
    TOTAL                            814      2     56      1    99%
    Required test coverage of 80.0% reached. Total coverage: 99.66%
    168 passed, 1 warning in 2.83s

The 2 uncovered statements are `app/alerts/repository.py:67` and `app/reports/repository.py:64` —
both present at the Phase 1 baseline. **No new uncovered code was introduced.**

## Weighted score

| Dimension | Weight | Checks passed | Contribution |
|---|---:|---|---:|
| D1 Architecture Compliance | 35% | 6/6 | 35.00 |
| D2 Test Quality & Business-Rule Coverage | 25% | 6/6 | 25.00 |
| D3 Error Contract Integrity | 15% | 5/5 | 15.00 |
| D4 Contract Fidelity | 15% | 5/5 | 15.00 |
| D5 Toolchain Cleanliness | 10% | 4/4 | 10.00 |
| **TOTAL** | **100%** | **26/26** | **100.00** |

    D1  35 × 6/6 = 35.00
    D2  25 × 6/6 = 25.00
    D3  15 × 5/5 = 15.00
    D4  15 × 5/5 = 15.00
    D5  10 × 4/4 = 10.00
                   ------
           score = 100.00

Failed checks: **none**. Per-check evidence:

- **D1:** 1.1–1.4, 1.6 from the `lint-imports` report above. 1.5 by reading the publish path and
  confirming no sibling *service* is called either — the write-by-call breach `lint-imports` cannot
  see. Only `activities_service` appears in `app/activities/`.
- **D2:** 2.1 six named tests resolve; 2.2 all six in the passing run; 2.3 state read back via
  `GET /api/tasks/{id}` rather than inferred from the response body; 2.4 `.code` asserted on every
  error path; 2.5 **no `>=` appears in any assertion** in the new file (the only `>=` occurrences
  are in the module docstring explaining why it is banned); 2.6 99.66% ≥ 80% and above the 99.63%
  baseline.
- **D3:** 3.1–3.4 from the repo-wide grep and the AST test. 3.5 vacuous — no new `AppError`
  subclass was added, consistent with contract A-6.
- **D4:** 4.1 six of six `yes`; 4.2 all claimed references opened and accurate; 4.3 the contract
  still holds 6 AC blocks and 6 named tests and its status line is unchanged; 4.4 the diff is 4
  modified files plus 1 new test file, every one inside `app/activities/**` or `tests/**`; 4.5 no
  exclusion was built and none of the 4 Known-gaps items is an exclusion.
- **D5:** 5.1 55 files — plausible for the diff (54 at baseline plus one new test module);
  5.2, 5.3 as above; 5.4 `fail_under = 80` unchanged at `pyproject.toml:109`, no `.importlinter`
  contract added or removed, and `git diff 12ebdb4 -- app tests` contains **no** added line
  matching `noqa` or `type: ignore`.

## AC results

| AC | Implemented | `file:line` verified | Named test | Test passes | Asserts state / code / events / audit | Result |
|---|---|---|---|---|---|---|
| AC-1 | yes | `service.py:163` ✓ `routes.py:64` ✓ | `::test_all_success_publishes_one_event_per_task` | yes | y / n-a / y (== 2) / y (== 2) | **PASS** |
| AC-2 | yes | `service.py:166` ✓ | `::test_partial_failure_returns_207_and_updates_only_valid_tasks` | yes | y / y / y (== 2) / y (== 2) | **PASS** |
| AC-3 | yes | `service.py:113` ✓ | `::test_done_task_in_batch_yields_invalid_status_transition_and_no_event` | yes | y / y / y (== 1) / y (== 1) | **PASS** |
| AC-4 | yes | `service.py:153` ✓ | `::test_target_status_outside_done_or_blocked_is_rejected_before_any_write` | yes | y / y / y (== 0) / y (== 0) | **PASS** |
| AC-5 | yes | `service.py:166` ✓ | `::test_all_items_failing_publishes_no_event_and_writes_no_audit_entry` | yes | y / y / y (== 0) / y (== 0) | **PASS** |
| AC-6 | yes | `service.py:148` ✓ | `::test_empty_task_id_list_is_rejected_with_422_and_no_events` | yes | n-a / y / y (== 0) / y (== 0) | **PASS** |

The two `n-a` cells are legitimate and were honestly declared as `n/a` in the summary rather than
claimed as `yes`: AC-1 has no failure path so there is no `.code` to assert, and AC-6 names no task
so there is no state to read back. A false `yes` in either cell would have been a high-severity
finding in its own right; there is none.

## Architecture rule compliance

| Rule | Result | Evidence |
|---|---|---|
| Module boundary | **PASS** | no sibling repository or service imported; `lint-imports` 8/8 |
| Event bus only | **PASS** | one `ACTIVITY_STATUS_CHANGED` per *successful* update, published at `service.py:118` after the write at `:117`; the aggregator adds no publish of its own |
| Error contract | **PASS** | reuses three existing subclasses; no new code; zero prohibited raise patterns repo-wide |
| Layer separation | **PASS** | route body is 3 statements delegating to the service; no repository import |
| Read-only reports | **PASS** | not engaged — `app/reports/` untouched by this diff |

## Test evidence

| Named test | Exists | Passes | State | `.code` | Event count | Audit count |
|---|---|---|---|---|---|---|
| `::test_all_success_publishes_one_event_per_task` | yes | yes | `:49-50` GET read-back | n/a | `== 2` at `:54` | `== 2` at `:58` |
| `::test_partial_failure_returns_207_and_updates_only_valid_tasks` | yes | yes | `:86-88` | `TASK_NOT_FOUND` `:80` | `== 2` at `:92` | `== 2` at `:94` |
| `::test_done_task_in_batch_yields_invalid_status_transition_and_no_event` | yes | yes | `:122-124` incl. `updated_at` | `INVALID_STATUS_TRANSITION` `:117` | `== 1` at `:128` | `== 1` at `:130` |
| `::test_target_status_outside_done_or_blocked_is_rejected_before_any_write` | yes | yes | `:152-153` | `VALIDATION_ERROR` `:145` | `== 0` at `:156` | `== 0` at `:157` |
| `::test_all_items_failing_publishes_no_event_and_writes_no_audit_entry` | yes | yes | `:204-205` | both codes `:198-201` | `== 0` at `:208` | `== 0` at `:209` |
| `::test_empty_task_id_list_is_rejected_with_422_and_no_events` | yes | yes | n/a | `VALIDATION_ERROR` `:220` | `== 0` at `:229` | `== 0` at `:230` |

Verified by opening `tests/activities/test_activities_bulk_status.py` and locating each named
construct at the stated line — not by reading the summary's table. One supplementary test beyond
the contract's mapping, `::test_non_handover_target_raises_validation_error_below_http` (`:161`),
asserts AC-4's rule against an **isolated** bus where "zero events" is a real guarantee rather than
a consequence of `reset_state` having cleared a shared log. That is stronger than the contract
required and is noted, not penalised.

## Findings

    [MINOR] .harness/skills/app-context/SKILL.md:72 — references
    `tests/test_main.py::test_exactly_the_nine_required_rest_endpoints_are_routed`, a test that
    no longer exists: it was renamed to `test_exactly_the_expected_rest_endpoints_are_routed`
    (`tests/test_main.py:49`). Section 3's heading also still reads "The 9 REST endpoints" and
    its table lists 9, but the application now routes 10.
    Rule violated: none. Gate: none — no gate or dimension check covers skill-file accuracy.
    Remediation: update `app-context` section 3 to 10 endpoints, add the
    `PATCH /api/activities/bulk-status` row, and correct the test name at line 72. Out of the
    Generator's allowed scope and out of mine; it is a post-sprint skill-file edit.
    Evidence: repo-wide grep for both test names; only `tests/test_main.py:49` defines one, and
    only the new name.

    [MINOR] .harness/skills/component-patterns/SKILL.md section 6 and
    .harness/skills/how-to-test/SKILL.md section 4 — both show the bulk response as
    `succeeded`/`failed` arrays, and how-to-test's worked example asserts `body["succeeded"]`.
    The approved contract specifies `updated`/`failed`/`results` with per-item `taskId`,
    `outcome`, `status`, `error`.
    Rule violated: none. Gate: none.
    Remediation: align both skill examples to the contract's shape.
    Evidence: contract "Request and response shape" versus the two skill sections. The
    Generator implemented the contract, which is correct per generator.agent.md section 2, and
    disclosed the divergence in Known gaps note 2.

    [MINOR] .harness/skills/component-patterns/SKILL.md section 6 — the status-code example
    reads `207 if (result.failed and result.succeeded) else 200`, returning **200** when every
    item fails. Contract A-2 requires **207** for an all-fail batch and AC-5 asserts it.
    Rule violated: none. Gate: none.
    Remediation: correct the example to `207 if result.failed else 200`.
    Evidence: contract A-2 and AC-5 versus the skill example; implementation at
    `app/activities/routes.py:64` follows the contract. Disclosed in Known gaps note 3.

BLOCKING = a hard gate failed. MAJOR = a dimension check failed. MINOR = no check failed.
**Three MINOR findings, zero BLOCKING, zero MAJOR.**

## Required remediation

None blocking. Nothing in `app/**` or `tests/**` requires change for this sprint to be accepted.

Carried forward as non-blocking conditions, all three being **skill-file** corrections outside both
the Generator's and the Evaluator's scope:

1. `app-context` §3 and `:72` — endpoint count 9 → 10 and the renamed test (finding 1).
2. `component-patterns` §6 and `how-to-test` §4 — bulk response shape (finding 2).
3. `component-patterns` §6 — all-fail status code (finding 3).

## Self-declaration spot-check

Every claim in the summary's Tests-added table with a `yes` in the event-count or audit-count
column was opened, per `how-to-review` §4. That is all 7 rows.

| Summary claim | Verified? | Note |
|---|---|---|
| AC-1 test asserts event count `== 2`, audit `== 2` | yes | `:54`, `:58` — `==`, not `>=` |
| AC-2 test asserts event count `== 2`, audit `== 2` | yes | `:92`, `:94` |
| AC-3 test asserts event count `== 1`, audit `== 1` | yes | `:128`, `:130` |
| AC-4 test asserts event count `== 0`, audit `== 0` | yes | `:156`, `:157` |
| Below-HTTP test asserts 0 on an isolated bus | yes | `:175`, `:176` — `activities.bus`/`activities.audit`, genuinely isolated |
| AC-5 test asserts event count `== 0`, audit `== 0` | yes | `:208`, `:209` |
| AC-6 test asserts event count `== 0`, audit `== 0` | yes | `:229`, `:230` |
| All 7 implementation `file:line` references | yes | each opened; the named construct is on the stated line |
| `mypy` 55 files / `pytest` 168 / coverage 99.66% / 8-of-8 | yes | identical to my own run — not a stale paste |
| "No `>=` appears anywhere in the file" | yes | the only `>=` occurrences are in the docstring explaining the ban |
| "`app/main.py` was not modified" | yes | absent from `git diff 12ebdb4 --name-only` |
| "no gate weakened" | yes | `fail_under = 80` intact; no added `noqa`/`type: ignore` |

**Zero false declarations.** The summary also discloses that the Generator found and corrected six
of its own inaccurate `file:line` references before submitting; I verified the *corrected* values
independently and they hold. Self-disclosure of a corrected error is the behaviour this harness
depends on to be affordable, and it is recorded here as such.

---
VERDICT: PASS

## Rationale

All eight hard gates passed with the output above, and the score is 100.00 because all 26 binary
checks passed — most notably 2.5, since every side-effect assertion uses `==` with an exact count
including zero on the three failure paths, which is the specific defect contract R-3 predicted and
AC-5 exists to catch. The strongest evidence is structural rather than statistical: the bulk
aggregator publishes nothing itself and delegates per item to `update_status`, so "one event per
*successful* update" is inherited from the single-item path rather than reimplemented where it
could diverge.

**A 100.00 does not mean nothing needs fixing, and stating otherwise would be the leniency this
role exists to prevent.** Three MINOR findings stand, and all three are defects in the *skill
files* rather than the code — including one, finding 1, where a legitimate test rename left
`app-context` pointing at a test that no longer exists and still claiming 9 endpoints. That file is
read by all four agents on every iteration, so the next Generator would inherit a stale fact.

That gap is in the **instrument**, and it is worth recording plainly: the 26 checks measure code
against contract, and nothing in them covers documentation or skill-file consistency after a
rename. A real defect therefore scored zero deduction. The compensating control worked anyway —
the Generator disclosed two of the three divergences itself, and the third surfaced from reading
the diff for orphaned references, which `how-to-review` §3 requires and no tool performs. A
candidate refinement is a D4 check 4.6, "no skill file or contract references a symbol the diff
renamed or removed", which would have caught finding 1 automatically.

## Statement

No code, test or configuration file was modified by this evaluation. Three findings were recorded
that I could have fixed in under two minutes; per `evaluator.agent.md` §1 the impulse to fix is the
finding, and repairing them here would have removed them from the audit trail where the Monitor
needs to see them.
