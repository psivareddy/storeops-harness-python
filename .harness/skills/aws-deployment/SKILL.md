# Skill: aws-deployment

**Purpose.** The repeatable procedure for deploying StoreOps to ECS Fargate and rolling it back,
as commands with their expected output and their abort conditions.

**Read by:** whoever performs a deployment — human or agent. Unlike the other eight skill files
this one governs an *operational* action rather than code generation, so it is written as a
runbook: numbered, idempotent where possible, with a named abort point at every step.

> **Boundary with [DEPLOYMENT.md](../../../DEPLOYMENT.md).** That document explains *what the
> target looks like and why ECS Fargate* — the resource inventory, the role split, the rationale.
> This file is *the sequence you execute*. Read that once; follow this every time.

---

## 0. Preconditions — all four, no exceptions

| # | Precondition | Check | If it fails |
|---|---|---|---|
| 1 | The harness gate is green | `mypy . && ruff check . && lint-imports && pytest --cov` → exit 0 | **Stop.** Never deploy a red gate |
| 2 | CI is green on this exact commit | GitHub Actions `CI` on the SHA — the `gate`, `harness-separation` **and** `container` jobs | **Stop.** CI is the trust boundary (`CLAUDE.md` §6); a local green is not sufficient |
| 3 | The commit is pushed | `git status` clean, `git log origin/main..HEAD` empty | **Stop.** Deploying an unpushed commit produces an image nobody can trace to source |
| 4 | Any in-flight sprint has a `PASS` or `CONDITIONAL PASS` verdict archived | `grep '^VERDICT:' .harness/reviews/sprint-*-evaluator-feedback.md` | **Stop.** Deploying code the Evaluator failed bypasses the governance layer entirely |

Precondition 4 is the one that makes this a *harness* skill rather than a generic runbook. The
gate proves the code is clean; the verdict proves it was **accepted**. They are different claims.

```bash
export AWS_REGION=eu-west-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ECR=$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/storeops
export SHA=$(git rev-parse --short HEAD)
export CLUSTER=storeops SERVICE=storeops FAMILY=storeops
```

---

## 1. Build and push — tag by commit SHA, never `latest`

```bash
docker build -t storeops:$SHA .
docker run --rm -d --name storeops-preflight -p 8000:8000 storeops:$SHA
sleep 5
curl -fsS http://localhost:8000/health          # expect status ok
test "$(docker exec storeops-preflight id -u)" = "10001"   # expect non-root
docker rm -f storeops-preflight

aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
docker tag storeops:$SHA $ECR:$SHA
docker push $ECR:$SHA

# Capture the digest. This, not the tag, is what a rollback should target.
export DIGEST=$(aws ecr describe-images --repository-name storeops \
  --image-ids imageTag=$SHA --query 'imageDetails[0].imageDigest' --output text)
echo "$SHA -> $DIGEST"
```

**Never tag `latest`.** Two tasks in one service could then be running different builds, and
"roll back to the previous image" stops being a well-defined instruction. ECR tag immutability
(`DEPLOYMENT.md` §2 item 1) enforces this, so a re-push of an existing tag fails rather than
silently replacing bytes.

**Abort if** the preflight `/health` fails or `id -u` is not `10001`. A root container will be
rejected by a `runAsNonRoot` policy after deployment, which is a slower and more confusing failure.

---

## 2. Register a new task-definition revision

```bash
aws ecs describe-task-definition --task-definition $FAMILY \
  --query 'taskDefinition' > /tmp/td.json

jq --arg img "$ECR@$DIGEST" '
  .containerDefinitions[0].image = $img
  | del(.taskDefinitionArn, .revision, .status, .requiresAttributes,
        .compatibilities, .registeredAt, .registeredBy)
' /tmp/td.json > /tmp/td-new.json

export NEW_REV=$(aws ecs register-task-definition \
  --cli-input-json file:///tmp/td-new.json \
  --query 'taskDefinition.revision' --output text)
echo "registered $FAMILY:$NEW_REV"
```

Pinning by **digest** (`@sha256:…`) rather than tag means the revision names exact bytes. A tag
can in principle be re-pointed; a digest cannot.

**Record the outgoing revision before deploying — this is the rollback target:**

```bash
export PREV_REV=$(aws ecs describe-services --cluster $CLUSTER --services $SERVICE \
  --query 'services[0].taskDefinition' --output text | awk -F: '{print $NF}')
echo "rollback target: $FAMILY:$PREV_REV"
```

**Abort if** `$PREV_REV` is empty on anything other than a first deployment. Deploying without a
known rollback target means the only recovery path is forward, under time pressure.

---

## 3. Deploy

```bash
aws ecs update-service --cluster $CLUSTER --service $SERVICE \
  --task-definition $FAMILY:$NEW_REV

aws ecs wait services-stable --cluster $CLUSTER --services $SERVICE
```

`services-stable` returns when the running count equals the desired count and no deployment is in
progress. Expect **2–4 minutes** at `desiredCount: 2` — mostly ALB health-check convergence
(healthy 2 × 15s) plus the 30s deregistration delay.

**If `wait` times out**, do not retry it. Go to §5 and roll back, then diagnose:

```bash
aws ecs describe-services --cluster $CLUSTER --services $SERVICE \
  --query 'services[0].events[:5]'
aws logs tail /ecs/storeops --since 10m
```

