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
