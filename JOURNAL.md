# JOURNAL.md — Architecture Journal

Design decisions, trade-offs, and insights captured **during** the build, one entry per decision
point, written at the time rather than reconstructed afterwards.

Each entry records: the decision · the alternatives considered · the rationale · **the assumption
the decision depends on**. The last field is the point of the journal — an entry with no stated
assumption is a description of what was done, not a record of a choice.

---

## Phase 0 — Repository setup and toolchain (2026-08-31)

### D-01 · Application code lives in `app/`, not `src/`

**Decision.** All StoreOps source sits under a top-level `app/` package.

**Alternatives considered.**
1. `src/` literally, per the capstone PDF's repository-structure table (section 7).
2. `src/storeops/` with a `package-dir` mapping in `pyproject.toml`.
3. `app/` — chosen.

**Rationale.** The PDF is internally inconsistent here. Section 7's table says `src/`, but section
2.3 step 4 gives the Python verification command as `uvicorn app.main:app --reload`, which cannot
resolve without a top-level `app` package. Reading the two together, section 7's table is the
generic cross-stack row — its sibling rows name Node, Java and .NET paths — while section 2.3 is
the Python-specific instruction. Option 2 would satisfy the table literally but forces either a
packaging indirection or a deviation from the PDF's own documented start command, trading a real
inconsistency for a cosmetic one. Section 7 is not itself a scored rubric row; section 2.3's
command is what a reviewer will actually type.

**Assumption it depends on.** That a reviewer verifying the app will run the PDF's stated start
command rather than diff the tree against section 7's table. If that assumption is wrong the cost
is one explanatory paragraph, which is why the deviation is documented in three places
(`CLAUDE.md` section 7, `PROMPT.md`, `DESIGN_BRIEF.md` Section D) rather than left silent.

---

### D-02 · Python 3.13 via `uv`, not a 3.11 install

**Decision.** The venv is `uv`-managed on CPython 3.13.2.

**Alternatives considered.**
1. Install Python 3.11 to match the PDF's floor exactly.
2. Use the `python` already on PATH (3.14).
3. Python 3.13 via `uv` — chosen.

