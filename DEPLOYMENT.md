# StoreOps — Deployment

**Recommendation: Amazon ECS on Fargate**, behind an Application Load Balancer, image in ECR.

---

## 0. Evidence — what was actually executed

Stated first and plainly, because a deployment document that blurs designed against executed is
worse than one that admits a gap.

| Claim | Status | Evidence |
|---|---|---|
| `GET /health` responds `200` with the environment from config | **EXECUTED** | live capture below |
| `PATCH /api/activities/bulk-status` returns 207 with per-item `AppError` detail | **EXECUTED** | live capture below |
| `mypy . && ruff check . && lint-imports && pytest --cov` green | **EXECUTED** | 168 passed, 99.66%, 8/8 contracts, exit 0 |
| `docker build -t storeops:local .` | **DESIGNED — NOT EXECUTED** | `docker` is not installed on this machine; `docker --version` fails. No build output is reproduced here |
| Container `HEALTHCHECK` passes | **DESIGNED — NOT EXECUTED** | same reason; the CI `container` job performs it on every push |
| ECS Fargate deployment | **DESIGNED — NOT EXECUTED** | no AWS account or credentials available in this environment |

**Nothing below that was not run is described as though it were.** The Docker and AWS sections are
a specification to execute against, and the CI `container` job in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) performs the build and the health probe on
neutral infrastructure on every push — so the unexecuted step is automated rather than merely
promised.

### Executed: health endpoint, environment-driven

Served by `uvicorn app.main:app` with `STOREOPS_ENV=production`, the same command and the same
variable the container `CMD` and task definition use:

```
$ STOREOPS_ENV=production uvicorn app.main:app --host 127.0.0.1 --port 8011
$ curl http://127.0.0.1:8011/health
{"status":"ok","app":"StoreOps API","environment":"production","version":"0.1.0"}
```

`"environment":"production"` is the load-bearing part: it proves configuration reaches the app
from the environment rather than from a committed default, which is the whole basis of the
promote-the-same-image model in §3.

### Executed: post-deploy verification of the sprint-1 endpoint

```
$ curl -X PATCH http://127.0.0.1:8011/api/activities/bulk-status \
    -H 'Content-Type: application/json' \
    -d '{"task_ids":["task-1","task-999"],"status":"DONE"}'
HTTP 207
{"updated":1,"failed":1,"results":[
  {"taskId":"task-1","outcome":"UPDATED","status":"DONE","error":null},
  {"taskId":"task-999","outcome":"FAILED","status":null,
   "error":{"code":"TASK_NOT_FOUND","message":"Task 'task-999' does not exist",
            "statusCode":404,"details":{"taskId":"task-999"}}}]}
```

HTTP 207 with one item updated, one item carrying a typed `TASK_NOT_FOUND` — the partial-failure
contract from `sprint-1-contract.md` AC-2, verified against a running server.

---

## 1. Why ECS Fargate over Elastic Beanstalk

Both would work. Fargate wins on four specifics of *this* service.

| Factor | ECS Fargate | Elastic Beanstalk |
|---|---|---|
| **Artefact match** | Runs the OCI image CI already builds and health-checks. Nothing is rebuilt or re-wrapped | Its Docker platform wraps the image in a managed EC2 layer; the deployed unit differs from the tested unit |
| **IAM granularity** | **Task role** is per-task and separate from the **execution role**. §5's least-privilege split is expressible directly | Instance profile is per-environment; every process on the instance shares it |
| **Rollback** | `UpdateService` to the previous task-definition revision — immutable, one call, seconds. Optionally CodeDeploy blue/green with automatic rollback on alarm | Application-version swap or environment CNAME swap; coarser and slower |
| **Operational surface** | No EC2 to patch. StoreOps is stateless with in-memory repositories, so there is nothing on the host worth keeping | Manages EC2 for you but you still own AMI currency |

The deciding factor is the second and third rows together. StoreOps' governing constraint is a
**typed error contract and a module boundary enforced at the code level**; the deployment layer
should extend that discipline, not dilute it. A per-task role that can read exactly one secret
prefix is the infrastructure analogue of `app/reports/` having no `add()` method — the capability
is absent, not merely unused.

**Choose Beanstalk instead if** the team has no ECS experience and needs something running this
week; the rollback story is acceptable and the migration path to ECS later is real.

