# Skill: evaluation-criteria

**Purpose.** The deterministic scoring instrument: eight hard gates each traced to a failure mode,
five weighted dimensions summing to exactly 100%, and verdict rules that produce the same outcome
given the same check results.

**Read by:** Evaluator only.

> **Boundary with [how-to-review](../how-to-review/SKILL.md).** This file is *what to measure and
> how the verdict is computed*. That file is *how to conduct the review* — gate order, evidence
> standards, how to convert a variable observation into a binary result, and what to do when your
> own assessment is uncertain.

---

## 1. Order of operations — non-negotiable

```
1. Run the deterministic suite. Capture real output.
2. Evaluate HG-1 .. HG-8.  Any gate FAIL  ->  VERDICT: FAIL. STOP. Do not score.
3. Only if all eight gates pass: score the five dimensions.
4. Apply the verdict rules in section 5.
```

**Hard gates are evaluated BEFORE scoring, and a score can never override a failed gate.** A
boundary breach in code that is otherwise 98% quality is still a boundary breach: it cannot be
safely merged, so there is no score that should let it through. Scoring a failed-gate sprint at all
is a defect in the review — it invites the reader to weigh a number against a blocker.

---

## 2. The hard gates — the failure-mode matrix

**Evidence required by the capstone brief. Every gate maps to at least one of the four failure
modes observed in the client's prior AI experiment.**

| Gate | Check | → FM | Detection | Type |
|---|---|---|---|---|
| **HG-1** | Zero direct imports of another module's `repository` | **FM-1** | `lint-imports` — the five `*-no-cross-module-repository` contracts | automated |
| **HG-2** | Every failure is an `AppError` subclass; no raw exception escapes a service or route | **FM-2** | `ruff` `TRY002`/`TRY301`/`BLE001` + `tests/test_architecture.py::test_services_raise_no_bare_exceptions` + review | automated + LLM |
| **HG-3** | Every business test asserts resulting state, `AppError.code`, event count, audit count. Status-only assertion fails. Coverage ≥ 80% | **FM-3** | `pytest --cov` (coverage) + review of the named tests | automated + LLM |
| **HG-4** | Cross-module side effects go through `EventBus.publish`; no direct sibling-repository write and no cross-module write by service call | **FM-4** | `lint-imports` + review of the publish path | automated + LLM |
| **HG-5** | No `routes.py` imports any `repository`; no business rule in a route | **FM-1, FM-4** | `lint-imports` `routes-never-import-repositories`, `module-layers` + `tests/test_architecture.py::test_routes_never_import_a_repository` | automated |
| **HG-6** | No write originates in `app/reports/`: no sibling mutation, no event published, no row created | **FM-1, FM-4** | `lint-imports` `reports-reads-only-via-services` + `tests/reports/test_reports_read_only.py` | automated |
| **HG-7** | `mypy . && ruff check . && lint-imports && pytest --cov` exits 0 | **all four** | the command itself | automated |
| **HG-8** | Every approved AC has an accurate `file:line` implementation reference **and** a named test that exists and passes | **FM-3** | `generator-summary.md` cross-checked against the repository | LLM-verified |

All four failure modes are gated. FM-1 by HG-1/HG-5/HG-6, FM-2 by HG-2, FM-3 by HG-3/HG-8, FM-4 by
HG-4/HG-5/HG-6.

### HG-8 exists as a gate, not a scoring item

"Missing evidence for a required AC → FAIL" is a *verdict rule* in the brief. It is implemented
here as a **gate** so it is checked deterministically before scoring, rather than becoming a
deduction that a strong score could absorb. An unevidenced AC is an unimplemented AC; accepting it
on assertion is precisely the rubber-stamp failure this harness exists to prevent.

### Why none of these can be a soft check

| Gate | Why it cannot be a deduction |
|---|---|
| HG-1 | A boundary breach silently couples two modules. Partial credit merges the coupling. |
| HG-2 | The error contract is binary — a raw raise returns an untyped 500 with no code to branch on. |
| HG-3 | A status-only test is worse than no test: a green suite that certifies nothing. |
| HG-4 | An unpublished side effect leaves no audit entry, so it is invisible to operations. |
| HG-5 | A rule in a route is unreachable from an event handler, so the same change bypasses validation by another path. |
| HG-6 | One write makes `reports` a second source of truth; a reporting bug can then corrupt operational data. |
| HG-7 | This is the CI gate. A red suite cannot be merged regardless of how good the design looks. |
| HG-8 | An AC accepted on assertion converts the contract into a suggestion. |

---

## 3. The weighted dimensions

**Evidence required by the capstone brief. Weights sum to exactly 100%.**

