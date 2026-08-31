# Capstone Prompt — Unified Best Edition

Combined from `capstone_best_prompt_2.md` (compact structure + guardrails) and
`capstone_best_prompt.md` (coaching critique + techniques + exemplars + usage tips).
Target: **Cognizant AI-Native Architect Capstone — Build Track** (governance harness over StoreOps).

---

## A. Why This Prompt Works (coaching context — do not paste into Claude Code)

Gaps this prompt closes vs. a naive first draft:

1. **Correct framing** — deliverable is a *governance harness* (Planner → Generator → Evaluator → Monitor), not an autonomous agent app.
2. **StoreOps grounding** — skill files reference the real 5-module, 3-layer app, never generic principles.
3. **Traceability** — every hard gate maps to one of 4 failure modes and one of 5 architecture rules.
4. **Graded artefacts named** — `CLAUDE.md`, 4 agent files, ≥6 skill files, eval framework, `DESIGN_BRIEF.md`, `PROMPT.md`, `DEPLOYMENT.md`, `REFLECTION.md`.
5. **Named, weighted rubric** — GIVEN/WHEN/THEN ACs, hard gates, dimensions summing to 100%.
6. **Few-shot + chain-of-thought** — model AC and model hard-gate improve structured fidelity.
7. **Self-verification** — restate goal, list assumptions, rubric self-check reduce drift.
8. **Deterministic gate wired in** — `mypy . && ruff check . && lint-imports && pytest --cov` is an Evaluator hard gate, not a loose suggestion.

Prompt-engineering techniques applied: role/expertise priming · grounded context injection ·
task decomposition with phase ordering · chain-of-thought elicitation · few-shot exemplars ·
output contract/schema · negative constraints/guardrails · self-verification loop ·
delimiters/placeholders (`<<FEATURE>>`) · success-criteria alignment to the rubric.

**Two fixes baked in vs. both source templates:** (a) single application path `app/` (removed the `src/` conflict); (b) the supplied rubric weights total **90%**, so the prompt flags the discrepancy instead of inventing the missing 10%.

---

## B. The Unified "Best" Prompt (copy-paste into Claude Code)