---

## 2. Minimum viable deployment

Everything required to serve traffic. Nothing optional.

| # | Resource | Configuration | Why |
|---|---|---|---|
| 1 | **ECR repository** `storeops` | image scanning on push; tag immutability **on** | Immutable tags mean a rollback to `sha-abc123` gets the bytes that were tested. Mutable tags make "same version" unverifiable |
| 2 | **ECS cluster** | Fargate capacity providers | No EC2 |
| 3 | **Task definition** `storeops` | 0.5 vCPU / 1 GB, `awsvpc`, port 8000, image pinned by **digest or commit SHA — never `latest`** | `latest` breaks rollback and makes two tasks in one service potentially different builds |
| 4 | **ECS service** | desired count **2**, rolling update, min healthy 100% / max 200% | Two tasks across AZs so a task replacement is not an outage. In-memory state means each task has its own data — see the caveat in §8 |
| 5 | **ALB + target group** | HTTP :80 → target :8000, health check `GET /health`, 200, interval 15s, healthy 2 / unhealthy 3, deregistration delay 30s | `/health` is the same probe the container `HEALTHCHECK` and CI use |
| 6 | **VPC** | tasks in **private** subnets; ALB in public; NAT or VPC endpoints for ECR + CloudWatch Logs | Nothing reaches the task except through the ALB |
| 7 | **Security groups** | ALB SG: :80 from the internet. Task SG: :8000 **from the ALB SG only** | Source is the ALB's group, not a CIDR |
| 8 | **CloudWatch log group** | `/ecs/storeops`, `awslogs` driver, 30-day retention | `unhandled_exception_handler` logs at `exception` level — that line is the FM-2 tripwire in production and must be searchable |
| 9 | **Execution role** | `AmazonECSTaskExecutionRolePolicy` + ECR pull + log write | Used by the **agent**, not the app. See §5 |
| 10 | **Task role** | see §5 — minimal, and for today genuinely empty | Used by the **app** |

### Optional enhancements — deliberately out of the MVP

| Enhancement | Adds | Why it is not required now |
|---|---|---|
| CodeDeploy **blue/green** with CloudWatch alarm rollback | Automatic revert on a 5xx spike | Rolling update plus manual rollback (§7) is sufficient at two tasks |
| **WAF** on the ALB | Managed rule sets | No authentication and no untrusted input surface yet |
| **Custom domain + ACM** certificate, HTTPS listener | TLS, stable hostname | The ALB DNS name is adequate for a demonstration. **Required before any real traffic** |
| **Auto-scaling** on ALB request count | Elasticity | Load is unknown; a fixed 2 is honest until it is measured |
| **X-Ray** tracing | Cross-module event-flow visibility | The in-process `EventBus` is fully observable via the audit sink today |
| **RDS / DynamoDB** | Durable, shared state | StoreOps is explicitly in-memory. This is the largest gap between this deployment and a production one — see §8 |

---

## 3. Environment-based configuration

`app/shared/config.py` reads settings from the environment with `os.getenv`, so **one image is
promoted across environments unchanged**. A rebuild per environment would mean the artefact in
production was never the artefact that was tested.

| Variable | Default | Production value | Set as |
|---|---|---|---|
| `STOREOPS_ENV` | `local` | `production` | task definition `environment` |
| `STOREOPS_APP_NAME` | `StoreOps API` | `StoreOps API` | task definition `environment` |
| `STOREOPS_LOG_LEVEL` | `INFO` | `INFO` | task definition `environment` |
| `STOREOPS_SLA_GRACE_MINUTES` | `60` | per business policy | task definition `environment` |

**The exact names matter.** It is `STOREOPS_ENV`, not `STOREOPS_ENVIRONMENT`
(`app/shared/config.py:50`). A mistyped name is not an error — `os.getenv` returns the default, so
the service silently reports `environment: "local"` while serving production traffic. Authoring
this document caught exactly that typo in the `Dockerfile`'s `ENV` block, and the `/health`
capture in §0 is the check that proves the correct name is wired.

`_int_from_env` also **falls back to the default on an unparseable value** rather than raising
(`config.py:33-40`), so `STOREOPS_SLA_GRACE_MINUTES=sixty` yields 60 with no complaint. Assert the
value in `/health` output or a smoke test rather than trusting that it was set.

