# Harness Design Brief

**StoreOps governance harness — Build Track capstone.** This brief documents the architectural
intent behind the working harness in this repository: how the demonstration feature was
decomposed into a sprint contract, how the governance layer enforces StoreOps's architecture
rules, how the Evaluator converts non-deterministic LLM output into a deterministic verdict, and
the key design decisions made during the build. Per capstone PDF §6.2, diagrams count toward the
page total; this brief uses tables in their place, which serve the same reviewing purpose.

---

## Section A — Intent Decomposition

### Why one sprint

The demonstration feature — shift handover bulk update, `PATCH /api/activities/bulk-status` — was
decomposed into a **single sprint contract**. The reason is architectural: the feature has no
internal seam a second sprint could sit behind. Every AC shares the same request shape, the same
service method, and the same three side-effect guarantees (state, event, audit). Splitting it —
"sprint 1 ships all-success, sprint 2 adds partial failure" — would mean shipping a
`bulk_update_status` that returns HTTP 200 unconditionally in sprint 1, which AC-5 (all-fail) and
AC-2 (partial-fail) later contradict; it would not be a smaller correct behaviour, just a wrong
one. `sprint-decomposition/SKILL.md`'s boundary rule is to draw the line where a partial
implementation is still independently correct, not merely smaller — this feature has no such line.

The sprint did absorb one scope decision **before** approval: the existing `activities` router was
`APIRouter(prefix="/api/tasks")`, which cannot host `/api/activities/bulk-status`. Rather than let
the Generator improvise a routing fix mid-sprint, the Planner recorded it as assumption **A-1** — a
second `APIRouter(prefix="/api/activities")` in the same module — so the approving human saw the
decision before any code existed.

### What made each acceptance criterion testable rather than subjective

Every AC in `sprint-1-contract.md` follows GIVEN/WHEN/THEN and is bound to concrete, numeric,
falsifiable outcomes — never "handles errors correctly". Three properties make an AC testable:

1. **Exact counts, not thresholds.** Every AC specifies `updated == N`, `failed == N`, and an
   exact event/audit count using `==`. `how-to-test/SKILL.md` bans `>=` for this reason — a
   threshold assertion is satisfied by a bug that publishes too many events.
2. **A named test, decided before code exists.** Each AC ends with a `Tests:` line naming the exact
   function that asserts it — e.g. AC-2 names
   `test_partial_failure_returns_207_and_updates_only_valid_tasks`. HG-8 checks exactly this: an AC
   without a named, passing test is unimplemented regardless of what the Generator claims.
3. **State read back, not inferred from the response.** AC-3 requires `task-4` to be re-read via
   `GET /api/tasks/{id}` and found unchanged — the contract does not accept the response body's
   silence about `task-4` as proof nothing happened to it.

### One full acceptance criterion, reproduced from `sprint-1-contract.md`

> **AC-2:** GIVEN seeded `task-1` (TODO) and `task-2` (IN_PROGRESS), and the id `task-999` which
> does not exist
> WHEN `PATCH /api/activities/bulk-status` runs with `task_ids: ["task-1", "task-999", "task-2"]`
> and `status: DONE`
> THEN `task-1` and `task-2` read back as `DONE`, the `task-999` entry is `FAILED` with
> `error.code == "TASK_NOT_FOUND"` and `error.statusCode == 404`, HTTP **207** is returned,
> `updated == 2` and `failed == 1`, `results` preserves request order, **exactly 2**
> `ACTIVITY_STATUS_CHANGED` events are published, AND **exactly 2** audit entries exist — **no
> event and no audit entry for `task-999`**.
>
> - **Modules:** `activities` (writes); none (reads)
> - **Architecture rules:** Layer separation, Error contract, Event bus only
> - **Tests:** `tests/activities/test_activities_bulk_status.py::test_partial_failure_returns_207_and_updates_only_valid_tasks`

This one AC exercises three of the five architecture rules and directly targets FM-2 (a typed
`AppError`, not a raw exception) and FM-3 (the test must assert event/audit *counts*, not just the
207 status) — deliberate, since this feature was chosen from PDF §3.4 specifically because it
exercises all five rules and all four failure modes in one sprint (`PROMPT.md` §3).

---

## Section B — Governance Framework

### Skill file strategy

