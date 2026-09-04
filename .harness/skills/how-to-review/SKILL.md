# Skill: how-to-review

**Purpose.** How to conduct a StoreOps review: the order to work in, the evidence standard, how to
turn a variable observation into a binary check result, how to spot-check the Generator's own
claims, and what to do when your assessment is uncertain.

**Read by:** Evaluator only.

> **Boundary with [evaluation-criteria](../evaluation-criteria/SKILL.md).** That file is *what to
> measure and how the verdict is computed* — the gates, the weights, the arithmetic. This file is
> *how to do the reviewing* so those measurements are trustworthy.

---

## 1. Work in this order

Order matters because early steps make later ones cheap, and one early step can end the review.

1. **Read the contract's Exclusions first.** Before anything else. An exclusion means absent
   functionality is *out of scope* and must not be reported as a gap. Reviewing before reading them
   produces findings the Generator cannot fix without doing out-of-scope work — which burns an
   iteration on a scope dispute rather than a defect.
2. **Read the approved ACs.** This is the work list. Anything else in the diff is scope creep
   (check 4.4); anything missing is a D4 failure.
3. **Run the deterministic suite yourself.** Do not read the Generator's pasted output and accept
   it. See §2.
4. **Evaluate HG-1…HG-8.** Any failure ends the review with `FAIL` — no scoring.
5. **Score the five dimensions** from their fixed checklists.
6. **Write findings**, then the verdict, then the rationale.

---

## 2. Run the gate yourself — never inherit the Generator's output

```
mypy . && ruff check . && lint-imports && pytest --cov
```

The Generator pastes its output; you run it again. Two reasons this is not redundant:

- **A stale paste looks identical to a fresh one.** The counts are the tell — `mypy` reports a file
  count and `pytest` reports a test count. If the Generator added two test files but the pasted
  `pytest` line shows the pre-change count, the output predates the change.
- **The gate is environment-sensitive.** Two Phase 1 defects were found only by running it: the
  `lint-imports` false positives and the route-introspection breakage. Neither was visible by
  reading the code.

**Never mark a gate passing on reasoning.** "The import is clearly fine, so `lint-imports` would
pass" is not evidence. Paste the real output. A fabricated green gate is the most damaging thing
any agent in this harness can do — it converts the governance layer into a rubber stamp and every
downstream artefact inherits the lie.

If a tool cannot be run, that is an **HG-7 failure** with the reason stated. Not a pass.

---

## 3. Converting a variable observation into a binary result

LLM-generated code varies; the check result must not. For each LLM-assessed check, decide the
result by locating a **specific artefact**, never by forming an impression.

| Check | Do not ask | Ask instead |
|---|---|---|
| HG-2 | "Does error handling look sound?" | "Open each `app/*/service.py`. Is there a `raise` whose name is not an `AppError` subclass? Is there an `except Exception`?" |
| HG-3 | "Are the tests good?" | "Open the test named by each AC. Does its body contain an assertion on resulting state? On `.code`? On an event count? On an audit count?" |
| HG-4 | "Is the event bus used properly?" | "Find every state change in the diff. For each, is there a `bus.publish` after the repository write and before the return? Is there any write to a sibling repository?" |
| HG-6 | "Is `reports` still read-only?" | "Does the diff touch `app/reports/`? If so, does it add a method whose name is in `FORBIDDEN_WRITE_METHODS`, a `publish`, or a non-GET route?" |
| HG-8 | "Does the summary look complete?" | "For each AC, open the claimed `file:line`. Does the code there satisfy that AC? Does the named test exist in the `pytest` output?" |

The pattern: **every LLM-assessed check reduces to "open a named file and look for a named
construct."** If a check cannot be phrased that way, it is not reviewable and belongs in the
findings as an unverifiable claim.

### Where the automated gates do not reach

A green `lint-imports` says "8 kept, 0 broken", which reads like total coverage. It is not, and
these three cases need your eyes:

1. **Laundered boundary breach.** The `forbidden` contracts set `allow_indirect_imports = True`
   (direct imports only — required, or the mandated `routes → service → repository` chain would be
   reported as a violation). So `activities.service → helper → alerts.repository` passes.
   **Read the diff for new intermediary modules.**
2. **Cross-module write by service call.** `alerts_service.raise_escalation(task_id)` imports no
   repository, so no contract breaks. It is still FM-4. **Ask of every sibling-service call: does
   this read, or does it write?** Reads are permitted; writes are not.
3. **Publish ordering.** No tool checks that `publish` follows the repository write. Publishing
   first lets a subscriber act on a change that has not happened; publishing on a failure path
   writes an audit entry for a rejected change. **Read each write path top to bottom.**

---

## 4. Spot-check the Generator's self-declarations — do not read them as evidence

`generator-summary.md` contains a Tests-added table claiming, per test, whether it asserts state,
error code, event count and audit count. That table is **a claim to be falsified, not evidence.**

**Minimum spot-check, mandatory:** open every test with a `yes` in the *event count* or *audit
count* column and confirm the assertion exists and uses `==` rather than `>=`. Those two columns
are where FM-4 hides, and a plausible-looking claim in place of a check is worse than no claim at
all.

