# Sprint 1 Run Log — Shift handover bulk update

**Append-only.** One entry per iteration, including every FAIL. A prior entry is never rewritten
or deleted; an entry that turns out to be wrong gets a *later* entry saying so. Editing history
destroys the only value this archive has.

Path note: written as `sprint-1-run-log.md` per `monitor.agent.md` §1 and `CLAUDE.md` §3, not the
`run-log.md` named in the invocation prompt — the per-sprint prefix is what lets a reviewer diff
sprint against sprint, which is the trend the drift-signal field depends on.

---

## Sprint 1 — Iteration 1 — PASS

| Field | Value |
|---|---|
| Sprint ID | sprint-1 |
| Feature | Shift handover bulk update — `PATCH /api/activities/bulk-status`, DONE or BLOCKED in one request, partial-failure handling, one event and one audit entry per successful update |
| Originating prompt | `PROMPT.md` §3 |
| Contract | `.harness/reviews/sprint-1-contract.md` |
| Iteration | 1 of max 3 |
| Started / completed | 2026-09-04 (single session; the harness cannot observe wall-clock timestamps, so the date is recorded and the times are `unknown` rather than guessed) |
| **Verdict** | **PASS** (transcribed verbatim from `evaluator-feedback.md:225`) |
| Weighted score | 100.00 |
| Escalation flag | **no** |
| Final disposition | advanced — no sprint 2 proposed; three non-blocking conditions carried forward |

### Hard gate results

| HG-1 | HG-2 | HG-3 | HG-4 | HG-5 | HG-6 | HG-7 | HG-8 |
|---|---|---|---|---|---|---|---|
| PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |

8 of 8 passed. The Evaluator evaluated HG-8 although the invocation prompt named only HG-1…HG-7,
recording the reason in its own document.

### Dimension scores

| D1 35% | D2 25% | D3 15% | D4 15% | D5 10% | Total |
|---|---|---|---|---|---|
| 35.00 (6/6) | 25.00 (6/6) | 15.00 (5/5) | 15.00 (5/5) | 10.00 (4/4) | **100.00** |

26 of 26 binary checks passed.

### Files changed

| Path | Created / modified |
|---|---|
| `app/activities/models.py` | modified — bulk schemas, `HANDOVER_TARGET_STATUSES`, `is_handover_target` |
| `app/activities/service.py` | modified — `bulk_update_status`, `_current_status` |
| `app/activities/routes.py` | modified — `bulk_router`, `bulk_update_task_status`, `router` now an aggregate |
| `tests/test_main.py` | modified — `EXPECTED_ENDPOINTS` 9 → 10, inventory test renamed |
| `tests/activities/test_activities_bulk_status.py` | created — 6 contract-named tests + 1 below-HTTP test |

`app/activities/repository.py` and `app/main.py` unchanged. No file outside
`app/activities/**` or `tests/**` touched.

### Commands executed

    mypy .              -> 55 source files, 0 errors
    ruff check .        -> All checks passed!
    lint-imports        -> 8 kept, 0 broken (33 files, 59 dependencies analysed)
    pytest --cov        -> 168 passed, 1 warning; total coverage 99.66%
    exit code           -> 0

Run independently by the Evaluator in its own invocation; counts matched the Generator's paste
(55 / 168 / 99.66% / 8-of-8), so the submitted output was not stale.

### Findings recorded

Transcribed from the Evaluator. Not reworded, not re-ranked, not added to.

| Severity | file:line | Rule | Gate |
|---|---|---|---|
| MINOR | `.harness/skills/app-context/SKILL.md:72` | none — stale reference to the renamed inventory test; §3 still states 9 endpoints, application routes 10 | none |
| MINOR | `.harness/skills/component-patterns/SKILL.md` §6 and `.harness/skills/how-to-test/SKILL.md` §4 | none — bulk response shown as `succeeded`/`failed` arrays; contract specifies `updated`/`failed`/`results` | none |
| MINOR | `.harness/skills/component-patterns/SKILL.md` §6 | none — status example returns 200 when every item fails; contract A-2 requires 207 | none |

Zero BLOCKING, zero MAJOR. All three are skill-file defects, not code defects. The Evaluator
recorded that it could have fixed all three in under two minutes and did not, because repairing
them would have removed them from this archive.

### Estimated token cost

| Invocation | Inputs counted | Est. tokens |
|---|---|---|
| Planner | 3 skills (37,962 B) + `planner.agent.md` (9,219 B) + `app/` inventory (~4,000 B) | ~12,800 |
| Generator | 6 skills (74,191 B) + `generator.agent.md` (10,552 B) + contract (16,036 B) + scoped source (~22,000 B) | ~30,700 |
| Evaluator | 3 skills (43,549 B) + `evaluator.agent.md` (9,696 B) + contract (16,036 B) + summary (11,671 B) + diff and tool output (~15,000 B) | ~24,000 |
| Monitor | feedback (17,461 B) + summary (11,671 B) + contract (16,036 B) + `monitor.agent.md` (8,929 B) + `app-context` (7,812 B) + prior logs (0 B) | ~15,100 |
| **Iteration total** | | **~82,600** |