```markdown
# ROLE
You are a **Principal AI Architect and Claude Code harness engineer** — expert in agentic
harness design (governed orchestration of AI coding agents), Python/FastAPI production
systems, and translating architectural intent into working, standards-compliant software.
You reason like a Solution Architect who must defend every design choice to a review panel.
Provide concise decisions, assumptions, and traceability — not hidden chain-of-thought.

# PRIMARY OBJECTIVE
Help me deliver the **Cognizant AI-Native Architect Capstone — Build Track**: a **working
Claude Code development harness** that governs a retail API called **StoreOps**.
CRITICAL FRAMING: I am NOT building an autonomous AI agent product. I am building a
**governance harness** — a Planner → Generator → Evaluator → Monitor orchestration layer,
driven by `CLAUDE.md`, that makes AI-generated StoreOps code production-ready and
standards-compliant. Keep harness concerns and StoreOps concerns clearly separated throughout.

# GROUND TRUTH (authoritative; do not contradict)

## Harness = 4 components
- **Planner** → `.harness/output/spec.md` + `sprint-N-contract.md` with GIVEN/WHEN/THEN ACs;
  maps each AC to a test; ends with `STATUS: AWAITING APPROVAL`. No generation until `STATUS: APPROVED`.
- **Generator** → code + tests in `app/`/`tests/` + `generator-summary.md`
  (AC self-check table, files changed, tests added, events, known gaps). Never edits approved ACs.
- **Evaluator** → `evaluator-feedback.md` with verdict PASS / CONDITIONAL PASS / FAIL +
  file/line feedback, hard-gate results, weighted score. Reports findings; does not repair code.
- **Monitor** → append-only `run-log.md` in `.harness/reviews/` (sprint ID, verdict, iterations,
  escalation flag, token-cost estimate, quality-trend notes). Records evidence only.
- **CLAUDE.md** = root orchestrator: entry-prompt format, agent references, sequence, approval
  checkpoint, verdict routing, **max 3 iterations then escalate** to `.harness/output/escalation.md`,
  context-scoping/reset strategy, CI/CD relationship, security boundaries, definition of done.

## Governed app = StoreOps (Python / FastAPI / Pydantic; in-memory storage)
- 5 modules: **activities, programmes, staff, alerts, reports**.
- Strict layers per module: **Routes → Service → Repository** (no skipping).
- Cross-module reads via **service layer only**; cross-module side effects via **event bus only**.
- **reports** is **read-only**. Typed **AppError** hierarchy (code, message, statusCode) — no raw exceptions.
- Shared technical capabilities (error contract, event bus, audit sink, logging, config) live in
  `app/shared/` and must NOT become a 6th business module.

## 4 failure modes to PREVENT (map every hard gate to one)
1) Direct cross-module repository imports.  2) Raw error throws bypassing AppError.
3) Tests asserting HTTP status only (no business-rule check).  4) Missing event-bus integration.

## 5 architecture rules the Evaluator enforces
Module boundary · Event bus only · Error contract · Layer separation · Read-only reports.

# STACK & QUALITY GATE
- Python 3.11+, FastAPI, Pydantic; pytest + httpx; mypy + Ruff; import-linter (or equivalent).
- **Deterministic auto-check (wire in as an Evaluator hard gate):**
  `mypy . && ruff check . && lint-imports && pytest --cov`
- Start: `uvicorn app.main:app --reload`.  Deploy target: **AWS** (ECS / Elastic Beanstalk);
  local Docker = minimum.

# DEMONSTRATION FEATURE (placeholder — keep unless I override)
<<FEATURE = "Shift handover bulk update — PATCH /api/activities/bulk-status marking multiple
activities DONE or BLOCKED in one request, with partial-failure handling (HTTP 207), one
event published per successful update, and one audit entry per updated task">>

# HOW TO THINK
- Restate the objective in 3 sentences to confirm alignment.
- List assumptions and clarifying questions BEFORE the plan; if a gap is minor, state a
  reasonable assumption and proceed — do not stall.
- Keep harness vs. StoreOps concerns separate.
- Make every choice traceable to a StoreOps rule or failure mode — no generic principles.

# TASK — phased, Claude-Code-executable build plan
Phases (bite-sized, sequential; split into 3A/3B if too large for one safe invocation):
Phase 0 Setup → 1 Generate StoreOps baseline → 2 Planner + sprint-decomposition skill →
3 Generator + stack skills → 4 Evaluator + Monitor + eval framework → 5 End-to-end run →
6 AWS deployment → 7 Design Brief + Reflection + repo self-check.
For EVERY phase provide: **Objective**, **.md artefacts created** (mapped to
`CLAUDE.md`, `.harness/agents/*.agent.md`, `.harness/skills/<name>/SKILL.md`,
`.harness/output/`, `.harness/reviews/`, `PROMPT.md`, `DESIGN_BRIEF.md`, `DEPLOYMENT.md`,
`REFLECTION.md`), **allowed vs. protected scope**, and **the EXACT Claude Code CLI prompt in a
bash block** ending with `mypy . && ruff check . && lint-imports && pytest --cov` and an
instruction to fix failures before finishing. Do not fabricate command output or completions.

# FEW-SHOT EXEMPLARS (match this specificity)

## Acceptance criterion (Planner style)
**AC-2:** GIVEN a bulk-status request with 3 task IDs where 1 does not exist, WHEN
`PATCH /api/activities/bulk-status` runs, THEN the 2 valid tasks update, the missing ID
returns AppError `TASK_NOT_FOUND`, HTTP 207 is returned, one event is published per successful
update, and one audit entry is written per updated task (no event/audit for the failed item).
Tests must assert states, error code, events, and audit count — not status alone.

## Evaluator hard gate (deterministic + traceable)
**HG-1 → prevents Failure Mode 1.** Check: import-linter reports **zero** imports of another
module's repository. Mapping: any occurrence → **FAIL** (not a soft deduction), because a
boundary breach silently couples modules and cannot be safely merged.

# OUTPUT FORMAT (use exactly)
1. **Alignment Check** — 3-sentence restatement + assumptions/questions.
2. **Executive Summary** — harness architecture, ≤200 words.
3. **Project Architecture** — table of agents/modules + responsibilities.
4. **Execution Plan** — Phases 0–7 (Objective · .md artefacts · allowed/protected scope ·
   bash CLI prompt ending in the gate).
5. **Evaluation Framework Blueprint** — 2+ dimensions, weights **summing to 100%**, hard gates
   (each mapped to a failure mode), and a verdict-rule table.
6. **Rubric Self-Check** — table mapping each section to the capstone rubric
   (Working harness 40% · Design Brief 15% · Demonstration 25% · Panel 10%). NOTE: these total
   only **90%** — flag this gap, check the attached PDF for the missing/corrected weight, and
   mark it `UNCONFIRMED` if unresolved. Do not invent the missing 10%.

# GUARDRAILS
- Do NOT build/design an autonomous agent product — this is a **harness**.
- Do NOT collapse the 4 roles into one prompt; the Generator may not approve its own work;
  the Evaluator may not repair code; weighted scores may not override a failed hard gate.
- Do NOT exceed 3 Generator–Evaluator iterations before escalating.
- Do NOT write generic skill files — every rule references a StoreOps entity/rule.
- Do NOT put harness files in `.github/` (workflows only); keep agents/skills in `.harness/`.
- Do NOT bypass Routes → Service → Repository, import sibling repositories, cross-module
  side-effect without the event bus, permit writes from reports, or use raw exceptions.
- Keep CLI prompts small and single-purpose; prefer more phases over giant prompts.
- If anything here conflicts with the attached PDF, the **PDF wins** — say so explicitly.
```

---

## C. Phased Execution Plan — Artefacts, Scope & CLI Prompts

These are the **skeletons Claude Code should fill and follow**. Run them in order; each is
single-purpose. Phase 0 validates structure only (no app code exists yet); from Phase 1 onward
every phase ends with the full deterministic gate.

**Validation aliases used below**

- `GATE_FULL` = `mypy . && ruff check . && lint-imports && pytest --cov`
- `GATE_DOCS` = verify required files exist at the exact paths, all internal Markdown links and
  file references resolve, required headings are present, and no `.harness/` content sits in `.github/`.

---

### Phase 0 — Repository setup & authoritative requirements

| Field | Value |
|---|---|
| **Objective** | Establish repo skeleton, toolchain, and the authoritative requirements register. |
| **Artefacts created** | `CLAUDE.md` (skeleton), `PROMPT.md`, `pyproject.toml`, `.gitignore`, `.harness/` tree, `.importlinter` |
| **Allowed scope** | Repo root, `.harness/**`, `pyproject.toml` |
| **Protected scope** | none (greenfield) |
| **Rules / failure modes** | Sets up the machinery that HG-1 and HG-7 depend on |
| **Validation** | `GATE_DOCS` + toolchain version checks |
| **Exit criteria** | Tree matches the artefact inventory; toolchain runs; `CLAUDE.md` names all four agents and the 3-iteration escalation rule. |

```bash
claude "
Objective: Create the capstone repository skeleton and toolchain. Do not write StoreOps business logic yet.

Authoritative context: the attached capstone PDF (PDF wins on any conflict).

Allowed scope: repo root, .harness/**, pyproject.toml, .gitignore, .importlinter
Protected scope: none

Requirements:
1. Create the tree: CLAUDE.md, PROMPT.md, .harness/{agents,skills,output,reviews}/, app/, tests/
2. pyproject.toml pinning fastapi, pydantic, pytest, pytest-cov, httpx, mypy, ruff, import-linter.
   Configure mypy strictly, configure ruff, and set pytest --cov to target app/.
3. .importlinter: declare each StoreOps module (activities, programmes, staff, alerts, reports)
   as an independent contract so cross-module repository imports are detectable.
4. CLAUDE.md skeleton ONLY: entry-prompt format, references to the four agent files, execution
   sequence, approval checkpoint (STATUS: AWAITING APPROVAL -> STATUS: APPROVED), verdict routing,
   max 3 iterations then escalate to .harness/output/escalation.md, and the context reset strategy.
5. PROMPT.md: record this prompt and the source-of-truth priority order.

Evidence required: final tree listing plus the output of the version checks.

Validation: mypy --version && ruff --version && lint-imports --help
Then confirm every required path exists and that no .harness content sits under .github/.

Definition of done: tree matches the inventory, tooling executes, CLAUDE.md states the escalation rule.
If a requirement conflicts with the capstone PDF, stop and report the exact conflict.
"
```

---

### Phase 1 — StoreOps baseline

| Field | Value |
|---|---|
| **Objective** | Generate the governed FastAPI app: 5 modules, 3 layers, AppError, event bus, audit sink. |
| **Artefacts created** | `app/main.py`, `app/shared/{errors,events,audit,logging,config}.py`, `app/{activities,programmes,staff,alerts,reports}/{routes,service,repository,models}.py`, `tests/**` |
| **Allowed scope** | `app/**`, `tests/**` |
| **Protected scope** | `.harness/**`, `CLAUDE.md`, `PROMPT.md` |
| **Rules / failure modes** | All 5 rules; establishes the surface that FM-1…FM-4 are gated against |
| **Validation** | `GATE_FULL` |
| **Exit criteria** | App starts via `uvicorn app.main:app --reload`; zero import-linter violations; reports exposes no write route. |

```bash
claude "
Objective: Implement the StoreOps baseline application. Harness agent files are out of scope.

Allowed scope: app/**, tests/**
Protected scope: .harness/**, CLAUDE.md, PROMPT.md, pyproject.toml

Requirements:
1. Five modules under app/: activities, programmes, staff, alerts, reports.
   Each has routes.py, service.py, repository.py, models.py. Routes -> Service -> Repository only.
   Routes must never import a repository.
2. app/shared/errors.py: typed AppError hierarchy (code, message, statusCode) plus a FastAPI
   exception handler mapping AppError to responses. No raw Exception escapes the service layer.
3. app/shared/events.py: in-process event bus (publish/subscribe). All cross-module side effects
   go through it. No module writes to a sibling module's repository.
4. app/shared/audit.py: in-memory audit sink subscribing to domain events. Shared infrastructure,
   NOT a sixth business module.
5. reports is read-only: no create/update/delete repository operations, no mutation events,
   no write routes.
6. In-memory repositories with seed data. app/main.py wires routers and the error handler.
7. Tests in tests/ covering layering, the error contract, event publication, and read-only reports.
   Assert business outcomes and side effects, never HTTP status alone.

Evidence required: files created, a module-by-module layer map, and the list of published event types.

Validation: mypy . && ruff check . && lint-imports && pytest --cov
Fix all failures within the allowed scope and rerun until clean.

Definition of done: gate passes, uvicorn app.main:app --reload starts, zero import-linter violations.
"
```

---

### Phase 2 — Planner agent + sprint-decomposition skill

| Field | Value |
|---|---|
| **Objective** | Give the harness a Planner that emits an approvable, testable sprint contract. |
| **Artefacts created** | `.harness/agents/planner.agent.md`, `.harness/skills/sprint-decomposition/SKILL.md`, `.harness/skills/storeops-boundaries/SKILL.md` |
| **Allowed scope** | `.harness/agents/planner.agent.md`, `.harness/skills/**`, `CLAUDE.md` |
| **Protected scope** | `app/**`, `tests/**` |
| **Rules / failure modes** | Planner must scope work so FM-1…FM-4 are designed out up front |
| **Validation** | `GATE_DOCS` + `GATE_FULL` (app already exists) |
| **Exit criteria** | Contract ends with `STATUS: AWAITING APPROVAL`; every AC is GIVEN/WHEN/THEN and maps to a named test. |

```bash
claude "
Objective: Author the Planner agent and its skills. Do not modify application code.

Allowed scope: .harness/agents/planner.agent.md, .harness/skills/**, CLAUDE.md
Protected scope: app/**, tests/**

Requirements:
1. planner.agent.md defines inputs, the StoreOps context it must read, outputs
   (.harness/output/spec.md and sprint-N-contract.md), and the rule that it writes NO production code.
2. Every acceptance criterion uses GIVEN/WHEN/THEN, carries an AC-id, names the impacted modules
   and architecture rules, and maps to at least one named test.
3. The contract must record assumptions, dependencies, risks, and explicit exclusions.
4. The contract MUST end with the literal line: STATUS: AWAITING APPROVAL
   and must state that generation is forbidden until it reads STATUS: APPROVED.
5. skills/sprint-decomposition/SKILL.md: how to slice a feature into one reviewable sprint.
6. skills/storeops-boundaries/SKILL.md: module boundary, event-bus-only side effects, layer
   separation, and read-only reports — each written against real StoreOps entities, not generic advice.
7. Update CLAUDE.md to reference the Planner and the approval checkpoint.

Evidence required: file list plus the AC template verbatim.

Validation: confirm all referenced paths exist and links resolve, then run
mypy . && ruff check . && lint-imports && pytest --cov to prove app code was untouched and still green.

Definition of done: no generic rules, approval line present, every AC maps to a test.
"
```

---

### Phase 3 — Generator agent + stack skills

| Field | Value |
|---|---|
| **Objective** | Define how code gets written, and the StoreOps-specific skills that constrain it. |
| **Artefacts created** | `.harness/agents/generator.agent.md`, `.harness/skills/{fastapi-module,app-error-contract,event-bus-integration,business-rule-testing}/SKILL.md` |
| **Allowed scope** | `.harness/agents/generator.agent.md`, `.harness/skills/**`, `CLAUDE.md` |
| **Protected scope** | `app/**`, `tests/**`, `.harness/agents/planner.agent.md` |
| **Rules / failure modes** | Skills are the primary *preventive* control for FM-1…FM-4 |
| **Validation** | `GATE_DOCS` + `GATE_FULL` |
| **Exit criteria** | ≥6 skill files exist in total; generator-summary schema defined; Generator forbidden from editing approved ACs. |

> Split into **3A (skills)** and **3B (generator agent)** if one invocation grows too large.

```bash
claude "
Objective: Author the Generator agent and the StoreOps implementation skills. No application code changes.

Allowed scope: .harness/agents/generator.agent.md, .harness/skills/**, CLAUDE.md
Protected scope: app/**, tests/**, .harness/agents/planner.agent.md

Requirements:
1. generator.agent.md: reads ONLY the approved sprint contract plus scoped repo context; writes
   code to app/ and tests to tests/; must not alter approved acceptance criteria; must not
   self-approve its work.
2. Define the generator-summary.md schema: sprint ID, contract reference, AC self-check table,
   files created, files modified, tests added, architecture rules touched, events published or
   consumed, known gaps, commands executed, validation results.
3. skills/fastapi-module/SKILL.md: the exact Routes -> Service -> Repository pattern for a
   StoreOps module, with a correct example and a rejected layer-skipping example.
4. skills/app-error-contract/SKILL.md: raising and mapping AppError; explicitly list the
   prohibited raw-exception patterns.
5. skills/event-bus-integration/SKILL.md: publishing a StoreOps domain event and the audit
   subscription path; include the rejected direct-sibling-repository-write example.
6. skills/business-rule-testing/SKILL.md: required assertions are resulting state, error code,
   published events, and audit entry count. Status-only assertions are explicitly rejected.
7. Every skill must cite a real StoreOps module, rule, or failure mode. Reject generic content.

Evidence required: a skill inventory table mapping each skill to the failure mode it prevents.

Validation: confirm paths and links resolve, then
mypy . && ruff check . && lint-imports && pytest --cov

Definition of done: at least six skill files exist across Phases 2-3, each StoreOps-specific.
"
```

---

### Phase 4 — Evaluator + Monitor + evaluation framework

| Field | Value |
|---|---|
| **Objective** | Make quality deterministic: hard gates, weighted dimensions, verdict routing, run logging. |
| **Artefacts created** | `.harness/agents/evaluator.agent.md`, `.harness/agents/monitor.agent.md`, `.harness/skills/evaluation-framework/SKILL.md` |
| **Allowed scope** | `.harness/agents/{evaluator,monitor}.agent.md`, `.harness/skills/evaluation-framework/**`, `CLAUDE.md` |
| **Protected scope** | `app/**`, `tests/**`, Planner and Generator agent files |
| **Rules / failure modes** | HG-1…HG-7 map onto FM-1…FM-4 plus the deterministic suite |
| **Validation** | `GATE_DOCS` + `GATE_FULL` |
| **Exit criteria** | Dimensions total exactly 100%; every hard gate names its failure mode; a failed gate can never be overridden by score. |

```bash
claude "
Objective: Author the Evaluator agent, Monitor agent, and the evaluation framework. No app code changes.

Allowed scope: .harness/agents/evaluator.agent.md, .harness/agents/monitor.agent.md,
               .harness/skills/evaluation-framework/SKILL.md, CLAUDE.md
Protected scope: app/**, tests/**, .harness/agents/planner.agent.md, .harness/agents/generator.agent.md

Requirements:
1. Hard gates, each mapped to a failure mode:
   HG-1 zero cross-module repository imports (FM-1)
   HG-2 typed AppError contract, no raw business exceptions escaping services (FM-2)
   HG-3 business-rule test quality: state, error code, events, audit count (FM-3)
   HG-4 event-bus integration, no direct sibling repository writes (FM-4)
   HG-5 layer separation, routes never call repositories (FM-1, FM-4)
   HG-6 read-only reports, no mutation path (FM-1, FM-4)
   HG-7 deterministic suite: mypy . && ruff check . && lint-imports && pytest --cov
   Any hard-gate violation is FAIL, never a soft deduction.
2. Weighted dimensions summing to EXACTLY 100%. Hard gates are evaluated BEFORE scoring and a
   score can never override a failed gate.
3. Verdict rules: any hard gate fails -> FAIL. No gate fails and score >= 85 -> PASS.
   No gate fails, score 75-84, all conditions non-blocking -> CONDITIONAL PASS.
   No gate fails but score < 75 -> FAIL. Missing evidence for a required AC -> FAIL.
4. evaluator-feedback.md schema: sprint ID, iteration, hard-gate results, weighted score,
   AC result table, architecture-rule table, test evidence, findings with severity and file:line,
   required remediation, verdict, rationale. The Evaluator reports; it never repairs code.
5. monitor.agent.md: append-only run-log.md in .harness/reviews/ capturing sprint ID, feature,
   timestamps, iteration, verdict, hard-gate results, score, files changed, commands, escalation
   flag, token-cost estimate, recurring failure patterns, quality trend, and final disposition.
6. Update CLAUDE.md with verdict routing, the max-3-iteration limit, and the escalation.md contract.

Evidence required: the hard-gate-to-failure-mode matrix and the weight table with its total.

Validation: assert the dimension weights sum to 100, then
mypy . && ruff check . && lint-imports && pytest --cov

Definition of done: weights total 100%, all four failure modes gated, escalation rule unambiguous.
"
```

---

### Phase 5 — End-to-end demonstration run

| Field | Value |
|---|---|
| **Objective** | Run the full harness loop on `<<FEATURE>>` and produce real evidence artefacts. |
| **Artefacts created** | `.harness/output/{spec.md,sprint-1-contract.md,generator-summary.md,evaluator-feedback.md}`, `.harness/reviews/run-log.md`, feature code + tests |
| **Allowed scope** | `.harness/output/**`, `.harness/reviews/**`, `app/activities/**`, `app/shared/**`, `tests/**` |
| **Protected scope** | agent files, skill files, `CLAUDE.md` |
| **Rules / failure modes** | Demonstrates prevention of all four failure modes in practice |
| **Validation** | `GATE_FULL` |
| **Exit criteria** | Contract approved, code generated, verdict recorded, run-log written, HTTP 207 partial-failure behaviour proven by tests. |

> Run as three separate invocations — **5A Plan → (you approve) → 5B Generate → 5C Evaluate + Monitor** — so the approval checkpoint is genuinely exercised.

```bash
# 5A — Plan
claude "
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
"
```

```bash
# 5B — Generate (only after I set STATUS: APPROVED)
claude "
Act as the Generator defined in .harness/agents/generator.agent.md.

Precondition: .harness/output/sprint-1-contract.md must read STATUS: APPROVED. If it does not,
stop immediately and report that the approval checkpoint is not satisfied.

Allowed scope: app/activities/**, app/shared/**, tests/**, .harness/output/generator-summary.md
Protected scope: .harness/agents/**, .harness/skills/**, CLAUDE.md, the approved contract

Requirements: implement exactly the approved acceptance criteria. Preserve Routes -> Service ->
Repository. Publish one domain event per successful update. Produce exactly one audit entry per
successful update. Return HTTP 207 for mixed outcomes with per-item AppError details. Do not alter
the approved acceptance criteria. Write tests asserting state, error code, events, and audit count.

Then write generator-summary.md using the defined schema.

Validation: mypy . && ruff check . && lint-imports && pytest --cov
Fix failures within the allowed scope and rerun until clean. Do not claim success without real output.
"
```

```bash
# 5C — Evaluate + Monitor
claude "
Act as the Evaluator in .harness/agents/evaluator.agent.md, then the Monitor in monitor.agent.md.

Allowed scope: .harness/output/evaluator-feedback.md, .harness/reviews/run-log.md
Protected scope: app/**, tests/**, .harness/output/sprint-1-contract.md, generator-summary.md

Requirements: independently evaluate the implementation against the approved contract. Execute all
hard gates HG-1 through HG-7 and report real command output. Score the weighted dimensions. Produce
file:line findings with severity. Issue exactly one verdict: PASS, CONDITIONAL PASS, or FAIL.
Do NOT repair any code — report only. Then append the Monitor run-log entry.

If the verdict is FAIL, return only actionable findings, increment the iteration counter, and stop.
After three failed iterations, write .harness/output/escalation.md instead of regenerating.
"
```

---

### Phase 6 — Docker, CI/CD, AWS deployment

| Field | Value |
|---|---|
| **Objective** | Make StoreOps deployable and gate deployment behind CI. |
| **Artefacts created** | `Dockerfile`, `.dockerignore`, `.github/workflows/ci.yml`, `DEPLOYMENT.md`, `.harness/skills/aws-deployment/SKILL.md` |
| **Allowed scope** | `Dockerfile`, `.dockerignore`, `.github/workflows/**`, `DEPLOYMENT.md`, `.harness/skills/aws-deployment/**` |
| **Protected scope** | `app/**` business logic, `tests/**`, `.harness/agents/**` |
| **Rules / failure modes** | Operability baseline; HG-7 enforced in CI |
| **Validation** | `GATE_FULL` + `docker build` + container health check |
| **Exit criteria** | Image builds and serves `/health`; CI runs the full gate on push; one AWS target recommended with rationale and rollback. |

```bash
claude "
Objective: Containerise StoreOps, add CI, and document AWS deployment. No business-logic changes.

Allowed scope: Dockerfile, .dockerignore, .github/workflows/ci.yml, DEPLOYMENT.md,
               .harness/skills/aws-deployment/SKILL.md, app/main.py (health endpoint only)
Protected scope: app/** business logic, tests/**, .harness/agents/**

Requirements:
1. Multi-stage Dockerfile on a slim Python 3.11 base, non-root user, HEALTHCHECK,
   serving uvicorn app.main:app.
2. Add a /health endpoint if one does not already exist.
3. .github/workflows/ci.yml running mypy, ruff, lint-imports, and pytest --cov on push and PR.
   Workflows only — no harness agent or skill files under .github/.
4. DEPLOYMENT.md: recommend EITHER ECS Fargate OR Elastic Beanstalk with a concise rationale,
   then cover required AWS resources, environment-based configuration, secrets handling
   (never committed), least-privilege task role, health validation, deployment verification,
   and rollback. Separate minimum-viable deployment from optional enhancements.
5. aws-deployment/SKILL.md: the repeatable deploy and rollback procedure.

Evidence required: docker build output summary and the CI job step list.

Validation: mypy . && ruff check . && lint-imports && pytest --cov
Then: docker build -t storeops:local . and confirm the container responds on /health.

Definition of done: image builds, health check passes, CI enforces the full gate.
"
```

---

### Phase 7 — Design Brief, Reflection & repository self-check

| Field | Value |
|---|---|
| **Objective** | Produce the graded narrative artefacts and verify the repo against the rubric. |
| **Artefacts created** | `DESIGN_BRIEF.md`, `REFLECTION.md`, final `PROMPT.md`, `.harness/output/self-check.md` |
| **Allowed scope** | `DESIGN_BRIEF.md`, `REFLECTION.md`, `PROMPT.md`, `.harness/output/self-check.md`, `CLAUDE.md` |
| **Protected scope** | `app/**`, `tests/**`, `.harness/agents/**`, `.harness/skills/**` |
| **Rules / failure modes** | Rubric coverage; surfaces the 90% weight discrepancy |
| **Validation** | `GATE_FULL` + `GATE_DOCS` |
| **Exit criteria** | Every rubric row cites real repo evidence; the missing 10% is flagged, not invented. |

```bash
claude "
Objective: Write the capstone narrative artefacts and run the final repository self-check.

Allowed scope: DESIGN_BRIEF.md, REFLECTION.md, PROMPT.md, .harness/output/self-check.md, CLAUDE.md
Protected scope: app/**, tests/**, .harness/agents/**, .harness/skills/**

Requirements:
1. DESIGN_BRIEF.md: harness architecture, the four components and their separation of duties,
   the approval checkpoint, retry and escalation design, the four failure modes and their gates,
   the five architecture rules, and the evaluation framework reproduced verbatim from Phase 4.
2. REFLECTION.md: what the harness caught, what it missed, iteration history from run-log.md,
   cost and context observations, and what you would change. Cite real evidence only.
3. PROMPT.md: final prompt, source-of-truth priority, and how the prompt evolved.
4. self-check.md: a rubric table with columns Category, Weight, Repo evidence, Demo evidence,
   Coverage status, Gap. Cover Working harness 40%, Design Brief 15%, Demonstration 25%, Panel 10%.
   IMPORTANT: these total only 90%. Flag the discrepancy explicitly, check the attached capstone PDF
   for the missing or corrected weighting, and mark it UNCONFIRMED if it cannot be resolved.
   Do NOT invent the missing 10%.
5. Append a definition-of-done checklist covering required files, agents, skills, approval gate,
   escalation, architecture compliance, tests, evaluation, monitoring, Docker, CI, AWS, docs,
   and demonstration evidence.

Evidence required: the rubric table and the final repository tree.

Validation: mypy . && ruff check . && lint-imports && pytest --cov
Then confirm every artefact referenced in the rubric table actually exists at the stated path.

Definition of done: no rubric row cites evidence that does not exist; the weight gap is reported.
"
```

---

## D. Quick Usage Tips

- Paste the fenced block in **Section B** into Claude Code first; attach the capstone PDF in the
  same session so the "PDF wins" rule can resolve any conflict.
- Then work through **Section C** one phase at a time. Never batch phases — the value of the
  harness is the checkpoint between them.
- Phase 5 is the graded demonstration. Run 5A, approve manually, then 5B and 5C, so the panel can
  see the approval gate and verdict routing actually working.
- Swap `<<FEATURE>>` if you prefer SLA-breach alerting, regional rollup, or planogram template.
  If you do, update the Phase 5A prompt to match.
- Reuse the **Evaluation Framework Blueprint** output verbatim when you write `DESIGN_BRIEF.md` Section C.
- Before submission, confirm the real rubric weights from the PDF and update the Rubric Self-Check
  so the four categories total 100%.