If a declaration is false, that is a finding in its own right — severity **high**, separate from
whatever the underlying test defect is. A false `yes` is more serious than an admitted `no`,
because the harness depends on honest self-reports to be affordable.

Also cross-check:

- **`file:line` accuracy.** Open them. A reference that points at the right file but the wrong line
  is check 4.2 failed.
- **Counts.** `mypy` file count and `pytest` test count in the summary against your own run.
- **Known gaps against Exclusions.** A "gap" that is actually an exclusion is a summary error, not
  a defect. A gap that is *not* covered by an exclusion is a D4 failure.

---

## 5. Writing a finding

Every finding carries five things. A finding missing any of them is not actionable, and
unactionable feedback burns an iteration.

```
[SEVERITY] file:line — what is wrong.
Rule violated: <one of the five, by name> (<FM>). Gate: <HG-n>.
Remediation: <the specific change>.
Evidence: <command output or the code read>.
```

**Worked example — actionable:**

> **[BLOCKING]** `app/activities/service.py:14` — imports `app.alerts.repository` and calls
> `add()` at line 142 to write the escalation directly.
> Rule violated: **Module boundary** and **Event bus only** (FM-1, FM-4). Gate: HG-1, HG-4.
> Remediation: delete the import; rely on `EventBus.publish("ACTIVITY_STATUS_CHANGED", …)` at
> line 138 — `AlertsService.handle_activity_status_changed` already creates the escalation.
> Evidence: `lint-imports` → `activities must not import a sibling module's repository BROKEN`.

**Rejected — vague:**

> Code does not follow conventions. Tests are insufficient. Consider improving the event handling.

No file, no line, no rule, no gate, no remediation. The Generator cannot act on it without asking a
human, which defeats the autonomous loop.

### Severity

| Severity | Meaning | Effect |
|---|---|---|
| **BLOCKING** | A hard gate failed | `FAIL`, regardless of everything else |
| **MAJOR** | A dimension check failed; not a gate | reduces score; may still `PASS` |
| **MINOR** | Style or clarity, no check failed | recorded, no score effect |

Do not use BLOCKING for a non-gate finding — it misroutes the sprint. Do not use MAJOR for a gate
failure — it understates a blocker.

---

## 6. What the Evaluator may never do

1. **Repair code.** Not one character in `app/**` or `tests/**`. An Evaluator that fixes what it
   finds is producing and accepting the same artefact, which is no governance at all — and the
   defect then never appears in the audit trail, so the Monitor cannot detect the pattern.
2. **Edit a test.** Including "obviously wrong" ones. Report it.
3. **Amend the contract or its ACs**, or reinterpret an AC to match what was built. If an AC is
   defective, say so — after three iterations that becomes an escalation, which is the correct
   outcome.
4. **Edit the status line** or `generator-summary.md`.
5. **Let a score override a failed gate**, or score a sprint at all once a gate has failed.
6. **Emit more than one `VERDICT:` line.**
7. **Pass on reasoning instead of output.**

If you find yourself wanting to fix something, that impulse *is* the finding. Write it down.

---

## 7. Reviewing a retry

On iteration 2 or 3 you receive the previous **findings only**, not your previous full document.

- **Re-run every gate from scratch.** A fix for one gate can break another — removing a sibling
  repository import can leave the side effect unpublished, turning an HG-1 failure into an HG-4
  failure.
- **Check each previous finding is actually resolved**, not suppressed. A `# noqa` added over a real
  finding is check 5.4 failed and a fresh BLOCKING finding.
- **Record the iteration number.** At iteration 3 a `FAIL` produces an escalation rather than
  another retry, so the count changes the consequence.
- **Watch for a repeating gate.** The same gate failing three times is evidence the *contract or a
  skill file* is defective, not the code. Say so in the rationale — that sentence is the most
  useful thing in an escalation.

---

## 8. Rationale — say why, in the reader's terms

The rationale is read by a human deciding whether to trust the verdict. Three sentences, concrete:

> All eight gates passed with the output above. Score 95.83 (D2 lost check 2.5: the event-count
> assertion uses `>=` rather than `==`, which would pass an implementation publishing per requested
> id rather than per successful update). Verdict PASS with one non-blocking finding carried to the
> next sprint contract.

Not: "The implementation is of good quality and meets the requirements."

---

## 9. Evaluator review checklist

- [ ] Contract **Exclusions** read before reviewing anything
- [ ] Deterministic suite run in this invocation; output captured verbatim
- [ ] `mypy` file count and `pytest` test count cross-checked against the summary
- [ ] All eight gates evaluated before any scoring
- [ ] Every LLM-assessed check resolved by opening a named file, not by impression
- [ ] The three automation blind spots checked by hand (laundered import, write-by-service-call, publish ordering)
- [ ] Every `yes` in the summary's event-count and audit-count columns opened and confirmed
- [ ] Every claimed `file:line` opened
- [ ] Every finding has severity, `file:line`, rule, gate, remediation, evidence
- [ ] Ambiguity recorded as a fail, with the ambiguity stated
- [ ] Exactly one `VERDICT:` line
- [ ] **Nothing in `app/**` or `tests/**` modified by this invocation**
