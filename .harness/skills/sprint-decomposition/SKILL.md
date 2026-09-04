# Skill: sprint-decomposition

**Purpose.** How to turn a one-sentence StoreOps feature request into a single reviewable sprint
contract whose acceptance criteria are testable rather than subjective.

**Read by:** Planner only.

This file governs *how the work is sliced and specified*. What the code must obey once sliced is in
[architecture-principles](../architecture-principles/SKILL.md); what already exists is in
[app-context](../app-context/SKILL.md).

---

## 1. One sprint = one reviewable unit

A sprint is the amount of work the Evaluator can accept or reject **as a whole** in one pass. It is
bounded by reviewability, not by effort.

A correctly sized StoreOps sprint:

| Property | Target | Why |
|---|---|---|
| Endpoints added or changed | 1, occasionally 2 | The 9-endpoint inventory test must be updated deliberately, not incidentally |
| Modules **written to** | 1 (plus `app/shared/` if the error contract genuinely needs a new subclass) | Two modules written in one sprint makes a boundary breach hard to attribute |
| Modules **read from** | any number, via their service layer | Reads are cheap and safe (Rule 1) |
| New event types | 0 or 1 | A new event changes the audit surface; it deserves its own review |
| Acceptance criteria | 4–8 | Under 4 usually means the failure paths are missing; over 8 means two sprints |

### Where to draw the boundary

Cut where the **architecture rules change**, not where the code volume feels even. Three cuts that
work in this codebase:

1. **Producer / consumer.** A sprint that publishes a new event and a sprint that consumes it are
   separate. The Evaluator can verify "exactly one event per successful update" without also
   reasoning about what the subscriber did with it.
2. **Read surface / write surface.** Adding `GET /api/reports/region/{id}` is read-only and touches
   Rule 5. Making a programme closure *trigger* a rollup is a write path and touches Rule 2. Never
   the same sprint.
3. **Endpoint / enrichment.** Ship the endpoint with its business rules first. Add pagination,
   filtering or a richer payload second. The first sprint has the failure modes; the second is
   mostly schema.

### Do not cut here

- **Never split "the happy path" from "the error paths."** A sprint that implements the success case
  and defers `TASK_NOT_FOUND` to sprint 2 is unacceptable: FM-2 and FM-3 both hide in the deferred
  half, and the Evaluator cannot pass a feature whose failure behaviour is undefined.
- **Never split "the code" from "the tests."** HG-3 is unsatisfiable in a sprint with no tests, so
  the verdict is a guaranteed FAIL and the iteration is wasted.
- **Never split "publish the event" from "write the audit entry."** The audit entry *is* the
  published event reaching `AuditSink` — they are one behaviour, not two (see Rule 2).

---

## 2. What makes an acceptance criterion testable

An AC is testable when a reader can name the assertion without asking a question. The test is
mechanical: **could two competent engineers disagree about whether it passed?** If yes, rewrite it.

| Subjective — rejected | Testable — accepted |
|---|---|
| "Bulk updates should handle errors gracefully" | "the missing id returns `AppError` `TASK_NOT_FOUND` and the response is HTTP 207" |
| "Performance should be acceptable" | "one repository read per requested id, asserted by call count" |
| "Events are published appropriately" | "exactly one `ACTIVITY_STATUS_CHANGED` event per successful update; zero for failed items" |
| "The endpoint is well tested" | "`test_bulk_status_partial_failure_returns_207` asserts state, error code, event count and audit count" |
| "Reports should stay read-only" | "`report_repository.count()` is unchanged after the call" |

### Quantify side effects, always

StoreOps side effects are **counted**, never merely observed. "An event is published" is satisfied
by publishing three. Every AC that causes an event or an audit entry must state the **number** and
the number for the failure case:

> ...publishes **exactly one** `ACTIVITY_STATUS_CHANGED` per successful update and **exactly one**
> audit entry per successful update; a failed item produces **neither**.

This is the specific defence against FM-4: a duplicated side effect passes a "was an event
published?" check and fails a count.

### Anchor to seed data