---

## 4. Verify — all four checks, in order, every time

```bash
ALB=$(aws elbv2 describe-load-balancers --names storeops-alb \
  --query 'LoadBalancers[0].DNSName' --output text)

# 1. health, plus the build and configuration that actually answered
curl -fsS "http://$ALB/health"
# expect: {"status":"ok","app":"StoreOps API","environment":"production","version":"0.1.0"}

# 2. the PDF section 2.3 verification endpoint
curl -fsS -o /dev/null -w '%{http_code}\n' "http://$ALB/api/tasks"       # expect 200

# 3. sprint-1 partial failure — 207 with a typed per-item error
curl -sS -X PATCH "http://$ALB/api/activities/bulk-status" \
  -H 'Content-Type: application/json' \
  -d '{"task_ids":["task-1","task-999"],"status":"DONE"}' -w '\nHTTP %{http_code}\n'
# expect HTTP 207, updated=1, failed=1, error.code == "TASK_NOT_FOUND"

# 4. error contract end to end — task-4 is seeded DONE and terminal
curl -sS -X PATCH "http://$ALB/api/tasks/task-4/status" \
  -H 'Content-Type: application/json' -d '{"status":"TODO"}' -w '\nHTTP %{http_code}\n'
# expect HTTP 409, error.code == "INVALID_STATUS_TRANSITION"
```

**Checks 3 and 4 are not optional.** A 200 from `/health` proves the process started. Only a typed
error code arriving through the ALB proves `register_error_handlers()` ran and the error contract
survived containerisation — a proxy that rewrites error bodies passes checks 1 and 2 and fails
these. That distinction is FM-2 reaching production.

**Abort and roll back if** any check returns an unexpected status **or** the right status with the
wrong `code`. The `code` is what clients branch on; a 409 carrying `CONFLICT` instead of
`INVALID_STATUS_TRANSITION` is a breaking change wearing a passing status.

Also confirm `"environment":"production"` in check 1. `os.getenv` falls back to a default on a
mistyped variable name, so `"local"` here means the task definition is wrong even though every
status code is correct. The variable is `STOREOPS_ENV` — not `STOREOPS_ENVIRONMENT`
(`app/shared/config.py:50`).

Checks 3 and 4 **mutate seeded state** and, with in-memory storage, only on the one task the ALB
routed to. Accepted for a scaffold; see `DEPLOYMENT.md` §8 item 1.

---

## 5. Roll back

```bash
aws ecs update-service --cluster $CLUSTER --service $SERVICE \
  --task-definition $FAMILY:$PREV_REV --force-new-deployment

aws ecs wait services-stable --cluster $CLUSTER --services $SERVICE

# then re-run all four checks from section 4
```

**Time to restore: ~2–4 minutes.**

| Trigger | Action |
|---|---|
| `/health` non-200 after deploy | ECS replaces failing tasks automatically; if all fail, roll back |
| `INTERNAL_ERROR` in the response body or `exception`-level lines in the log | **Roll back immediately** — an untyped exception reached `unhandled_exception_handler`, which is FM-2 live |
| Verify check 3 or 4 wrong | Roll back; the error contract is broken |
| 5xx spike | Roll back, then read `/ecs/storeops` |
| Image will not pull | **Not** a rollback — fix the ECR tag or the execution-role permission |
| `"environment":"local"` in `/health` | **Not** a rollback — fix the task definition's `STOREOPS_ENV` and redeploy |

**Two things never to do.** Do not roll back by re-tagging an image: rolling the task definition
keeps an audit trail of what ran when, and re-tagging destroys it. Do not edit a task definition
in place — revisions are immutable, which is the property the whole procedure rests on.

**Roll forward instead** only when the previous revision is known bad, since a rollback would
restore a different fault.

---

## 6. After any rollback — close the loop in the harness

A rollback is evidence about the harness, not just an operational event. It means something reached
production that the gate and the verdict both accepted.

1. Record it in `JOURNAL.md`: what deployed, what broke, which check caught it, time to restore.
2. Ask **which gate should have caught this.** If the answer is "none of the eight", that is a gap
   in `evaluation-criteria` §2 and the candidate new gate belongs in `REFLECTION.md`.
3. If CI passed but production failed, the deterministic suite has a coverage gap the archive
   should name — the same reasoning `CLAUDE.md` §6 applies when the harness passes and CI fails.
4. If a `.harness/reviews/` run log already flagged the area as a recurring pattern, the drift
   signal was correct and was not acted on. That is the more important finding.

---

## 7. Deployment checklist

- [ ] Gate green locally; CI green on this SHA (all three jobs)
- [ ] Commit pushed; working tree clean
- [ ] Archived verdict for the sprint is `PASS` or `CONDITIONAL PASS`
- [ ] Image tagged by commit SHA, **never** `latest`; digest captured
- [ ] Preflight: local container serves `/health` and runs as uid `10001`
- [ ] `$PREV_REV` recorded **before** `update-service`
- [ ] Task definition pins the image by digest
- [ ] `services-stable` returned rather than timed out
- [ ] All four verify checks pass, including both **error codes**
- [ ] `/health` reports `"environment":"production"`
- [ ] Rollback command prepared and pasted into the change record before deploying