| # | Dimension | Weight | Gates it carries | Automated check (PDF §5.4) |
|---|---|---:|---|---|
| **D1** | Architecture Compliance | **35%** | HG-1, HG-4, HG-5, HG-6 | `lint-imports` |
| **D2** | Test Quality & Business-Rule Coverage | **25%** | HG-3 | `pytest --cov`, `fail_under = 80` |
| **D3** | Error Contract Integrity | **15%** | HG-2 | `ruff` TRY/BLE + `mypy` |
| **D4** | Contract Fidelity | **15%** | HG-8 | named-test existence and pass |
| **D5** | Toolchain Cleanliness | **10%** | HG-7 | `mypy . && ruff check . && lint-imports && pytest --cov` |
| | **TOTAL** | **100%** | HG-1…HG-8 | every dimension has ≥ 1 automated check |

**Why these five for StoreOps.** D1 carries the largest weight because three of the four failure
modes are boundary or layering failures, and they are the ones that compound — a breach merged
today makes the next breach cheaper. D2 is second because FM-3 defeats *every other control*: a
green suite that asserts nothing makes D1 and D3 unverifiable. D3 and D4 are equal and mid-weight:
both are contract integrity, one with the client, one with the approver. D5 is smallest not because
it matters least but because it is fully automated and binary — it needs no judgement, so weight
spent there buys no discrimination.

### Scoring: dimension score = passed checks / total checks × 100

Each dimension is a fixed checklist of binary checks. This is what makes the score reproducible:
given the same check results, the arithmetic is fixed. **Never assign a dimension score by
impression.**

```
weighted score = Σ (dimension_weight × passed_checks / total_checks)
```

#### D1 — Architecture Compliance (35%), 6 checks

| # | Check | Passes when |
|---|---|---|
| 1.1 | No sibling repository imported | `lint-imports` reports all 5 `*-no-cross-module-repository` contracts KEPT |
| 1.2 | No route imports a repository | `routes-never-import-repositories` KEPT |
| 1.3 | Layer ordering intact | `module-layers` KEPT |
| 1.4 | `app.shared` imports no business module | `shared-is-infrastructure-only` KEPT |
| 1.5 | Cross-module side effects published, not called | publish path read; no cross-module write by service call |
| 1.6 | `reports` performs no write | `reports-reads-only-via-services` KEPT and read-only tests pass |

#### D2 — Test Quality & Business-Rule Coverage (25%), 6 checks

| # | Check | Passes when |
|---|---|---|
| 2.1 | Every named test in the contract exists | each `path::name` resolves |
| 2.2 | Every named test passes | present in the `pytest` run |
| 2.3 | Resulting state asserted | state read back, not inferred from the response body |
| 2.4 | `AppError.code` asserted on every error path | not the HTTP status alone |
| 2.5 | Event counts asserted with `==`, not `>=` | exact counts, including zero on failure paths |
| 2.6 | Coverage ≥ 80% and not materially below the 99.63% baseline | `pytest --cov` output |

#### D3 — Error Contract Integrity (15%), 5 checks

| # | Check | Passes when |
|---|---|---|
| 3.1 | No builtin or bare raise in a service | `ruff` clean + AST test passes |
| 3.2 | No `HTTPException` in any service | source read of `app/**/service.py` |
| 3.3 | No `except Exception` / bare `except` | `ruff BLE001` clean |
| 3.4 | No error returned as a dict or `None` from a service | source read |
| 3.5 | Any new `AppError` subclass has a unique code, a family base, and is named in the contract | duplicate-code test + contract |

#### D4 — Contract Fidelity (15%), 5 checks

| # | Check | Passes when |
|---|---|---|
| 4.1 | Every AC implemented or listed in Known gaps | `generator-summary.md` |
| 4.2 | Every `file:line` reference accurate | opened and confirmed |
| 4.3 | No approved AC altered | contract diffed against the approved text |
| 4.4 | Nothing written outside the contract's allowed scope | diff reviewed |
| 4.5 | Contract Exclusions respected and **not** reported as gaps | exclusions read first |

#### D5 — Toolchain Cleanliness (10%), 4 checks

| # | Check | Passes when |
|---|---|---|
| 5.1 | `mypy .` clean | 0 errors, file count plausible for the diff |
| 5.2 | `ruff check .` clean | 0 findings |
| 5.3 | `lint-imports` 8/8 kept | 0 broken |
| 5.4 | No gate weakened to achieve green | no lowered `fail_under`, deleted contract, or new `# type: ignore` / `# noqa` masking a real finding |

### Worked arithmetic

All gates pass. D1 6/6, D2 5/6 (event counts used `>=`), D3 5/5, D4 5/5, D5 4/4:

```
D1 35 × 6/6 = 35.00
D2 25 × 5/6 = 20.83
D3 15 × 5/5 = 15.00
D4 15 × 5/5 = 15.00
D5 10 × 4/4 = 10.00
                -----
        score =  95.83   ->  no gate failed and score >= 85  ->  VERDICT: PASS
```

Note check 2.5 failed on a *style* of assertion while HG-3 still passed, because the tests did
assert counts. Had they asserted status alone, HG-3 would have failed and the score would never
have been computed.

