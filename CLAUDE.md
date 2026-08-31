# CLAUDE.md — StoreOps Development Harness Orchestrator

> **Status: Phase 0 skeleton.** Agent bodies and the evaluation framework are authored in
> Phases 2–4 and referenced here. Sections marked _(Phase N)_ are placeholders whose contracts
> are already binding — the agent files must conform to them, not the reverse.

This repository contains two separable concerns. Do not mix them.

| Concern | Location | What it is |
|---|---|---|
| **The harness** | `.harness/`, `CLAUDE.md` | A governance layer that orchestrates AI code generation |
| **The governed application** | `app/`, `tests/` | StoreOps — a retail store operations REST API |

The harness exists to prevent four specific failure modes observed in this client's prior
AI-assisted development experiment. Every rule, gate, and skill file below traces to one of them.

| ID | Failure mode | Primary control |
|---|---|---|
| **FM-1** | Direct imports from another module's repository, bypassing the service boundary | HG-1, HG-5 (`lint-imports`) |
| **FM-2** | Raw error throws bypassing the typed `AppError` hierarchy | HG-2 (`ruff` TRY/BLE + review) |
| **FM-3** | Tests asserting HTTP status codes without verifying business rules | HG-3 (`pytest --cov` + review) |
| **FM-4** | Missing event bus integration — state changes written directly to sibling repositories | HG-4, HG-6 (`lint-imports` + review) |

---

## 1. Entry prompt format

A developer starts a harness run with a single Planner invocation. This is the **only** manual
entry point:

```
@planner <feature description in one or two sentences>
```

Example:

```
@planner Add shift handover bulk update — PATCH /api/activities/bulk-status marking multiple
activities DONE or BLOCKED in one request, with partial-failure handling, one event per
successful update, and one audit entry per updated task.
```

The developer has exactly **two** active steps in a run:

1. Invoke the Planner with the feature prompt.
2. Review `.harness/output/sprint-N-contract.md` and change its final line to `STATUS: APPROVED`.

After step 2 the Generator/Evaluator loop runs autonomously until every sprint reaches `PASS`
(or `CONDITIONAL PASS`), or an escalation is written.

---

## 2. Agents

Four agents, each with a bounded, non-overlapping responsibility. **No agent may perform another
agent's role in the same invocation.** Separation of duties is the primary control: an agent that
both produces and accepts an artefact provides no governance.

| Agent | Definition file | Reads (skills) | Writes | Absolutely may not |
|---|---|---|---|---|
| **Planner** | `.harness/agents/planner.agent.md` _(Phase 2)_ | `app-context`, `architecture-principles`, `sprint-decomposition` | `.harness/output/spec.md`, `.harness/output/sprint-N-contract.md` | Write production code or tests |
| **Generator** | `.harness/agents/generator.agent.md` _(Phase 3B)_ | `app-context`, `architecture-principles`, `component-patterns`, `app-error-contract`, `event-bus-integration`, `how-to-test` | `app/**`, `tests/**`, `.harness/output/generator-summary.md` | Amend an approved AC; self-approve; issue a verdict |
| **Evaluator** | `.harness/agents/evaluator.agent.md` _(Phase 4)_ | `architecture-principles`, `how-to-review`, `evaluation-criteria` | `.harness/output/evaluator-feedback.md` | Repair code or edit a test |
| **Monitor** | `.harness/agents/monitor.agent.md` _(Phase 4)_ | `app-context` | `.harness/reviews/sprint-N-run-log.md` | Alter a verdict or reinterpret findings |

Skill files live in `.harness/skills/<name>/SKILL.md` and are **feedforward context**: an agent
reads its declared skills *before* acting, not as a review checklist afterwards.

---

## 3. Execution sequence

```
  developer: @planner <feature>
       |
       v
  [PLANNER] ---> .harness/output/spec.md
                 .harness/output/sprint-N-contract.md
                 ends with: STATUS: AWAITING APPROVAL
       |
       X  <=== HARD STOP. Generation is forbidden here.
       |
  developer edits the contract's final line to: STATUS: APPROVED
       |
       v
  +--> [GENERATOR] ---> app/**, tests/**, generator-summary.md
  |         |
  |         v
  |    [EVALUATOR] ---> evaluator-feedback.md, containing "VERDICT: ..."
  |         |
  |         v
  |    [MONITOR]   ---> .harness/reviews/sprint-N-run-log.md   (runs on EVERY verdict)
  |         |
  |    read VERDICT and route (section 4)
  |         |
  +---------+  FAIL and iteration < 3: findings only, back to Generator
            |
            +-> PASS / CONDITIONAL PASS: archive, advance to next sprint
            +-> FAIL at iteration 3: write .harness/output/escalation.md, STOP
```