Ten skill files exist under `.harness/skills/`, four above PDF §5.3's stated minimum of six. Each
earns its place by governing a distinct part of the pipeline, and none restates another's rules:

| Skill | Read by | Governs | Why shared / not shared |
|---|---|---|---|
| `app-context` | **all four** | Orientation: 5 modules, 9 (now 10) endpoints, 3 events, seed data | Shared because every agent needs the same facts before acting; kept short because its cost is paid four times per iteration |
| `architecture-principles` | Planner, Generator, Evaluator | *What* the five rules are and what breaks without each, with correct/rejected examples | Shared across the three agents that must reason about the rules, but not the Monitor, which never reads `app/` |
| `sprint-decomposition` | Planner only | Sprint slicing, AC testability, the AC→test mapping | Planner-only: no other agent draws sprint boundaries |
| `component-patterns`, `app-error-contract`, `event-bus-integration`, `how-to-test` | Generator only | *How* to type the code that obeys each rule — the routes/service/repository pattern, the `AppError` hierarchy, the publish/subscribe wiring, the four required test assertions | Deliberately **not** given to the Evaluator. If the Evaluator graded code against a restatement of the Generator's own implementation guide, a sprint could pass by matching the template rather than by being correct |
| `how-to-review`, `evaluation-criteria` | Evaluator only | Review order and evidence standard; the hard gates, weighted dimensions, and verdict rules | Two files, not one, because PDF §5.3 requires at least two Evaluator-specific skills, and because "how to review" (process) and "what to measure" (criteria) are genuinely separable — a reviewer can improve the process without changing the rubric |
| `aws-deployment` | whoever deploys | The ECS Fargate deploy/rollback runbook | Governs an *operational* action, not code generation — written as a numbered runbook rather than feedforward rules for that reason |

Every rule in every file cites a real StoreOps symbol or path — a generic-sounding rule is treated
as a defect in that file, per the drift signal below.

### The `.harness/reviews/` archive as a governance audit trail

`.harness/reviews/` holds five committed files for sprint 1: `sprint-1-spec.md`,
`sprint-1-contract.md`, `sprint-1-generator-summary.md`, `sprint-1-evaluator-feedback.md`, and
`sprint-1-run-log.md`. Unlike `.harness/output/` (gitignored working state), this directory is
permanent — CI's `harness-separation` job fails the build if it is ever empty, so committing the
audit trail is enforced, not a convention.

**What it captures.** Per sprint: the approved contract, what the Generator built and self-checked
against each AC, the Evaluator's independent verdict with real gate output, and the Monitor's
append-only run log — iteration count, hard-gate results, dimension scores, token cost estimate,
and a **skill-file drift signal** field.

**Who can access it.** Any future agent invocation or human reviewer — it is plain committed
markdown, not a database. The Planner and Generator do not read it (context-scoping rule 3 in
CLAUDE.md §5); the Monitor and any future audit do.

**How it surfaces a recurring issue.** `monitor.agent.md` defines the drift-signal field as firing
when a gate fails twice on the same rule *or* when a finding names a skill file directly. In the
sprint-1 run, three MINOR findings all named skill files (`app-context` §3/`:72`,
`component-patterns` §6, `how-to-test` §4), and the Monitor recorded the drift signal on the
**first** occurrence rather than waiting for a second, reasoning that shipping a known-stale
`app-context` to sprint 2 would propagate the defect to all four agents on the very next
invocation. That is the audit trail doing exactly the job PDF §6.2 asks it to describe: turning a
one-off finding into a named candidate refinement before it recurs.

### One skill file rule, stated in full, with what breaks without it

From `architecture-principles/SKILL.md`, **Rule 2 — Event bus only**:

> Side effects that cross a module boundary are raised via `app/shared/events.py`, never by a
> direct service-to-service call or a sibling repository write.

**What breaks without it**, per the skill file's own analysis, in three ways invisible at the call
site:

1. `AuditSink.record` is subscribed to the bus, so an unpublished side effect produces no
   `AuditEntry` — the notification exists but operations cannot see why.
2. A second consumer becomes impossible to add without editing the producing service — e.g. adding
   an SMS escalation would force a change inside `activities`, a module that has no business
   knowing escalation exists.