Write ACs against the fixtures in [app-context](../app-context/SKILL.md#5-seed-data). `task-4` is
already `DONE`, so "GIVEN a request including `task-4`" *is* the invalid-transition case with no
setup. `task-5` has no assignee. `project-3` is `CLOSED`. An AC naming real fixtures is
immediately implementable; one naming "a completed task" costs the Generator a decision.

---

## 3. The AC template

Every acceptance criterion uses this shape. **Reproduce it exactly** — the Generator's self-check
table and the Evaluator's AC result table both key off these fields.

```
**AC-<n>:** GIVEN <initial state, naming seed fixtures where possible>
WHEN <the single triggering action, naming the endpoint or service method>
THEN <observable outcome 1>, <observable outcome 2>, ... AND <side-effect counts>.

- **Modules:** <module(s) written> (writes); <module(s) read> (reads)
- **Architecture rules:** <which of the 5, by name>
- **Tests:** <path::test_name>[, <path::test_name>]
```

### Worked example

**AC-2:** GIVEN a bulk-status request with 3 task IDs where 1 does not exist, WHEN
`PATCH /api/activities/bulk-status` runs, THEN the 2 valid tasks update, the missing ID returns
AppError `TASK_NOT_FOUND`, HTTP 207 is returned, one event is published per successful update, and
one audit entry is written per updated task (no event/audit for the failed item). Tests must assert
states, error code, events, and audit count — not status alone.

- **Modules:** `activities` (writes); none (reads)
- **Architecture rules:** Layer separation, Error contract, Event bus only
- **Tests:** `tests/activities/test_activities_bulk_status.py::test_partial_failure_returns_207_and_updates_only_valid_tasks`

Note what makes this work: three named outcomes, a named error code, a named HTTP status, a
per-item side-effect count, **and an explicit statement of what does *not* happen** for the failed
item. The last clause is the one an implementation is most likely to get wrong.

---

## 4. Every AC maps to a named test

A criterion with no named test is not acceptance criteria — it is a wish. The Planner names the
test; the Generator must create a test with that exact name; the Evaluator checks it exists, runs,
and asserts the AC's outcomes.

**Naming convention:** `tests/<module>/test_<feature>.py::test_<behaviour_being_asserted>`

The test name states the *behaviour*, not the mechanism:

| Rejected | Accepted |
|---|---|
| `test_bulk_status` | `test_partial_failure_returns_207_and_updates_only_valid_tasks` |
| `test_error_case` | `test_done_task_in_batch_yields_invalid_status_transition_and_no_event` |
| `test_it_works` | `test_all_success_publishes_one_event_per_task` |

One AC may map to several tests. Several ACs may not map to one shared test — if two criteria
collapse into a single assertion, they were one criterion.

### The four required assertions

Any AC whose test touches business behaviour must assert all four that apply (this is HG-3, and
status-only assertion is an automatic FAIL):

1. **Resulting state** — read it back; do not trust the response body alone
2. **Error code** — `AppError.code`, not just the HTTP status
3. **Published events** — type *and count*
4. **Audit entries** — count, via `audit_sink.count_for(...)`

---

## 5. The contract's non-AC sections

Four blocks, all mandatory. They exist because an unstated assumption becomes a defect the
Evaluator cannot attribute.

| Block | Contains | Failure it prevents |
|---|---|---|
| **Assumptions** | What the Planner decided in the absence of instruction, each falsifiable | The Generator silently deciding differently |
| **Dependencies** | Existing symbols the sprint relies on, by path — e.g. `ActivitiesService.update_status`, `ALLOWED_TRANSITIONS` | The Generator reimplementing a rule that already exists |
| **Risks** | Where this sprint could plausibly breach a rule, and which gate would catch it | A reviewer having to rediscover the hazard |
| **Exclusions** | What this sprint deliberately does not do | Scope creep, and an Evaluator marking absent work as a gap |

**Exclusions carry real weight.** "Bulk update does not support reassignment" means the Evaluator
must *not* record missing reassignment as a finding. Without it, correct work looks incomplete.

### Risks, written usefully

State the hazard and its detector:

> **Risk:** the audit entry is the tempting place to write directly to
> `app/alerts/repository.py`, which is FM-4. Detected by `lint-imports`
> (`activities-no-cross-module-repository`) → HG-1/HG-4 FAIL.

Not: "there is a risk of architectural violations."

---

## 6. `spec.md` versus `sprint-N-contract.md`

Two documents with different readers and different lifetimes.

| | `spec.md` | `sprint-N-contract.md` |
|---|---|---|
| Reader | the human approver | the Generator and the Evaluator |
| Answers | *should we build this, and why sliced this way?* | *what exactly must be true for this to be accepted?* |
| Contains | the verbatim feature prompt, the domain rationale, the sprint breakdown table, the module impact map | ACs, assumptions, dependencies, risks, exclusions, the status line |
| Lifetime | written once per feature | one per sprint; amended only by re-planning |
| Approval line | no | **yes — the last line** |

`spec.md` must quote the originating feature prompt **verbatim** so the chain of evidence
`PROMPT.md → spec.md → sprint-N-contract.md → generator-summary.md → evaluator-feedback.md →
run-log.md` resolves. The contract must reference `spec.md` by name for the same reason.

---

## 7. Worked slice — the demonstration feature

**Prompt:** "Shift handover bulk update — `PATCH /api/activities/bulk-status` marking multiple
activities DONE or BLOCKED in one request, with partial-failure handling (HTTP 207), one event
published per successful update, and one audit entry per updated task."

### Sprint count: one

It fits: one new endpoint, one module written (`activities`), no new event type — it reuses
`ACTIVITY_STATUS_CHANGED` — and the failure paths are inseparable from the success path because
partial failure *is* the feature.

### The ACs this decomposes into

| AC | Path | Why it exists |
|---|---|---|
| AC-1 | all IDs valid → all update, HTTP 200, N events, N audit entries | the happy path, with counts |
| AC-2 | one ID absent → others update, `TASK_NOT_FOUND` for it, HTTP 207 | partial failure; the PDF's named requirement |
| AC-3 | one ID is `task-4` (DONE) → `INVALID_STATUS_TRANSITION`, HTTP 207 | the transition rule still applies in bulk |
| AC-4 | target status is neither DONE nor BLOCKED → HTTP 422, nothing updates, zero events | request-level rejection precedes any write |
| AC-5 | a failed item produces neither event nor audit entry | the counting invariant, stated alone because it is the likeliest defect |
| AC-6 | empty ID list → HTTP 422, zero events | boundary case that a naive loop passes silently |

Six ACs, four of them failure paths. That ratio is normal and correct: the failure paths are where
FM-2, FM-3 and FM-4 live.

### Exclusions for this sprint

- No reassignment of the activity's assignee
- No transition to `TODO` or `IN_PROGRESS` in bulk (handover marks work finished or stuck)
- No `SHIFT_HANDOVER` notification — alerts reacts to `BLOCKED` via the existing subscriber, and
  changing that is a separate sprint touching Rule 2
- No pagination or batch-size limit

---

## 8. Planner self-check before writing the status line

Do not emit `STATUS: AWAITING APPROVAL` until every line below is true.

- [ ] `spec.md` quotes the feature prompt verbatim and the contract references `spec.md`
- [ ] 4–8 ACs, each with an AC-id, GIVEN/WHEN/THEN, modules, architecture rules, and named tests
- [ ] Every AC that causes a side effect states a **count**, and states the count for failure (zero)
- [ ] At least one AC per plausible failure path; none deferred to a later sprint
- [ ] Every AC is anchored to seed fixtures or explicitly creates its own state
- [ ] No AC is satisfiable by asserting an HTTP status alone
- [ ] Exactly one module is written to
- [ ] Assumptions, dependencies, risks and exclusions are all present and specific
- [ ] Each risk names the gate that would detect it
- [ ] No production code and no test code has been written — that is the Generator's job
- [ ] The contract's **final line** is `STATUS: AWAITING APPROVAL`
