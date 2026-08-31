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

_Recorded verbatim in Phase 5A when the Planner is invoked. The feature below is the planned
target; this section is updated with the exact prompt as issued._

**Planned feature — shift handover bulk update:**

```
@planner Add shift handover bulk update — PATCH /api/activities/bulk-status allowing outgoing
shift staff to mark multiple operational activities as DONE or BLOCKED in a single request, with
partial-failure handling returning HTTP 207, one domain event published per successful update,
and one audit entry written per updated task.
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
| 1 | StoreOps baseline (5 modules, 3 layers, AppError, event bus, audit sink) | pending |
| 2 | Planner agent + shared foundation skills | pending |
| 3A | Generator implementation skills | pending |
| 3B | Generator agent | pending |
| 4 | Evaluator, Monitor, evaluation framework | pending |
| 5A–5C | End-to-end demonstration run (plan → approve → generate → evaluate) | pending |
| 6 | Docker, CI, AWS deployment | pending |
| 7 | Design Brief, Reflection, repository self-check | pending |

---

## 5. Prompt evolution

_Completed in Phase 7 (PDF section 6.3): how the invocation prompt changed across the build and
what each change fixed._