3. `activities` can no longer be tested in isolation, because exercising a status change would
   require the `alerts` repository to be present and reset.

This is the rule HG-1 and HG-4 both gate, and it is the rule the evaluation-criteria worked example
(Section C below) shows failing.

---

## Section C — Non-Determinism Strategy

*Reproduced verbatim from `.harness/skills/evaluation-criteria/SKILL.md`, the binding evaluation
framework built in Phase 4 and exercised unchanged in the Phase 5 demonstration run.*

### 1. Order of operations — non-negotiable

```
1. Run the deterministic suite. Capture real output.
2. Evaluate HG-1 .. HG-8.  Any gate FAIL  ->  VERDICT: FAIL. STOP. Do not score.
3. Only if all eight gates pass: score the five dimensions.
4. Apply the verdict rules in section 5.
```

Hard gates are evaluated **before** scoring, and a score can never override a failed gate. A
boundary breach in code that is otherwise 98% quality is still a boundary breach: it cannot be
safely merged, so there is no score that should let it through.

### 2. The hard gates — the failure-mode matrix

| Gate | Check | → FM | Detection | Type |
|---|---|---|---|---|
| **HG-1** | Zero direct imports of another module's `repository` | **FM-1** | `lint-imports` — the five `*-no-cross-module-repository` contracts | automated |
| **HG-2** | Every failure is an `AppError` subclass; no raw exception escapes a service or route | **FM-2** | `ruff` `TRY002`/`TRY301`/`BLE001` + AST test + review | automated + LLM |
| **HG-3** | Every business test asserts resulting state, `AppError.code`, event count, audit count. Status-only assertion fails. Coverage ≥ 80% | **FM-3** | `pytest --cov` + review of named tests | automated + LLM |
| **HG-4** | Cross-module side effects go through `EventBus.publish`; no direct sibling-repository write and no cross-module write by service call | **FM-4** | `lint-imports` + review of the publish path | automated + LLM |
| **HG-5** | No `routes.py` imports any `repository`; no business rule in a route | **FM-1, FM-4** | `lint-imports` layers contract + AST test | automated |
| **HG-6** | No write originates in `app/reports/` | **FM-1, FM-4** | `lint-imports` + read-only tests | automated |
| **HG-7** | `mypy . && ruff check . && lint-imports && pytest --cov` exits 0 | **all four** | the command itself | automated |
| **HG-8** | Every approved AC has an accurate `file:line` reference **and** a named, passing test | **FM-3** | `generator-summary.md` cross-checked against the repository | LLM-verified |

All four failure modes are gated: FM-1 by HG-1/HG-5/HG-6, FM-2 by HG-2, FM-3 by HG-3/HG-8, FM-4 by
HG-4/HG-5/HG-6.

**Why none can be a soft check.** HG-1: a boundary breach silently couples two modules — partial
credit merges the coupling. HG-2: the error contract is binary — a raw raise returns an untyped 500
with no code to branch on. HG-3: a status-only test is worse than no test — a green suite that
certifies nothing. HG-4: an unpublished side effect leaves no audit entry, invisible to operations.
HG-5: a rule in a route is unreachable from an event handler, so the same change bypasses
validation by another path. HG-6: one write makes `reports` a second source of truth. HG-7 is the
CI gate — a red suite cannot be merged regardless of design quality. HG-8: an AC accepted on
assertion converts the contract into a suggestion.

### 3. The weighted dimensions — sum to exactly 100%

| # | Dimension | Weight | Gates it carries | Automated check |
|---|---|---:|---|---|
| D1 | Architecture Compliance | **35%** | HG-1, HG-4, HG-5, HG-6 | `lint-imports` |
| D2 | Test Quality & Business-Rule Coverage | **25%** | HG-3 | `pytest --cov`, `fail_under = 80` |
| D3 | Error Contract Integrity | **15%** | HG-2 | `ruff` TRY/BLE + `mypy` |
| D4 | Contract Fidelity | **15%** | HG-8 | named-test existence and pass |
| D5 | Toolchain Cleanliness | **10%** | HG-7 | the full gate command |
| | **TOTAL** | **100%** | HG-1…HG-8 | ≥1 automated check per dimension |