**Rationale.** The PDF specifies "Python 3.11+", so 3.13 is compliant, not a deviation. Option 2
was rejected on inspection: the 3.14 on PATH is a bare install with only `pip`, and 3.14 is new
enough that FastAPI/Pydantic wheel availability is a risk I did not want on the critical path of a
graded build. There is also a broken `Python311\` directory on this machine with `Lib` and
`Scripts` but no `python.exe`, so option 1 meant a fresh install to gain nothing. `uv` was already
present and resolved all 40 packages in six seconds.

**Assumption it depends on.** That no dependency added later requires `<3.13`. Mitigated by
`requires-python = ">=3.11"` in `pyproject.toml`, so the constraint is declared rather than
implied by whatever happens to be installed — a reviewer or teammate can rebuild on 3.11 without
editing anything.

---

### D-03 · `.harness/output/` is gitignored; `.harness/reviews/` is committed with explicit negations

**Decision.** In-flight run state is untracked. The governance audit trail is tracked, and
`.gitignore` carries explicit `!.harness/reviews/**` negations.

**Alternatives considered.**
1. Commit everything, including `.harness/output/`.
2. Ignore all of `.harness/`, committing artefacts by hand at the end of a run.
3. Split them, with defensive negations — chosen.

**Rationale.** The two directories have opposite lifecycles. `.harness/output/` is mutable scratch
space that the Generator and Evaluator overwrite every iteration; committing it would produce a
history of three near-identical `evaluator-feedback.md` versions per sprint and invite someone to
mistake iteration 2's `FAIL` for the final verdict. `.harness/reviews/` is the opposite — PDF
section 7 designates it the *permanent* quality and observability record, and section 8.2 scores
whether a run-log is actually committed. Option 2 was rejected because a manual archive step is
exactly the step that gets skipped under deadline, and an audit trail with gaps is worse than none:
it looks complete.

The negations are deliberately redundant. Nothing currently ignores `.harness/reviews/`, but the
whole value of the archive is that it survives; a future broad ignore rule silently swallowing the
audit trail is a plausible and near-undetectable failure.

**Assumption it depends on.** That the Monitor writes to `.harness/reviews/` directly rather than
relying on a copy-out step at the end of a run. Enforced in Phase 4 by making the archive path
part of `monitor.agent.md`'s output contract, not a manual instruction.

---

### D-04 · Per-module `forbidden` contracts, not one aggregate `independence` contract

**Decision.** `.importlinter` declares one `forbidden` contract per source module (five of them),
plus a routes-never-import-repositories contract, a layer-ordering contract, and a shared-is-
infrastructure contract.

**Alternatives considered.**
1. A single `independence` contract across the five modules.
2. One aggregate `forbidden` contract listing all modules as sources and all repositories as
   targets.
3. Per-module contracts — chosen.

**Rationale.** Option 1 is wrong on the domain, not merely verbose: full independence would forbid
the *legitimate* cross-module service call the architecture explicitly permits — `reports`
aggregating via `ActivitiesService` is required behaviour, and a contract that bans it would train
developers to disable the linter. Option 2 is wrong mechanically: with every module as a source and
every repository as a target it would forbid `app.activities.service` importing
`app.activities.repository`, which is the intended layering.

Per-module contracts avoid both and buy something the Evaluator needs: a violation names the
offending module in the contract title, so `lint-imports` output drops straight into
`evaluator-feedback.md` as an actionable `file:line` finding rather than an aggregate "contract
broken" that a human has to decompose.

**Assumption it depends on.** That the five module names are stable. If a sixth business module is
added, someone must add both its own contract and an entry in the other five — a real maintenance
cost, accepted because the alternative is losing per-module attribution in the Evaluator's
feedback. Worth revisiting if StoreOps ever exceeds ~8 modules, at which point generating
`.importlinter` from a module list becomes the better trade.

---

### D-05 · Ruff carries part of the error contract, rather than leaving HG-2 fully LLM-assessed

**Decision.** Enable ruff's `TRY`, `BLE`, `EM` and `RSE` rule families so `raise Exception(...)`
and blind `except Exception` are caught by a deterministic tool.

**Alternatives considered.**
1. Leave the error contract entirely to the Evaluator's judgement, as PDF section 3.5 permits
   ("Automated (linter rule) + LLM-assessed").
2. Write a custom AST check for raw raises in `app/**/service.py`.
3. Configure existing ruff rules — chosen.

**Rationale.** PDF section 5.4 strongly recommends at least one automated check per evaluation
dimension, precisely because an LLM assessor's leniency varies between runs — and the Error
Contract dimension is the one most exposed to that, since "is this a raw throw?" reads as a
judgement call to a model even though it is mechanically decidable. `TRY002` flags vanilla
`Exception` raises and `BLE001` flags blind excepts, which is Failure Mode 2 almost exactly, at
zero implementation cost. Option 2 would catch more (e.g. `raise HTTPException` from a service
layer) but is code the harness would then have to maintain and test.

**Assumption it depends on.** That `TRY002` + `BLE001` cover enough of Failure Mode 2 that the
Evaluator's LLM-assessed portion only handles the residue — notably `raise HTTPException` from a
service, which ruff will not flag. This gap is real and is stated in `evaluation-criteria` as the
LLM-assessed part of HG-2 rather than being papered over. If the demonstration run shows the
Evaluator missing it, option 2 becomes the Phase 7 improvement candidate.

---

### Phase 0 insight

Writing `.importlinter` before any application code existed changed the Phase 1 requirements. The
contracts are a machine-readable statement of the architecture, so drafting them forced decisions
that would otherwise have surfaced mid-implementation — in particular that `app/shared/` needs its
own contract forbidding it from importing any business module. Nothing in the capstone brief lists
that as a rule; it falls out of "shared must not become a sixth module" once you try to express it
to a dependency analyser. The constraint is now enforced rather than aspirational.

---

## Phase 1 — StoreOps baseline (2026-08-31)

### D-06 · `forbidden` contracts check DIRECT imports only

**Decision.** Every `forbidden` contract in `.importlinter` sets `allow_indirect_imports = True`.

**Alternatives considered.**
1. Leave the default (transitive checking).
2. Drop the `routes-never-import-repositories` contract and rely on the `layers` contract.
3. Direct-only checking — chosen.

**Rationale.** This was not a preference, it was a **bug fix found by running the gate**. With
transitive checking, import-linter reported five violations that were all the *correct*
architecture:

```
app.staff.routes is not allowed to import app.staff.repository:
-   app.staff.routes -> app.staff.service (l.14)
    app.staff.service -> app.staff.repository (l.13)