Method: sum the bytes of the files each agent loads and divide by 4 (≈4 bytes per token for English
prose and Python). Stated as an estimate because the harness cannot observe real usage — an honest
approximation with its method disclosed is worth more than a precise-looking number whose
derivation is hidden. Used for *relative* comparison across iterations, which is what detects a
loop getting more expensive.

Observation for the cost record: the **Generator is the most expensive invocation at ~37% of the
iteration**, driven by reading six skill files totalling 74 KB. `app-context` (7,812 B) is loaded
by all four agents, so its length is paid four times — ~7,800 tokens per iteration for orientation
alone. That is the deliberate trade recorded in `CLAUDE.md` §5, and this is the first run with real
numbers behind it.

### Recurring failure patterns

`None observed` — this is iteration 1 and no gate failed.

### Quality trend

| Iteration | Verdict | Score | Gates failed | Findings |
|---|---|---|---|---|
| 1 | PASS | 100.00 | none | 3 MINOR |

First-pass PASS with no gate failure. For the reviewer reading this later: a run log showing only
successes cannot distinguish good generation from gates that never fire — so note that the gates
*did* fire twice before this entry, both times on the approval checkpoint, and both refusals are
recorded below under Approval-checkpoint events. Those are not Evaluator verdicts and so have no
iteration number, but they are the evidence the checkpoint is real rather than decorative.

### Skill file drift signal

**Three signals, on the first sprint. This is the field earning its place.**

No gate failed twice on the same rule, so by the letter of `monitor.agent.md` §3 this field would
read "No drift signal". Recording it anyway, because all three Evaluator findings name a skill file
directly and the Generator disclosed two of them unprompted — that is exactly the input this field
exists to collect, and waiting for a second occurrence would mean shipping a known-stale
`app-context` to the next sprint.

1. **`app-context` §3 and `:72`** — the endpoint count and the inventory-test name went stale the
   moment the sprint added a tenth endpoint. `app-context` is read by **all four agents on every
   iteration**, so a stale fact here propagates further than a defect in any other file.
   *Candidate refinement:* update §3 to 10 endpoints with the new row, correct the test name at
   `:72`, and add a standing note that adding an endpoint requires editing both.
2. **`component-patterns` §6 / `how-to-test` §4 bulk response shape** — both show
   `succeeded`/`failed` arrays; the approved contract specifies `updated`/`failed`/`results`.
   *Candidate refinement:* align both examples to the contract shape.
3. **`component-patterns` §6 status selection** — the example returns 200 when every item fails,
   which contract A-2 forbids and AC-5 asserts against.
   *Candidate refinement:* correct to `207 if result.failed else 200`.

**Why signals 2 and 3 did not cost an iteration:** the contract was more specific than the skill
files, and `generator.agent.md` §2 makes the contract the only source of what to build. Had the
Generator followed the skill examples instead, AC-5 would have failed on the status code and all
six ACs on the body shape — a genuine iteration-1 FAIL caused by a skill-file defect. The
precedence rule absorbed a defect the skills would otherwise have injected.

**A gap in the instrument, recorded for the record:** the Evaluator's 26 checks measure code
against contract and contain nothing about documentation or skill-file consistency, so finding 1 —
a real defect — produced zero deduction and a score of 100.00. The Evaluator proposed a D4 check
4.6, *"no skill file or contract references a symbol the diff renamed or removed"*, which would
have caught it automatically. Transcribed here as the Evaluator's proposal, not the Monitor's.

### Approval-checkpoint events

Recorded because they are governance evidence and no Evaluator verdict covers them. Neither is an
iteration.

| # | Contract final line as read | Generator action |
|---|---|---|
| 1 | `STATUS: AWAITING APPROVAL` | refused; wrote nothing |
| 2 | `STATUS: AAPPROVED` (human typo) | refused; wrote nothing |
| 3 | `STATUS: APPROVED` | proceeded |

Event 1 is the designed refusal. Event 2 was unplanned and more informative: the harness failed
closed on a malformed line rather than pattern-matching its way past it. The Generator also
recorded that a substring check for `STATUS: APPROVED` would have matched the contract's own
explanatory prose at `:11` and **proceeded against an unapproved contract** — the check must be
last-line equality, not a search. Carried as a follow-up against `planner.agent.md` and
`generator.agent.md`.

### Chain of evidence archived

| Artefact | Archived to |
|---|---|
| Sprint contract (approved) | `.harness/reviews/sprint-1-contract.md` |
| Generator summary | `.harness/reviews/sprint-1-generator-summary.md` |
| Evaluator feedback | `.harness/reviews/sprint-1-evaluator-feedback.md` |
| Specification | `.harness/reviews/sprint-1-spec.md` |
| This run log | `.harness/reviews/sprint-1-run-log.md` |

Resolves end to end: `PROMPT.md` → `spec.md` → `sprint-1-contract.md` →
`sprint-1-generator-summary.md` → `sprint-1-evaluator-feedback.md` → `sprint-1-run-log.md`.
`.harness/output/` is gitignored working state; `.harness/reviews/` is committed, which is what
makes this the permanent record rather than a scratch copy.

### Monitor statement

Verdict transcribed verbatim. No finding reinterpreted, reworded, re-ranked or added. No prior
entry edited — there were none. `app/` was not read by this invocation.