---

## 4. Secrets handling

**StoreOps has no secrets today.** No database, no API key, no `AuthToken` signing key — `AuthToken`
exists as a model with no verification path. Saying "secrets are managed in Secrets Manager" would
be describing a mechanism that is not wired to anything.

What is true today, and enforced:

- **No secret is committed.** No default in `config.py` is sensitive; `.gitignore` excludes `.env`,
  `.env.*`; `.dockerignore` excludes `.env`, `.env.*`, `*.pem`, `*.key` so a developer's local
  `.env` cannot be copied into an image even though git never sees it.
- **No secret is baked into the image.** The `Dockerfile` `ENV` block holds only non-sensitive
  defaults. A secret in `ENV` is readable by anyone who can `docker history` the image.
- **`unhandled_exception_handler` does not echo the original exception message**, so a connection
  string in an exception cannot leak into a response body.
  `tests/shared/test_errors.py::test_unhandled_exception_is_converted_to_the_envelope_without_leaking_detail`
  raises with a fake connection string and asserts its absence. **Preserve that property** when
  the handler is next touched.

**When the first real secret arrives** (a database URL, most likely — §8):

1. Store it in **AWS Secrets Manager** at `storeops/production/<name>`.
2. Inject via the task definition's `secrets` block, which resolves the value to an environment
   variable at task start. Never via `environment`, and never at build time.
3. Grant `secretsmanager:GetSecretValue` on `arn:aws:secretsmanager:<region>:<acct>:secret:storeops/production/*`
   to the **execution role** (it fetches before the container starts), not the task role.
4. Enable rotation and confirm the app re-reads on restart. `get_settings()` is deliberately
   uncached (`config.py:46`), so a task restart is sufficient — no in-process cache to invalidate.
5. Never log a resolved secret. `STOREOPS_LOG_LEVEL=DEBUG` in production is a review item for
   exactly this reason.

---

## 5. Least-privilege roles

Two roles, different actors. Conflating them is the most common ECS over-permissioning mistake.

### Execution role — used by the ECS **agent**, before the app runs

`AmazonECSTaskExecutionRolePolicy` covers the standard case:

- `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` on the
  `storeops` repository
- `logs:CreateLogStream`, `logs:PutLogEvents` on `/ecs/storeops:*`
- later, `secretsmanager:GetSecretValue` on the `storeops/production/*` prefix only

### Task role — used by the **application**

```json
{ "Version": "2012-10-17", "Statement": [] }
```

**Empty, deliberately.** StoreOps calls no AWS API: storage is in-memory, the event bus is
in-process, the audit sink is a Python list. An empty policy is the accurate description of what
the application needs.

A task role is still attached rather than omitted, for two reasons: the first genuine AWS call has
an obvious, reviewable place to add a permission, and an attached-but-empty role makes a future
diff that adds `s3:*` visible in review rather than invisible in an absence.

**Do not** attach a managed policy "to save time later". The reason `app/reports/` has no `add()`
method is that an absent capability cannot be misused; the same reasoning applies here.

---

## 6. Health validation and deployment verification

### Health

Three layers, all hitting the same `GET /health` at `app/main.py:70`:

| Layer | Mechanism | Effect on failure |
|---|---|---|
| Container | `HEALTHCHECK` in the `Dockerfile` (stdlib `urllib`, no curl in `python:slim`) | Docker marks the container unhealthy |
| ALB target group | `GET /health`, expect 200, healthy 2 / unhealthy 3 | Target drained; ECS replaces the task |
| CI | `container` job starts the image and curls `/health`, then asserts `id -u` is `10001` | Push fails before any deploy |

`/health` returns `status`, `app`, `environment`, `version` — enough to confirm *which build with
which configuration* answered, which a bare `200` cannot.

### Post-deploy verification — run all four, in order

