# Skill: app-context

**Purpose.** Orient any agent to StoreOps in one read: what the service does, what entities exist,
what is already built, and what command proves it still works. This file states *facts*, not rules —
rules live in [architecture-principles](../architecture-principles/SKILL.md).

**Read by:** Planner, Generator, Evaluator, Monitor (all four).

> **Cost note.** This file is loaded by every agent on every iteration, so its length is paid four
> times per loop. It is deliberately the shortest skill file in the harness. Resist adding rules
> here — they belong in a file only the agent that needs them will read.

---

## 1. What StoreOps is

A REST API for retail store operations management. Store teams create operational programmes,
assign and track activities across departments, coordinate staff, and read performance reports by
store. In-memory storage, no database. Stub business logic — structure and boundaries are the point.

- **Stack:** Python 3.13 (declared floor 3.11+), FastAPI, Pydantic v2, in-memory repositories
- **Start:** `uvicorn app.main:app --reload` → http://localhost:8000
- **Application code lives in `app/`, not `src/`** — see [Section 6](#6-known-deviations)

---

## 2. The five business modules

Every module owns `routes.py`, `service.py`, `repository.py`, `models.py` under `app/<module>/`.

| Module | Retail responsibility | Entities and enums |
|---|---|---|
| `activities` | Operational activities: restocking runs, planogram resets, compliance checks | `Task`; `TaskStatus` (TODO / IN_PROGRESS / DONE / BLOCKED), `TaskPriority` (LOW / MEDIUM / HIGH / CRITICAL), `TaskCategory` (RESTOCKING / PLANOGRAM / AUDIT / COMPLIANCE / GENERAL) |
| `programmes` | Store programmes and staff membership: seasonal rollouts, compliance drives, refits | `Project`, `ProjectMember`; `ProjectRole` (STORE_MANAGER / DEPARTMENT_LEAD / ASSOCIATE), `ProjectStatus` (PLANNED / ACTIVE / CLOSED) |
| `staff` | Staff registration, authentication, profiles | `User`, `UserProfile`, `AuthToken`; `StaffRole` (REGIONAL_MANAGER / STORE_MANAGER / DEPARTMENT_LEAD / ASSOCIATE) |
| `alerts` | In-app alerts triggered by operational events | `Notification`; `AlertType` (INVENTORY / SLA_BREACH / SHIFT_HANDOVER / ESCALATION), `NotificationChannel` (IN_APP / EMAIL), `NotificationStatus` (PENDING / SENT / READ / FAILED) |
| `reports` | Store and regional performance summaries | `Report`, `StoreSummary`; `ReportType` (STORE_SUMMARY / REGIONAL_ROLLUP / DEPARTMENT_PERFORMANCE), `ReportStatus` (PENDING / READY / FAILED) |

### Shared infrastructure — `app/shared/`

Technical capabilities only. **Not a sixth business module**: it owns no routes and no domain rules.

| File | Provides |
|---|---|
| `errors.py` | `AppError` base (`code`, `message`, `status_code`) + 11 subclasses, FastAPI handlers |
| `events.py` | `EventBus` (`publish` / `subscribe`), `Event`, `EventName` catalogue, `event_bus` singleton |
| `audit.py` | `AuditSink` (`record`, `attach`, `count_for`), `audit_sink` singleton |
| `config.py` | `Settings`, `get_settings()` — environment-driven |
| `logging.py` | `configure_logging()`, `get_logger()` |

`app/main.py` is the **composition root**: it registers error handlers, wires event subscriptions
(`wire_event_handlers()`), includes the five routers, and serves `GET /health`.

---

## 3. The 9 REST endpoints

`/health` is infrastructure and excluded from this count.

| # | Method | Path | Module |
|---|---|---|---|
| 1 | GET | `/api/tasks` | activities |
| 2 | GET | `/api/tasks/{task_id}` | activities |
| 3 | POST | `/api/tasks` | activities |
| 4 | PATCH | `/api/tasks/{task_id}/status` | activities |
| 5 | GET | `/api/projects` | programmes |
| 6 | POST | `/api/projects/{project_id}/members` | programmes |
| 7 | GET | `/api/users` | staff |
| 8 | GET | `/api/notifications` | alerts |
| 9 | GET | `/api/reports/store/{store_id}` | reports |

`tests/test_main.py::test_exactly_the_nine_required_rest_endpoints_are_routed` asserts this set
exactly. **Adding an endpoint requires updating that test** — it is not an incidental assertion.

---

## 4. Event catalogue

Three event types, all published to `event_bus` and all recorded by `audit_sink`:

| Event | Published by | Consumed by |
|---|---|---|
| `ACTIVITY_CREATED` | `ActivitiesService.create_task` | audit sink |
| `ACTIVITY_STATUS_CHANGED` | `ActivitiesService.update_status` | audit sink, `AlertsService.handle_activity_status_changed` |
| `PROGRAMME_MEMBER_ADDED` | `ProgrammesService.add_member` | audit sink |

`ACTIVITY_STATUS_CHANGED` payload keys: `taskId`, `storeId`, `previousStatus`, `newStatus`,
`priority`, `assigneeId`. Payloads are plain mappings, never domain models.

---

## 5. Seed data

Every repository re-seeds on `reset()`; `tests/conftest.py` does this before each test. Seed base
time is `2026-08-31T08:00:00Z`. **Write acceptance criteria against these fixtures** rather than
inventing data — a criterion naming `task-4` is immediately testable.

**Tasks** (`app/activities/repository.py`)

| id | status | priority | category | store | assignee | due |
|---|---|---|---|---|---|---|
| `task-1` | TODO | HIGH | RESTOCKING | store-101 | user-3 | +6h |
| `task-2` | IN_PROGRESS | MEDIUM | PLANOGRAM | store-101 | user-3 | +1d |
| `task-3` | BLOCKED | CRITICAL | COMPLIANCE | store-101 | user-2 | −2h (overdue) |
| `task-4` | **DONE** | MEDIUM | AUDIT | store-102 | user-4 | −1d |
| `task-5` | TODO | LOW | GENERAL | store-102 | **none** | none |

`task-4` is the ready-made invalid-transition fixture (DONE is terminal). `task-5` is the
ready-made no-assignee fixture.

**Staff:** `user-1` REGIONAL_MANAGER (store-101) · `user-2` STORE_MANAGER (store-101) ·
`user-3` DEPARTMENT_LEAD, Grocery (store-101) · `user-4` ASSOCIATE, Chilled (store-102)

**Programmes:** `project-1` ACTIVE store-101 (members user-2, user-3) · `project-2` PLANNED
store-101 (user-2) · `project-3` **CLOSED** store-102 (user-4) — the closed-programme fixture

**Notifications:** `notification-1` INVENTORY → user-3, subject `task-1` · `notification-2`
SLA_BREACH → user-2, subject `task-3`

> **Trap.** `notification-1` already targets `task-1`. A test asserting "one notification exists
> for task-1" passes before anything happens. Filter by `alert_type`, or compare before/after
> counts. This exact mistake cost two failing tests in Phase 1.

**Stores referenced:** `store-101`, `store-102`. `ActivitiesService.known_store_ids()` is the
authority — `reports` uses it to reject unknown stores.

---

## 6. Known deviations

**`app/` not `src/`.** Capstone PDF section 7's structure table says `src/`, but PDF section 2.3
step 4 gives the start command as `uvicorn app.main:app --reload`, which requires a top-level `app`
package. Section 7's table is the generic cross-stack row; section 2.3 is the Python-specific
instruction. Recorded in `DESIGN_BRIEF.md` Section D and `JOURNAL.md` D-01.

---

## 7. The quality gate

One command. Every agent that touches code must run it and **paste the real output**:

```
mypy . && ruff check . && lint-imports && pytest --cov
```

| Tool | Enforces | Config |
|---|---|---|
| `mypy` | strict typing, 54 files | `pyproject.toml` `[tool.mypy]` |
| `ruff` | style + `TRY`/`BLE`/`EM` error-contract rules | `pyproject.toml` `[tool.ruff]` |
| `lint-imports` | 8 dependency contracts | `.importlinter` |
| `pytest --cov` | tests + **80% coverage floor** | `[tool.coverage.report] fail_under = 80` |

Current baseline: **160 tests passing, 99.63% coverage, 8/8 contracts kept.** A change that lowers
any of these needs an explicit justification, not silence.

**Test helpers** in `tests/conftest.py`: `reset_state` (autouse), `client`, `activities` and
`alerts` isolated harnesses, `api_endpoints()`, `endpoint_tags()`.