### The approval checkpoint

`STATUS: AWAITING APPROVAL` is a blocking gate, not a formality.

- The Generator's **first action** is to read the contract's status line.
- If it does not read exactly `STATUS: APPROVED`, the Generator stops immediately and reports
  that the approval checkpoint is not satisfied. It writes nothing.
- Only a human may change the status line. No agent may edit it — the Planner because it would
  be self-approving its own contract, the Generator because it would be authorising its own work.

---

## 4. Verdict routing

The Evaluator emits exactly one machine-readable line in `evaluator-feedback.md`:

```
VERDICT: PASS
VERDICT: CONDITIONAL PASS
VERDICT: FAIL
```

The orchestrator routes on that marker alone — never on prose, tone, or the numeric score.

| Verdict | Iteration | Action |
|---|---|---|
| `PASS` | any | Archive artefacts to `.harness/reviews/`, run Monitor, advance to the next sprint |
| `CONDITIONAL PASS` | any | Archive, run Monitor, log outstanding conditions, advance; conditions carry into the next sprint contract |
| `FAIL` | 1 or 2 | Return **findings only** to the Generator, increment the iteration counter, re-invoke Generator |
| `FAIL` | 3 | Do **not** regenerate. Write `.harness/output/escalation.md` and stop |

**Two invariants that hold regardless of anything else:**

1. A failed hard gate produces `FAIL`. The weighted score can never override it. A boundary
   breach at 95% quality is still a boundary breach.
2. If the Evaluator's own assessment is ambiguous on any check, it resolves toward `FAIL` and
   states the ambiguity. The harness **fails closed** — an uncertain accept is worse than an
   unnecessary retry, because the retry costs tokens and the accept costs production defects.

### Iteration bound and escalation

**Maximum three Generator/Evaluator iterations per sprint.** The bound exists because a third
consecutive failure is evidence the *contract or the skill files* are defective, not the
generated code — and further iterations would burn tokens re-deriving the same wrong answer.

On the third `FAIL`, write `.harness/output/escalation.md` containing:

| Field | Content |
|---|---|
| Sprint ID | e.g. `sprint-1` |
| Feature | The originating prompt from `PROMPT.md` |
| Iterations used | `3` |
| Blocking issue | The specific defect, with `file:line` |
| Hard gate failed | e.g. `HG-1 — cross-module repository import` |
| Failure mode | The FM the gate maps to |
| What was tried | One line per iteration |
| Recipient | The developer who approved the sprint contract |
| Recommended action | Amend the contract, refine a named skill file, or accept a scope reduction |

An escalation is a **successful harness outcome**, not a harness failure. Detecting that a
feature cannot be safely generated under the current standards is exactly what the governance
layer is for.

---

## 5. Context scoping and reset strategy

Long runs degrade when every agent inherits every prior agent's context. Each invocation is
therefore scoped to the minimum it needs, and handoffs happen through **files on disk**, not
through conversation history.

| Agent | Loads | Deliberately does not load |
|---|---|---|
| Planner | Skills (3), `app/` module/route inventory, `PROMPT.md` | Implementation bodies, prior sprints' feedback |
| Generator | Skills (6), the approved contract, only the modules in its allowed scope | `spec.md` narrative, Evaluator internals, other modules' bodies |
| Evaluator | Skills (3), the contract, `generator-summary.md`, the diff, real tool output | The Generator's reasoning or conversation history |
| Monitor | `evaluator-feedback.md`, `generator-summary.md`, prior run-logs | `app/` source entirely |

**Reset rules**

1. **One agent per invocation.** Fresh context each time; the file handoff is the interface.
2. **Reset between sprints.** No sprint inherits another's context; the sprint contract is the
   complete input.
3. **On a FAIL retry, pass findings only** — not the full previous feedback document. The
   Generator needs the defects, not the Evaluator's reasoning about them.
4. **Skills are re-read, never remembered.** An agent that "recalls" a rule instead of reading
   it is running on a stale copy.

**Cost-awareness (depth vs. token budget).** Skill file depth is deliberately uneven:
`app-context` is short because it is orientation loaded by all four agents, so every extra line
is paid four times per iteration. `architecture-principles` and `evaluation-criteria` are the
longest because they are the files whose ambiguity directly causes retries — and one avoided
retry costs less than the tokens saved by trimming them.

---

## 6. CI/CD relationship

The harness gate **precedes and feeds into** CI. It does not replace it.

```
Harness (local, pre-commit)              CI (.github/workflows/ci.yml, post-push)
  Evaluator runs HG-1..HG-8       ->       same 4 commands re-run on neutral infrastructure
  verdict blocks the commit                pipeline blocks the merge
```