```bash
ALB=storeops-alb-123456.eu-west-1.elb.amazonaws.com

# 1. Health, and confirm the environment and version that actually deployed
curl -fsS "http://$ALB/health"
# expect: {"status":"ok","app":"StoreOps API","environment":"production","version":"0.1.0"}

# 2. The PDF section 2.3 verification endpoint
curl -fsS -o /dev/null -w '%{http_code}\n' "http://$ALB/api/tasks"     # expect 200

# 3. Sprint-1 partial failure: HTTP 207, one typed per-item error
curl -sS -X PATCH "http://$ALB/api/activities/bulk-status" \
  -H 'Content-Type: application/json' \
  -d '{"task_ids":["task-1","task-999"],"status":"DONE"}' \
  -w '\nHTTP %{http_code}\n'
# expect HTTP 207, updated=1, failed=1, error.code == "TASK_NOT_FOUND"

# 4. Error contract intact end to end — task-4 is seeded DONE and terminal
curl -sS -X PATCH "http://$ALB/api/tasks/task-4/status" \
  -H 'Content-Type: application/json' -d '{"status":"TODO"}' \
  -w '\nHTTP %{http_code}\n'
# expect HTTP 409, error.code == "INVALID_STATUS_TRANSITION"
```

Steps 3 and 4 are the ones worth insisting on. A 200 from `/health` proves the process started;
only a **typed error code through the ALB** proves the `AppError` handler is registered and the
error contract survived containerisation. A misconfigured proxy that rewrites error bodies passes
steps 1 and 2 and fails these.

Checks 3 and 4 **mutate seeded state** (`task-1` becomes `DONE`). With in-memory storage that
persists until the task restarts, and it hits only the one task the ALB routed to — see §8.

---

## 7. Rollback

Immutable task-definition revisions make this a single call. **Roll back first, diagnose after.**

```bash
# 1. What is deployed, and what preceded it?
aws ecs describe-services --cluster storeops --services storeops \
  --query 'services[0].taskDefinition'
aws ecs list-task-definitions --family-prefix storeops --sort DESC --max-items 5

# 2. Revert to the previous known-good revision
aws ecs update-service --cluster storeops --service storeops \
  --task-definition storeops:41 --force-new-deployment

# 3. Watch it settle
aws ecs wait services-stable --cluster storeops --services storeops

# 4. Re-run all four checks from section 6 against the ALB
```

**Time to restore: ~2–4 minutes**, dominated by ALB health-check convergence
(healthy 2 × 15s) plus the 30s deregistration delay.

| Trigger | Action |
|---|---|
| `/health` non-200 after deploy | Automatic — ECS replaces failing tasks; if all fail, roll back |
| 5xx spike, or `INTERNAL_ERROR` in the logs | Roll back immediately. `INTERNAL_ERROR` means an untyped exception reached `unhandled_exception_handler` — that is FM-2 in production |
| Check 3 or 4 returns the wrong code | Roll back. The error contract is broken and clients branching on `code` are already misbehaving |
| Image will not pull | Not a rollback — the ECR tag or execution-role permission is wrong |

**Do not roll back by re-tagging an image.** Rolling the *task definition* keeps an audit trail of
what ran when; re-tagging destroys it, and ECR tag immutability blocks it anyway.

**Roll forward instead** only when the previous revision is known bad — a rollback would restore a
different fault.

---

## 8. Known limitations — read before treating this as production-ready

1. **In-memory storage, so state is per-task and ephemeral.** With `desiredCount: 2`, two
   consecutive requests can hit different tasks and see different data. `task_repository.reset()`
   re-seeds on start, so every deployment silently discards all writes. This is the intended
   scaffold design (PDF §3.3 specifies in-memory) and the **single largest gap** to production.
   *Fix:* a real repository behind the existing interface — the `TaskRepository` method surface
   (`get`, `replace`, `add`, `list_all`) is already the seam, and Rule 1 means no other module
   would change. Then `desiredCount` becomes meaningful and §6's mutating checks stop being
   task-affine.
2. **No authentication or authorisation.** `AuthToken` and `StaffRole` exist as models with no
   verification path. `PATCH /api/activities/bulk-status` is unauthenticated — deliberate, per
   `sprint-1-contract.md` Exclusion 8. Do not expose this to the internet without an authorizer.
3. **HTTP only.** No ACM certificate or HTTPS listener in the MVP. Required before real traffic.
4. **The event bus is in-process.** `EventBus` publishes to subscribers inside the same Python
   process, so an event raised on task A is invisible to task B, and the audit sink is per-task.
   Cross-task events need SNS/EventBridge or SQS behind the same `publish` interface.
5. **Docker build and the AWS deployment were not executed here** (§0). CI performs the build and
   health probe on every push; the AWS steps remain unexecuted.