---

## 4. Ambiguity resolves toward FAIL

For any check where the evidence does not clearly establish a pass, record **fail**, and state the
ambiguity in the finding. The harness fails closed.

The reasoning is asymmetric cost: an unnecessary retry costs tokens; an uncertain accept costs a
production defect and, worse, teaches the loop that uncertainty is passable. This applies to the
gates too — an HG-4 check where the publish path cannot be traced is an HG-4 **failure**, recorded
as "publish path could not be confirmed at `file:line`", not a pass with a caveat.

---

## 5. Verdict rules

Evaluated in order. The first matching row decides.

| # | Condition | Verdict |
|---|---|---|
| 1 | **Any** of HG-1…HG-8 fails | **FAIL** |
| 2 | No gate fails **and** weighted score ≥ 85 | **PASS** |
| 3 | No gate fails, score **75–84**, and every outstanding condition is non-blocking | **CONDITIONAL PASS** |
| 4 | No gate fails **and** score < 75 | **FAIL** |
| 5 | A required AC lacks evidence | **FAIL** (reached via HG-8 at row 1) |
| 6 | The Evaluator's own assessment is ambiguous on any check | **FAIL**, with the ambiguity stated |

### "Non-blocking" is a defined term, not a judgement

A condition is **non-blocking** only if all of these hold:

- it does not violate any of the five architecture rules
- it does not reduce test coverage below 80%
- it does not leave any AC unevidenced
- it can be fixed in a later sprint without changing the approved contract
- it is recorded as a carried condition in the next sprint contract

If any one fails, the condition is blocking and the verdict is `FAIL`. A "minor" boundary breach
does not exist.

### Emitting the verdict

Exactly one line, exactly once, in `evaluator-feedback.md`. One of these three literals, character
for character — the orchestrator string-matches the marker, so a variant spelling routes nowhere:

```
VERDICT: PASS
VERDICT: CONDITIONAL PASS
VERDICT: FAIL
```

Not `VERDICT: Pass`, not `VERDICT: CONDITIONAL-PASS`, not `Verdict: PASS`, and not the marker
followed by a qualifier on the same line.

The orchestrator routes on this marker alone — never on prose, tone, or the score. Do not emit the
marker more than once, do not emit it inside a code fence used for illustration, and do not
decorate it.

---

## 6. Worked example — variable Generator output to a definitive verdict

**Iteration 1.** The Generator implements `PATCH /api/activities/bulk-status`. It works: correct
207 on mixed outcomes, per-item `TASK_NOT_FOUND`, 8 new tests, coverage 99.4%. The summary claims
every AC implemented. By impression this is a strong sprint — a lenient assessor scores it ~92 and
passes it.

Then the gates run:

```
$ lint-imports
Contracts: 7 kept, 1 broken.
activities must not import a sibling module's repository BROKEN
- app.activities.service -> app.alerts.repository (l.14)
```

The Generator wrote the audit entry by importing `app.alerts.repository` and calling `add()`
directly instead of relying on the published event.

**HG-1 fails** → row 1 → **`VERDICT: FAIL`**. The score is not computed. The finding:

> `app/activities/service.py:14` — imports `app.alerts.repository`. Rule violated: **Module
> boundary** and **Event bus only** (FM-1, FM-4). HG-1, HG-4. Remediation: delete the import and
> rely on `EventBus.publish("ACTIVITY_STATUS_CHANGED", …)`; the alerts subscriber already creates
> the escalation. Evidence: `lint-imports` output above.

Re-run the same inputs and the outcome is identical — that is the determinism the instrument buys.
The 92-by-impression is exactly what the hard gate exists to overrule.

**Iteration 2.** The import is gone, `lint-imports` reports 8/8, all gates pass. Scoring finds
check 2.5 failed — the event-count assertion reads `assert len(events) >= 1`, which passes against
an implementation publishing one event per *requested* id rather than per *successful* update.
Score 95.83 → row 2 → **`VERDICT: PASS`**, with a non-blocking finding recommending `== 2`.

Had the same weakness appeared with a status-only test, HG-3 would have failed and iteration 2
would have been another `FAIL` — the difference is whether the assertion is *weak* or *absent*.

---

## 7. Evaluator checklist

- [ ] Deterministic suite run in this invocation, output captured verbatim
- [ ] All eight gates evaluated **before** any scoring
- [ ] Any gate failure → `FAIL`, and no score computed
- [ ] Every dimension scored from its fixed checklist, never by impression
- [ ] Weights confirmed to total 100 and the arithmetic shown
- [ ] Every ambiguous check recorded as a fail with the ambiguity stated
- [ ] "Non-blocking" applied against the five-part definition, not by feel
- [ ] Exactly one `VERDICT:` line
- [ ] Every finding carries `file:line`, the rule violated, the gate, the FM, and a remediation
- [ ] No code, test or configuration file modified by this invocation
