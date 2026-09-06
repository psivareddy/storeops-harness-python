# Reflection

## What the harness caught

The approval checkpoint caught two real events, not staged ones — recorded in
`sprint-1-run-log.md` under "Approval-checkpoint events". The Generator was invoked once against
`STATUS: AWAITING APPROVAL` and once against a human typo, `STATUS: AAPPROVED`; both times it
refused and wrote nothing. The second refusal is the more informative of the two: a naive
precondition implemented as a substring search for `"STATUS: APPROVED"` would have matched the
contract's own explanatory prose at line 11 and proceeded against an unapproved contract. The
check had to be last-line equality, not containment — a distinction this run surfaced by accident
rather than by design, and one now carried as a follow-up against `planner.agent.md` and
`generator.agent.md`.

The Evaluator's independent re-execution of the gate also caught something the Generator's
self-report could not have: the Generator's own `generator-summary.md` originally cited six
`file:line` references that were off by one to three lines each. These were machine-verified and
corrected before the Evaluator ran, which means the harness's separation-of-duties design worked
even where the fabrication would have been mine, not the Generator's.

## What it missed

Sprint 1 passed with a weighted score of 100.00 and zero MAJOR or BLOCKING findings, yet three
MINOR findings — all in skill files, all pre-dating this sprint — survived the entire pipeline:
`app-context/SKILL.md` still claimed 9 endpoints and named the pre-rename inventory test at line
72; `component-patterns/SKILL.md` §6 and `how-to-test/SKILL.md` §4 showed the bulk response as
`succeeded`/`failed` arrays when the approved contract specifies `updated`/`failed`/`results`; and
`component-patterns/SKILL.md` §6 showed an all-fail batch returning HTTP 200 when contract
assumption A-2 requires 207. None of the 26 binary checks in `evaluation-criteria/SKILL.md`
measures skill-file/contract consistency, so all three produced zero deduction. The Evaluator
noticed this gap itself and proposed a new D4 check ("no skill file or contract references a
symbol the diff renamed or removed") — recorded in the run log, not yet implemented, because
implementing it mid-demonstration would have erased the evidence that the gap exists.

Sprint 1 also never exercised the escalation path. It passed on iteration 1, so
`.harness/output/escalation.md` was never written and the three-iteration bound is verified only
by specification (`CLAUDE.md` §4), not by a real FAIL-FAIL-FAIL run. That is disclosed rather than
simulated, per DESIGN_BRIEF.md Section C.

## Iteration history

One iteration, one verdict: `PASS`, 8/8 hard gates, weighted score 100.00
(D1 35.00/35, D2 25.00/25, D3 15.00/15, D4 15.00/15, D5 10.00/10 — `sprint-1-run-log.md`). The
run's own analysis attributes the clean first pass to the contract being *more specific* than the
skill files it was implemented alongside: `sprint-1-contract.md` fixed the bulk response shape and
the 207-on-all-fail status code explicitly, so `generator.agent.md` §2's precedence rule (the
approved contract outranks a skill file example) absorbed a defect the stale `component-patterns`
example would otherwise have injected. Had the Generator followed the skill file's own worked
example instead of the contract, AC-5 would have failed on the status code and all six ACs would
have failed on the response body shape — a genuine iteration-1 FAIL caused by a skill-file defect,
not a code defect.

## Cost and context observations

The run log estimates ~82,600 tokens for the full Planner→Generator→Evaluator→Monitor iteration,
by summing the bytes each agent's declared skill reads plus its contract/summary inputs and
dividing by four. The Generator was the most expensive single invocation at roughly 37% of the
total, driven by six skill files totalling 74 KB. `app-context` (7.8 KB) is read by all four
agents every iteration, so its length alone costs roughly 7,800 tokens of pure orientation per
iteration — the exact trade `CLAUDE.md` §5 names as deliberate ("every extra line is paid four
times"), now measured for the first time rather than asserted.

## One concrete improvement

Add the Evaluator's own proposed check — call it D4.6 — that fails a sprint when a skill file or
the contract references a symbol (test name, endpoint count, response field) that the diff renamed
or removed. The trade-off: it requires the Evaluator to diff skill-file prose against the actual
code change, which is exactly the kind of judgment call `how-to-review/SKILL.md` currently reserves
for findings rather than gates — turning it into a gate raises the bar for what counts as a
passing sprint, and would very likely have turned sprint 1 into a `CONDITIONAL PASS` rather than a
clean `PASS`, carrying the three skill-file fixes forward as an explicit, tracked obligation instead
of a footnote in the run log.