The deterministic suite is identical in both places, deliberately:

```
mypy . && ruff check . && lint-imports && pytest --cov
```

- **The harness catches defects before they are committed** — cheaper, and the feedback reaches
  the Generator while the context is still live.
- **CI is the trust boundary** — it re-runs the same gate on a clean checkout, so a passing
  harness verdict on a developer's machine cannot be taken on faith.
- **CI is authoritative on disagreement.** If the harness passes and CI fails, CI is right and
  the harness has an environment-dependence bug worth logging in `REFLECTION.md`.

**File separation.** `.github/` contains CI/CD workflows **only**. No agent definitions, no
skill files, no run artefacts. `.harness/` contains the governance layer. Mixing them would make
the harness look like pipeline configuration and invite it to be bypassed with a `[skip ci]`.

---

## 7. Repository layout

| Path | Purpose | Committed? |
|---|---|---|
| `CLAUDE.md` | This file — the orchestrator | yes |
| `PROMPT.md` | The demonstration feature prompt + source-of-truth order | yes |
| `DESIGN_BRIEF.md` | Harness Design Brief _(Phase 7)_ | yes |
| `REFLECTION.md` | Post-run reflection _(Phase 7)_ | yes |
| `JOURNAL.md` | Architecture journal, appended every phase | yes |
| `DEPLOYMENT.md` | Deployment target, steps, evidence _(Phase 6)_ | yes |
| `.harness/agents/` | Four `*.agent.md` definitions | yes |
| `.harness/skills/` | `<name>/SKILL.md` feedforward guides | yes |
| `.harness/output/` | In-flight run state | **no** — gitignored |
| `.harness/reviews/` | Governance audit trail, one set per sprint | **yes** — permanent record |
| `app/` | StoreOps source: 5 modules + `shared/` | yes |
| `tests/` | Tests mirroring `app/` | yes |

> **Documented deviation from capstone PDF section 7.** The PDF's repo-structure table names
> `src/` for application code, but PDF section 2.3 step 4 gives the Python start command as
> `uvicorn app.main:app --reload`, which requires a top-level `app` package. Section 7's table is
> the generic cross-stack row; section 2.3 is the Python-specific instruction. This harness uses
> `app/`. Rationale recorded in `DESIGN_BRIEF.md` Section D and `JOURNAL.md`.

---

## 8. StoreOps architecture rules (enforced, not advisory)

Full detail in `.harness/skills/architecture-principles/SKILL.md` _(Phase 2)_.

| Rule | Constraint | Gate |
|---|---|---|
| **Module boundary** | No module imports another module's `repository`. Cross-module reads go through the target module's **service** layer | HG-1 |
| **Event bus only** | Cross-module side effects are raised via `app/shared/events.py`, never by direct service-to-service side-effect import | HG-4 |
| **Error contract** | No raw exceptions in services or routes. All errors are `AppError` subclasses carrying `code`, `message`, `statusCode` | HG-2 |
| **Layer separation** | Routes → Service → Repository, no skipping. Routes hold no business logic; repositories call no external services | HG-5 |
| **Read-only reports** | `app/reports` aggregates from activities, programmes and staff and never writes to them | HG-6 |

`app/shared/` holds technical capabilities only (error contract, event bus, audit sink, logging,
config). It must not acquire routes or domain rules — it is not a sixth business module.

---

## 9. Definition of done for a sprint

A sprint is complete when **all** of the following hold:

1. The contract read `STATUS: APPROVED` before any code was written.
2. Every AC has an implementation reference and a named passing test in `generator-summary.md`.
3. All eight hard gates pass with **real, pasted** command output — never summarised or asserted.
4. `mypy . && ruff check . && lint-imports && pytest --cov` is green.
5. The Evaluator issued exactly one `VERDICT:` line, with `file:line` findings.
6. The Monitor appended a run-log to `.harness/reviews/`.
7. The full chain of evidence resolves: `PROMPT.md` → `spec.md` → `sprint-N-contract.md` →
   `sprint-N-generator-summary.md` → `sprint-N-evaluator-feedback.md` → `sprint-N-run-log.md`.

**Never report a gate as passing without pasting its real output.** A fabricated green gate is
the single most damaging thing any agent in this harness can do: it converts a governance layer
into a rubber stamp.

---

## 10. Source-of-truth priority

On any conflict, resolve in this order:

1. `AI_Native_Architect_Build.pdf` — the authoritative capstone brief
2. `CLAUDE.md` — this file
3. `.harness/agents/*.agent.md`
4. `.harness/skills/*/SKILL.md`
5. Anything else, including `capstone_best_prompt_combined.md` (a working document, not a spec)