```

A route reaching a repository *through its service* is exactly the mandated layering, so the
contract as originally written forbade the design it was meant to protect and the gate was
unpassable. The same false positive hit `reports.service → programmes.service →
programmes.repository`, which is the permitted cross-module read.

PDF section 3.5 says "No module may import **directly** from another module's repository", so
direct-only is also the faithful reading. Option 2 was rejected because the `layers` contract
does *not* forbid a route importing a repository — in a layers contract a higher layer may
import any lower layer, so `routes → repository` is permitted by construction. Only an explicit
`forbidden` contract catches layer skipping.

**Assumption it depends on.** That a developer cannot launder a boundary breach through an
intermediary module — e.g. `activities.service → helper → alerts.repository` would now pass. The
residual risk is accepted because the *direct* import is the realistic failure mode (it is what
an LLM writes when it wants a sibling's data), and the laundering variant requires deliberately
constructing a shim. `tests/test_architecture.py` adds a source-level AST check as a second net.

### D-07 · Cross-module side effects are wired in `main.py`, not inside a module

**Decision.** `app/main.py` is the composition root: it attaches the audit sink to the bus and
registers the alerts subscriber. No business module wires another.

**Alternatives considered.**
1. `activities.service` calls `alerts_service` directly for the notification.
2. Each module self-registers its subscribers on import.
3. Explicit wiring in the composition root — chosen.

**Rationale.** Option 1 *is* Failure Mode 4 and would break HG-1/HG-4. Option 2 is subtler and
tempting: it keeps wiring next to the handler. But import-time side effects mean the
subscription depends on whether a module has happened to be imported yet, which makes the
cross-module behaviour dependent on import order — untestable in isolation and a genuinely
nasty class of bug. Explicit wiring means the whole fan-out of the system is readable in one
file, which is also what lets the Evaluator verify the event topology without tracing imports.

**Assumption it depends on.** That the number of subscriptions stays small enough to enumerate
by hand. Past roughly a dozen, a declarative registry that `main.py` iterates would be better;
the current three-line body is not worth that machinery.

### D-08 · `EventBus.subscribe` is idempotent

**Decision.** Re-subscribing an already-registered handler is a silent no-op.

**Alternatives considered.**
1. Allow duplicates (standard pub/sub semantics).
2. Raise on duplicate registration.
3. Idempotent no-op — chosen.

**Rationale.** The test suite builds an application per test via `create_app()`, and each build
calls `wire_event_handlers()` against the process-wide bus. Under option 1 the twentieth test
would fire twenty notifications per status change — and the symptom (an off-by-N side-effect
count) is miles from the cause (factory wiring). Option 2 is defensible for a library but would
make the application factory non-reentrant, which is a worse constraint than the one it removes.
The guard works because Python bound methods compare equal when `__self__` and `__func__` match.

**Assumption it depends on.** That no caller legitimately wants the same handler invoked twice
per event. True here, and the property is asserted directly by
`test_subscribe_is_idempotent_so_wiring_twice_does_not_double_side_effects` so the intent
survives someone "simplifying" the guard away.

### D-09 · `DONE` is terminal and same-status updates are rejected

**Decision.** The transition table permits nothing out of `DONE`, and no status may transition
to itself.

**Alternatives considered.**
1. Allow any transition; treat status as a free-form field.
2. Allow reopening `DONE` (e.g. `DONE → IN_PROGRESS`).
3. `DONE` terminal, self-transitions rejected — chosen.

**Rationale.** Option 1 leaves the Evaluator with nothing to assess: with no rule there is no
business rule for a test to verify, which quietly enables Failure Mode 3 (status-only
assertions become the *only* thing a test could assert). A completed activity is an audit record
of work done on a shift; reopening it rewrites history rather than recording a new problem, so
option 2 was rejected in favour of raising a fresh activity. Rejecting self-transitions matters
for the event contract specifically: a `TODO → TODO` update would publish an
`ACTIVITY_STATUS_CHANGED` event whose `previousStatus` equals its `newStatus`, i.e. an audit
entry describing no change.

**Assumption it depends on.** That the Phase 5 bulk-status feature wants an invalid-transition
path to exercise. It does — a request mixing a valid task with a `DONE` one is precisely the
HTTP 207 partial-failure case, and this rule is what generates the per-item error.

### D-10 · Endpoint inventory asserted from the OpenAPI schema, not `app.routes`

**Decision.** Tests that assert which endpoints exist read `/openapi.json`.

**Alternatives considered.**
1. Walk `app.routes` and read `.path` / `.methods`.
2. Maintain a hand-written list and review it by eye.
3. Assert against the published OpenAPI document — chosen.

**Rationale.** Option 1 was written first and **failed**: FastAPI 0.141 on Starlette 1.6 wraps
each included router in an internal object exposing only `original_router` and
`effective_route_contexts` — no `.path`, no `.methods`. So five of ten entries in `app.routes`
were opaque, and a test walking that table silently saw only `/health`. Worse, it *looked* like
an application bug when the routing itself was fine. The OpenAPI document is a public, versioned
contract and is closer to what the assertion actually means: "what does this service publish?"

**Assumption it depends on.** That every endpoint appears in the schema — false for a route with
`include_in_schema=False`. Nothing in StoreOps uses that flag; if one ever did, the 9-endpoint
test would under-count and needs revisiting.

### Phase 1 insight

Two of the three defects in this phase were found by the automated gate rather than by reading
the code — the import-linter false positives (D-06) and the route-introspection breakage (D-10).
Neither was visible by inspection, and both would have been invisible to an LLM Evaluator
reasoning about the source without executing anything. That is the concrete argument for HG-7
requiring *pasted command output* rather than an assertion that checks pass: the run is the
evidence. It also means the Evaluator must never be allowed to "reason" its way to a gate
verdict, which is now a stated rule for Phase 4.

---

## Phase 2 — Planner agent and shared-foundation skills (2026-09-04)

### D-11 · Skill files named after the PDF's vocabulary, not the working document's

**Decision.** The shared foundation is `app-context` + `architecture-principles`. The working
document's proposed `storeops-boundaries` is not created.

**Alternatives considered.**
1. `storeops-boundaries`, as `capstone_best_prompt_combined.md` and the Phase 2 prompt both name it.
2. Create both — `architecture-principles` for the rubric, `storeops-boundaries` as an alias.
3. `app-context` + `architecture-principles` only — chosen.

**Rationale.** PDF section 5.3 names the required files literally: *"Shared foundation (required
for all agents): app-context, architecture-principles"*, and section 5.2's table names
`how-to-review` for the Evaluator. Skill file quality is 8% of the working-harness score and a
reviewer checks section 5.3 as a list; a file named `storeops-boundaries` forces them to infer the
mapping. The working document is explicitly ranked below the PDF in `PROMPT.md`'s source-of-truth
order, so this is not a judgement call — it is that order being applied. Option 2 was rejected
because a duplicated rule set drifts: two files stating the module boundary rule means one of them
is eventually wrong, and PDF section 11 is explicit that a great submission is one where *every
file earns its place*.

**Assumption it depends on.** That the grader checks section 5.3's named list rather than counting
files. If they only count, the naming is neutral and this costs nothing — the decision is
asymmetric in its favour.

### D-12 · The Planner names tests but never writes them

**Decision.** Each AC carries `<path>::<test_name>`. The Generator creates the test with that
exact name.

**Alternatives considered.**
1. The Planner writes the test bodies, so the contract is executable.
2. The Planner names no tests; the Generator chooses its own coverage.
3. The Planner names tests, the Generator implements them — chosen.

**Rationale.** Option 1 is tempting because a failing test is the most precise possible acceptance
criterion. It breaks separation of duties in a specific way: the Generator would be graded against
tests it did not have to satisfy honestly, and the fastest route to green becomes editing the
Planner's test rather than the code. Option 2 leaves HG-3 unenforceable — with no named test, the
Evaluator cannot distinguish "not tested" from "tested somewhere", which is exactly the ambiguity
FM-3 hides in. Naming without implementing gives the Evaluator a mechanical check (does
`test_partial_failure_returns_207_and_updates_only_valid_tasks` exist and pass?) while leaving the
Generator responsible for the assertions inside it.

**Assumption it depends on.** That the Generator cannot pass HG-3 with a named-but-hollow test —
a function with the right name and a single `assert response.status_code == 207`. It cannot, but
only because HG-3 requires the four assertions (state, error code, event count, audit count) as a
separate check. If that check were relaxed, this decision would become a loophole. The two are
coupled and must stay coupled.

### D-13 · Contract exclusions are binding on the Evaluator, not just informative

**Decision.** The contract's Exclusions block states what the sprint deliberately does not do, and
`planner.agent.md` records that the Evaluator must **not** report those as gaps.

**Alternatives considered.**
1. Omit exclusions; let the Evaluator judge scope from the ACs.
2. List exclusions as informational context.
3. Make them binding — chosen.

**Rationale.** An Evaluator that fails closed on ambiguity (the harness's stated posture) will
treat absent functionality as a gap unless told otherwise. Without exclusions, "bulk update does
not support reassignment" reads as incomplete work, producing a finding the Generator cannot fix —
it would have to implement out-of-scope work to clear it. That is a mechanism for burning all three
iterations on a scope dispute rather than a defect. Making exclusions binding converts a likely
false-positive FAIL into a settled question, decided by the human at approval time, which is where
scope decisions belong.

**Assumption it depends on.** That the Planner's exclusions are honest rather than a way to
pre-excuse weak work. The control is the approval checkpoint: the human reads the exclusions before
writing `STATUS: APPROVED`, so an exclusion that guts the feature is visible precisely when it is
cheapest to reject.

### D-14 · Git runs through PowerShell; file writes run through Bash

**Decision.** All git commands use the PowerShell tool. File authoring uses Bash heredocs or the
Write tool.

**Alternatives considered.**
1. `git config --global --add safe.directory C:/Users/.../storeops-harness-python`, making Bash work.
2. Use PowerShell for everything.
3. Split by capability — chosen.

**Rationale.** This corrects an error from Phase 0. I reported the dubious-ownership blocker as
non-existent because `git status` worked; it worked *in PowerShell*, and I generalised from one
shell to both. Re-verified in Phase 2: the same command in Bash fails with
`fatal: detected dubious ownership`, and `git config --global --get-all safe.directory` confirms no
exception exists for this repo. The sandboxed Bash tool runs under a restricted token — it also
cannot write `/etc/*` — so ownership resolves differently there.

Option 1 would work but mutates global git configuration on a machine that hosts other
repositories, to fix a tool-routing problem that has a zero-config answer. Rejected as
disproportionate.

**Assumption it depends on.** That the PowerShell tool remains available for git. If a later phase
runs in a bash-only context (CI, a container), option 1 becomes necessary — worth noting because
`.github/workflows/ci.yml` in Phase 6 runs on Linux where this cannot arise.

### Phase 2 insight

Writing `architecture-principles` was the first point where the harness had to state a rule it
could not fully enforce. `lint-imports` checks direct imports only (D-06), so a boundary breach
laundered through an intermediary module passes. The temptation was to leave that unsaid — the
contract report says "8 kept, 0 broken", which reads like total coverage.

Stating the gap in the skill file instead has a second-order effect on Phase 4: the Evaluator now
has a written obligation to *read the publish path* rather than treat a green `lint-imports` as
proof of Rule 2 compliance. An honest statement of what a gate does not cover is what turns the
Evaluator's LLM-assessed portion from duplicated effort into the part that actually adds
detection. A skill file that overclaims its automation would have made the human review redundant
in exactly the place it is most needed.

---

## Phase 3 — Generator agent and implementation skills (2026-09-04)

### D-15 · Rules and mechanics are separate skill files, not one merged file

**Decision.** `architecture-principles` states the five rules and is read by Planner, Generator and
Evaluator. Four further files — `component-patterns`, `app-error-contract`, `event-bus-integration`,
`how-to-test` — state the implementation mechanics and are read by the Generator **only**.

**Alternatives considered.**
1. One large `architecture-principles` containing rules and code templates, read by all three.
2. Four Generator files that restate the rules alongside the mechanics, dropping the shared file.
3. Rules shared, mechanics Generator-only, with an explicit stated boundary at the top of each
   file — chosen.

**Rationale.** The decisive argument is what the Evaluator must *not* see. If the Evaluator reads
implementation templates, it grades the code against a restatement of the code — the template
becomes the specification, and any defect the template shares is invisible. Keeping the Evaluator on
rules-and-consequences means it assesses whether the rule holds, not whether the shape matches.

Option 1 also loses on cost: `architecture-principles` is loaded by three agents per iteration, so
every line of Generator-only template would be paid three times to be useful once. Option 2 is the
duplication trap already rejected in D-11 — two files stating the module boundary rule means one is
eventually wrong, and PDF section 11 is explicit that a great submission is one where every file
earns its place.

Each of the four Generator files therefore opens with a stated boundary ("that file states the rule
and why; this file is how you type the code that obeys it") so a reviewer can see the split is
intentional rather than accidental overlap.

**Assumption it depends on.** That the Evaluator can judge Rule 2 compliance from
`architecture-principles` alone, without the publish-order detail in `event-bus-integration`. This
is the weakest assumption in the phase — publish-before-persist is a real defect that
`architecture-principles` describes only in prose. If the Phase 5 run shows the Evaluator missing
ordering defects, the fix is to move the validate→persist→publish ordering rule *up* into
`architecture-principles` Rule 2, not to hand the Evaluator the templates.

### D-16 · One narrow exception to the raw-exception ban: bulk aggregators

**Decision.** `except AppError` is permitted in a bulk aggregator **in the service layer** and
nowhere else. Stated as an explicit exception in both `component-patterns` and
`app-error-contract`.

**Alternatives considered.**
1. Ban `except AppError` outright; have the bulk method pre-validate every item before writing any.
2. Have the bulk method inspect each item without calling the single-item service method.
3. Permit the catch, narrowly scoped and documented — chosen.

**Rationale.** Option 1 sounds cleaner and is worse. Pre-validating all items then writing all
items means the validation logic exists twice — once as a predicate, once inside
`update_status` — and the two drift. It also cannot express per-item failures that only surface at
write time. Option 2 is the same duplication with extra steps, and it breaks the event-count
invariant: an aggregator that does its own writing has to publish its own events, which is exactly
where an N+1 defect appears.

Option 3 keeps `update_status` as the single place the transition rule lives, so N successful items
publish exactly N events with no additional code — the counting invariant falls out of reuse. The
cost is one permitted catch, which is why it is named with its layer and its purpose rather than
left as a judgement call.

**Assumption it depends on.** That the exception stays narrow. It is written as "a bulk aggregator
in the service layer, and nowhere else, and never in a route", and `ruff BLE001` still catches the
broader `except Exception`. The residual risk is a Generator reading this as general licence to
catch `AppError` in services; the Evaluator's HG-2 check must therefore treat any `except AppError`
outside a bulk aggregator as a finding.

### D-17 · The Generator declares its own test quality in the summary

**Decision.** `generator-summary.md` includes a Tests-added table with per-test columns for
*asserts state / error code / event count / audit count*.

**Alternatives considered.**
1. List tests added, without claims about what they assert.
2. Have the Evaluator derive it by reading every test.
3. Require the Generator to self-declare per assertion type — chosen.

**Rationale.** HG-3 is the hardest gate to automate: `pytest --cov` proves a test *ran*, not that it
*asserted anything meaningful*, and coverage is precisely the metric the original failure mode
gamed. Option 2 works but makes the Evaluator's most expensive check also its least structured —
it must reconstruct the claim before it can test it. A self-declaration turns the check into
verification: the Evaluator reads a specific claim ("asserts audit count == 2") and confirms or
refutes it at a named line, which is both cheaper and produces a sharper finding.

The self-declaration is not trusted. It is an assertion the Evaluator falsifies, and a false `yes`
is a more serious finding than an admitted `no` — which the agent file states outright, because an
agent that believes honest gaps are punished will learn to hide them.

**Assumption it depends on.** That the Evaluator actually spot-checks the table rather than reading
it as evidence. If it does not, this decision makes things *worse* than option 2 by supplying a
plausible-looking claim in place of a check. Phase 4's `how-to-review` must therefore require
opening at least the tests behind any `yes` in the event-count and audit-count columns.

### Phase 3 insight

Writing `how-to-test` exposed that coverage and assertion quality are independent, and that only
one of them is automatable. A status-only test executes the entire endpoint and reports ~100%
coverage while asserting nothing — so the 80% floor in `pyproject.toml` and HG-3 are not two
strengths of the same control, they are one automated check plus one irreducibly LLM-assessed
check. Phase 4 must not let the green coverage number stand in for the assertion check, because
the original client failure was a green suite that certified nothing.

The practical consequence is a rule now written into `how-to-test`: side-effect assertions use
`==` with an exact count, never `>=`. An implementation that publishes one event per *requested*
id rather than per *successful* update passes `>= 1` and fails `== 2`. That single character is
the difference between detecting FM-4 in the demonstration run and shipping it.

---

## Phase 4 — Evaluator, Monitor and the evaluation framework (2026-09-04)

### D-18 · A failed hard gate suppresses the score entirely

**Decision.** Once any of HG-1…HG-8 fails, the Evaluator emits `FAIL` and **computes no weighted
score at all**. The document records `not computed — gate failed`.

**Alternatives considered.**
1. Always compute the score, and let the gate override it in the verdict.
2. Compute it and record it alongside the failure, marked "informational".
3. Do not compute it — chosen.

**Rationale.** Options 1 and 2 are the same mistake at different volumes: they put a number next to
a blocker and invite the reader to weigh them. A human reading "HG-1 FAILED / score 92" will
reasonably wonder whether 92 is good enough, and that question should not be askable. The brief
says a score can never override a gate; the cleanest enforcement is to make the comparison
unavailable rather than merely disallowed.

There is also a determinism argument. Scoring a broken sprint means scoring code whose architecture
is known-invalid, where several checks are unanswerable — is check 1.5 "publish path correct" a
pass when the publish path was replaced by a direct write? A number derived from unanswerable
checks is worse than no number.

**Assumption it depends on.** That the Monitor's trend table tolerates a missing score. It does —
the field is itself the signal, and the gate-results row carries what the score would have. If a
future analysis wants score-over-time across failed iterations, this decision blocks it; accepted,
because gate-failure counts are the more useful trend.

### D-19 · Dimension scores are derived from fixed binary checklists, not assigned by judgement

**Decision.** Each dimension is a fixed list of binary checks (6/6/5/5/4 = 26 total).
`dimension score = passed / total × 100`; the weighted score is the sum.

**Alternatives considered.**
1. The Evaluator assigns each dimension 0–100 by judgement against a description.
2. Bands (excellent / adequate / poor) mapped to numbers.
3. Fixed binary checklists with derived arithmetic — chosen.

**Rationale.** The rubric requires verdict rules that "produce the same outcome given the same check
results". Option 1 fails outright — the same code scores differently across runs because "how good
is the test quality?" has no fixed answer. Option 2 only relocates the problem: the band boundaries
become the judgement call, and an assessor under pressure drifts toward the generous band.

Binary checks push the non-determinism down to the smallest unit, where it is most tractable: "does
this test assert an audit count?" has one answer, verifiable by opening one file. Twenty-six such
answers then determine the score arithmetically. The score stops being an opinion and becomes a
derived value, which is the entire point of the instrument.

**Assumption it depends on.** That the checklists are complete enough that a real defect fails at
least one check. This is the assumption most likely to be wrong and it is not testable in advance —
only the demonstration run will show whether a defect can pass all 26. If one does, the fix is a
new check in the relevant dimension, not a return to judgement scoring.

### D-20 · The Evaluator is denied the four Generator implementation skills

**Decision.** The Evaluator reads `architecture-principles`, `how-to-review` and
`evaluation-criteria` only — not `component-patterns`, `app-error-contract`,
`event-bus-integration` or `how-to-test`.

**Alternatives considered.**
1. Give the Evaluator every skill file — more context, better review.
2. Give it the Generator skills but not the Planner's.
3. Rules and review method only — chosen.

**Rationale.** This is D-15 applied to the Evaluator, and it is counter-intuitive enough to state
plainly: withholding context here *improves* detection. If the Evaluator reads
`component-patterns`, its check silently becomes "does this code match the template?" instead of
"does this code obey the rule?" — and any defect the template itself contains becomes structurally
invisible, because reference and artefact agree. The Evaluator's independence comes from assessing
against the rule and its consequence, which is what `architecture-principles` supplies.

It is also a cost argument: `component-patterns` and `how-to-test` together are ~600 lines the
Evaluator would pay for every iteration to obtain a worse check.

**Assumption it depends on.** That `architecture-principles` states every rule the Evaluator must
enforce in consequence terms, without the mechanics. Already known to be imperfect — the
validate→persist→publish ordering rule lives in `event-bus-integration` and appears in
`architecture-principles` only as prose. `how-to-review` compensates by naming publish ordering as
one of three explicit automation blind spots to check by hand. If the demonstration run shows
ordering defects passing, the fix is to promote that rule into `architecture-principles` Rule 2 —
not to hand over the templates.

### D-21 · The Monitor never reads `app/`

**Decision.** The Monitor's inputs are `evaluator-feedback.md`, `generator-summary.md`, the
contract and prior run logs. It does not open application source at all.

**Alternatives considered.**
1. Let it read the diff so log entries are self-contained.
2. Let it read `app/` to sanity-check the Evaluator's findings.
3. Files-on-disk only, no source — chosen.

**Rationale.** Option 2 creates a second, competing assessment: if the Monitor can check findings,
it can disagree with them, and the archive stops being a record of what was decided and becomes an
opinion about whether the decision was right. That destroys its evidential value — a reviewer
auditing an acceptance decision needs to know what the Evaluator concluded, not what the Monitor
made of it. The prohibition on reinterpreting findings only holds if the Monitor lacks the means to
form its own view. Option 1 is milder with the same defect in miniature, and it would make the
Monitor the most expensive agent in the loop rather than the cheapest.

**Assumption it depends on.** That `evaluator-feedback.md` is complete enough to log from. Enforced
by making every section of that schema mandatory — if the Evaluator omits findings, the Monitor
records the omission rather than going to look for them.

### Phase 4 insight

The validation script written to check "weights sum to 100" caught something I was not looking for:
`evaluation-criteria` documented all three verdicts in its rules table but only ever showed the
literal string `VERDICT: PASS` in its emitting section. Since the orchestrator string-matches the
marker, an Evaluator issuing a conditional pass had no exact spelling to copy — and the likely
improvisations (`VERDICT: Conditional Pass`, `VERDICT: CONDITIONAL-PASS`) route nowhere, which
would have surfaced as the loop silently stalling rather than as an error.

The general lesson restates Phase 1's: a machine-readable contract needs a machine-checked
assertion. Three of the four defects found in this build so far came from writing a check rather
than re-reading the artefact — the import-linter false positives, the route-introspection
breakage, and now a missing verdict literal in the very file whose job is removing ambiguity from
the verdict. Phase 5's demonstration run should be treated as another such check, not a formality.