**Why these five for StoreOps.** D1 carries the largest weight because three of the four failure
modes are boundary or layering failures, and they compound — a breach merged today makes the next
one cheaper. D2 is second because FM-3 defeats every other control: a green suite that asserts
nothing makes D1 and D3 unverifiable. D3 and D4 are equal and mid-weight — both are contract
integrity, one with the client's architecture, one with the human approver. D5 is smallest not
because it matters least but because it is fully automated and binary; weight spent there buys no
discrimination between sprints.

### 4. Verdict rules — same inputs, same outcome

| # | Condition | Verdict |
|---|---|---|
| 1 | Any of HG-1…HG-8 fails | **FAIL** |
| 2 | No gate fails and weighted score ≥ 85 | **PASS** |
| 3 | No gate fails, score 75–84, all outstanding conditions non-blocking | **CONDITIONAL PASS** |
| 4 | No gate fails but score < 75 | **FAIL** |
| 5 | A required AC lacks evidence | **FAIL** (via HG-8) |
| 6 | The Evaluator's own assessment is ambiguous on any check | **FAIL**, ambiguity stated |

A condition is **non-blocking** only if it violates none of the five architecture rules, does not
drop coverage below 80%, leaves no AC unevidenced, is fixable without amending the approved
contract, and is carried into the next sprint contract as a recorded condition. If any one of
those fails, the verdict is FAIL — there is no such thing as a minor boundary breach.

### 5. Walkthrough — variable Generator output to a definitive verdict

**Iteration 1.** The Generator implements `PATCH /api/activities/bulk-status`. It works: correct
207 on mixed outcomes, per-item `TASK_NOT_FOUND`, 8 new tests, coverage 99.4%. The summary claims
every AC implemented. By impression this reads as a strong sprint — a lenient assessor might score
it ~92 and pass it.

The gates run first:

```
$ lint-imports
Contracts: 7 kept, 1 broken.
activities must not import a sibling module's repository BROKEN
- app.activities.service -> app.alerts.repository (l.14)
```

The Generator wrote the audit entry by importing `app.alerts.repository` and calling `add()`
directly instead of relying on the published event. **HG-1 fails → `VERDICT: FAIL`.** The score is
never computed. The finding: `app/activities/service.py:14` — imports `app.alerts.repository`.
Rule violated: Module boundary and Event bus only (FM-1, FM-4). Remediation: delete the import and
rely on `EventBus.publish("ACTIVITY_STATUS_CHANGED", …)`.

Re-running the same inputs produces the same outcome — that is the determinism the instrument
buys, and it is exactly what the 92-by-impression score exists to be overruled by.

**Iteration 2.** The import is gone; `lint-imports` reports 8/8. Scoring finds one dimension check
failed — an event-count assertion read `assert len(events) >= 1` instead of `== 2` — but HG-3 still
passed because a count *was* asserted, just loosely. Score 95.83 → row 2 → `VERDICT: PASS`, with a
non-blocking finding recommending the exact-count fix. Had the same weakness appeared as a
status-only assertion instead, HG-3 itself would have failed and iteration 2 would have been
another FAIL — the difference between a *weak* assertion and an *absent* one is exactly what
separates a scoring deduction from a hard gate.

**What the actual run did differently.** The real run (`sprint-1-run-log.md`) passed on iteration 1
with 8/8 gates and a 100.00 score. REFLECTION.md explains the gap: the approved contract was more
prescriptive than the skill files that would otherwise have steered the Generator toward the wrong
response shape and status code, and the contract took precedence per `generator.agent.md` §2.

### 6. Escalation path

**Trigger:** a third consecutive `VERDICT: FAIL` on the same sprint contract (`CLAUDE.md` §4,
"Iteration bound and escalation"). The bound exists because a third consecutive failure is
evidence the *contract or the skill files* are defective, not the generated code — further
iterations would burn tokens re-deriving the same wrong answer.

**What it contains** (`.harness/output/escalation.md`, per `CLAUDE.md` §4): sprint ID, the
originating feature prompt, iterations used (`3`), the blocking issue with `file:line`, the
specific hard gate that failed, the failure mode it maps to, one line per iteration on what was
tried, the recipient, and a recommended action — amend the contract, refine a named skill file, or
accept a scope reduction.

**Who receives it:** the developer who approved the sprint contract — the same human checkpoint
that started the sprint closes it on escalation.

