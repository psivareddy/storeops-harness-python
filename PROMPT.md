# PROMPT.md — Harness Invocation Record

This file records the prompts used to drive the harness, and the authority order used to resolve
conflicts between instruction sources. Required by capstone PDF sections 5.5 and 6.3.

---

## 1. Source-of-truth priority

When two instructions conflict, the higher entry wins. This order is binding on every agent.

| # | Source | Authority |
|---|---|---|
| 1 | `AI_Native_Architect_Build.pdf` | Authoritative capstone brief. Wins over everything, including this file. |
| 2 | `CLAUDE.md` | Orchestration contract: sequence, routing, iteration bound, scoping. |
| 3 | `.harness/agents/*.agent.md` | Per-agent responsibility and handoff schema. |
| 4 | `.harness/skills/*/SKILL.md` | Feedforward implementation and review rules. |
| 5 | An approved `sprint-N-contract.md` | Binding for that sprint; may not be amended by the Generator. |
| 6 | `capstone_best_prompt_combined.md` | Working document that shaped this build. **Not a specification.** |

### Recorded conflicts and their resolutions

| Conflict | Resolution | Authority |
|---|---|---|
| PDF section 7 names `src/` for application code; PDF section 2.3 step 4 gives the start command `uvicorn app.main:app --reload`, which requires `app/` | Use **`app/`**. Section 7's table is the generic cross-stack row (its sibling rows name Node/Java/.NET paths); section 2.3 is the Python-specific instruction. | PDF, internally reconciled |
| PDF section 5.2 prose says "Three agent definition files"; its own table lists **four** (including `monitor.agent.md`), and section 8.2 scores "Monitor and observability" separately at 2% | Build **four** agents. | PDF table + section 8.2 |
| `capstone_best_prompt_combined.md` instructs that the 90% rubric total be flagged `UNCONFIRMED` | **Resolved, not unconfirmed.** PDF section 8.1 lists `JOURNAL.md` as a **+10% bonus** and states "the maximum score without the optional architecture journal is 90%". The four required components total 90% by design. | PDF section 8.1 |
| Working document names skill files `storeops-boundaries`, `business-rule-testing` | Use the PDF's own vocabulary: `app-context`, `architecture-principles`, `sprint-decomposition`, `how-to-review`, `component-patterns`, `how-to-test`. | PDF sections 5.2, 5.3 |

---

## 2. Harness entry prompt format

Defined in `CLAUDE.md` section 1. A run begins with one Planner invocation:

```
@planner <feature description in one or two sentences>
```

The developer then reviews `.harness/output/sprint-N-contract.md` and sets its final line to
`STATUS: APPROVED`. Nothing is generated before that.

---

## 3. Demonstration feature prompt

**Final prompt, as actually issued to invoke the Planner (Phase 5A):**

```
Act as the Planner defined in .harness/agents/planner.agent.md.

Feature: Shift handover bulk update — PATCH /api/activities/bulk-status marking multiple
activities DONE or BLOCKED in one request, with partial-failure handling, one event per
successful update, and one audit entry per updated task.

Allowed scope: .harness/output/spec.md, .harness/output/sprint-1-contract.md
Protected scope: app/**, tests/**, .harness/agents/**, .harness/skills/**

Requirements: produce GIVEN/WHEN/THEN acceptance criteria covering the all-success path, the
partial-failure path returning HTTP 207, the invalid-target-state path, and the guarantee that a
failed item produces neither an event nor an audit entry. Map every AC to a named test.

End the contract with the literal line: STATUS: AWAITING APPROVAL

Write no production code. Stop after the contract.
```

Chosen from capstone PDF section 3.4's suggested features because it exercises all five
architecture rules and all four failure modes in a single sprint:

| Rule / failure mode | How this feature exercises it |
|---|---|
| Layer separation (HG-5) | Bulk logic must sit in the service, not the route |
| Module boundary (HG-1) | The audit entry tempts a direct write to a sibling repository |
| Event bus only (HG-4) | One event per successful update, none for failures |
| Error contract (HG-2) | Per-item `TASK_NOT_FOUND` / invalid-transition `AppError`s inside a 207 |
| Business-rule tests (HG-3) | HTTP 207 alone proves nothing — event and audit **counts** must be asserted |

---

## 4. Phase prompt log

The build was executed in eight phases. Each phase's prompt is recorded here as it is run.

| Phase | Objective | Status |
|---|---|---|
| 0 | Repository setup, toolchain, requirements register | complete |
| 1 | StoreOps baseline (5 modules, 3 layers, AppError, event bus, audit sink) | complete |
| 2 | Planner agent + shared foundation skills | complete |
| 3A | Generator implementation skills | complete |
| 3B | Generator agent | complete |
| 4 | Evaluator, Monitor, evaluation framework | complete |
| 5A | Plan — Planner invoked, contract written, `STATUS: AWAITING APPROVAL` | complete |
| 5B | Generate — refused twice at the approval checkpoint, then implemented the approved contract | complete |
| 5C | Evaluate + Monitor — `VERDICT: PASS`, 8/8 gates, 100.00, archived to `.harness/reviews/` | complete |
| 6 | Docker, CI, AWS deployment documentation | complete |
| 7 | Design Brief, Reflection, repository self-check | complete |

---

## 5. Prompt evolution

The invocation prompt changed twice across the build, both times before any code was written —
which is itself evidence the approval checkpoint is doing its job: a scope defect surfaced by
review, not by a failed gate.

| Change | What triggered it | What it fixed |
|---|---|---|
| Endpoint path resolved to `/api/activities/bulk-status`, not a path under the existing `/api/tasks` prefix | The Planner noticed, before approval, that `app/activities/routes.py`'s existing router is `APIRouter(prefix="/api/tasks")`, which cannot host the PDF §3.4 path | Recorded as contract assumption A-1 (a second `APIRouter` in the same module) rather than left for the Generator to improvise mid-sprint |
| Phase 5B's allowed scope widened to include `tests/test_main.py` | The endpoint inventory test (`EXPECTED_ENDPOINTS`) goes from 9 to 10 entries regardless of implementation choice, and the original scope excluded that file | Without the widening, the Generator would have had to choose between leaving the inventory test red (an automatic HG-7 FAIL) or writing outside its protected scope — a scope defect burning an iteration on a problem the contract review should have caught first |

Both changes were made to the **prompt and the contract**, never to the harness's agent or skill
files, and both were decided by a human before `STATUS: APPROVED` was written — consistent with
`CLAUDE.md` §2's rule that only a human may change the approval line.