**Not exercised in this run.** Sprint 1 passed on iteration 1, so no `escalation.md` exists here.
Its absence is not a gap: CLAUDE.md §4 states an escalation is "a successful harness outcome, not
a harness failure" — detecting that a feature cannot be safely generated is exactly what the
governance layer is for. The demonstration evidence covers the PASS path completely and the
escalation path only in specification — noted honestly in REFLECTION.md, not fabricated.

---

## Section D — Architectural Decisions

### Decision 1 — `app/`, not `src/`

**The decision.** Application code lives at `app/`, contradicting PDF §7's repository-structure
table, which names `src/` for every stack including Python.

**Alternatives considered.** (a) Follow §7 literally and use `src/`. (b) Use `app/` per §2.3 Step
4's explicit Python start command, `uvicorn app.main:app --reload`, which requires a top-level
`app` package.

**Rationale.** §7's table is the generic cross-stack row — its sibling entries name Node.js, Java,
and .NET paths, so it reads as a template column rather than a Python-specific instruction. §2.3
Step 4 is unambiguous and Python-specific: the literal command cannot resolve against `src/`. Per
`PROMPT.md` §1, this picks the more specific of two internally conflicting PDF instructions — a
documented reconciliation, not a deviation from the PDF.

**Assumption this depends on.** That §2.3's command is meant literally rather than as an
illustrative placeholder. If Cognizant's programme materials intended `src/` regardless, this
decision would need reversing along with every import in `app/**` and `tests/**` — a
mechanical but wide-reaching change.

### Decision 2 — Ten skill files against a minimum of six, with a strict Generator/Evaluator split

**The decision.** Build ten skill files, not the PDF §5.3 minimum of six, and enforce that the
four Generator-only implementation skills (`component-patterns`, `app-error-contract`,
`event-bus-integration`, `how-to-test`) are never read by the Evaluator.

**Alternatives considered.** (a) Meet the minimum of six and let the Evaluator read the same
implementation-pattern skills the Generator does, on the theory that a shared vocabulary would
make review faster. (b) The chosen approach: separate *what the rule is* (`architecture-principles`,
shared) from *how to type code that obeys it* (Generator-only), and give the Evaluator its own pair
of review-specific skills instead.

**Rationale.** If the Evaluator's skill reads included the Generator's implementation templates, a
sprint could pass review by matching the template's shape rather than by being correct against the
actual rule — the Evaluator would be grading the Generator's homework against an answer key the
Generator itself wrote. Disjoint reads mean the Evaluator's judgment is formed from the rule and
the code, not from a style guide the Generator also had.

**Assumption this depends on.** That the added token cost of four extra skill files (paid once per
Generator invocation, never by the Evaluator or Monitor) is worth the independence it buys. If a
future sprint's Generator context routinely approaches a budget ceiling, this split would need
revisiting — `CLAUDE.md` §5 already documents the cost-awareness trade explicitly for this reason.

### Decision 3 — a second `APIRouter` inside `app/activities/routes.py` rather than moving the endpoint

**The decision.** `PATCH /api/activities/bulk-status` is served by a second `APIRouter(prefix="/api/activities")`
inside the existing `activities` module, aggregated with the original `/api/tasks` router via a
single exported `router` in the same file — rather than, for instance, creating a new top-level
router file or renaming the existing prefix.

**Alternatives considered.** (a) Rename the existing router's prefix from `/api/tasks` to
`/api/activities`, breaking the nine already-tested endpoints. (b) Create the bulk endpoint under
the existing `/api/tasks` prefix instead of matching the PDF's stated path. (c) The chosen
approach.

**Rationale.** The PDF's literal path (`/api/activities/bulk-status`, §3.4) is source-of-truth
priority 1, and the existing prefix serves nine passing endpoints that (b) would have broken
silently. Two routers inside one module is a routing detail — module ownership, layer separation,
and every architecture rule are unaffected, since both delegate to the same `ActivitiesService`.
Recorded as assumption A-1 **before** approval so a human, not the harness, made the call on a
genuine ambiguity in the source material.

**Assumption this depends on.** That a reviewer accepts "two routers, one module" as a routing
detail rather than a layering violation. If a future architecture review decided routers must be
1:1 with URL prefixes, this module would need a second file — a mechanical split with no service or
repository change.
