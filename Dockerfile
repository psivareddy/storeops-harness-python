# StoreOps container image.
#
# Multi-stage: the builder compiles wheels and populates a virtualenv; the runtime stage copies
# only that venv. Build toolchains, pyproject and the source tree never reach the final image.
#
# Python 3.11 is deliberate, not incidental: pyproject.toml declares `requires-python = ">=3.11"`
# and `[tool.mypy] python_version = "3.11"`, so 3.11 is the version the type checker validates
# against. Shipping a newer interpreter than the gate reasons about would mean shipping something
# untested. Override for a local experiment with `--build-arg PYTHON_VERSION=3.13`.

ARG PYTHON_VERSION=3.11

# ---------------------------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /src

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# pyproject first so the dependency layer is reused when only app/ changes. The source is still
# needed for `pip install .` (setuptools builds the `app` package), so this splits the cache at
# the coarsest useful boundary rather than the theoretical best one.
COPY pyproject.toml ./
COPY app ./app

# Runtime dependencies only — fastapi, pydantic, uvicorn[standard]. The `dev` extra
# (pytest, mypy, ruff, import-linter) is intentionally absent: test and lint tooling in a
# production image is attack surface, and the gate runs in CI, not in the container.
RUN pip install --no-cache-dir .

# ---------------------------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    STOREOPS_ENV=production \
    STOREOPS_LOG_LEVEL=INFO

# Non-root, no login shell, fixed high UID. The fixed UID matters for ECS/EKS: a
# `runAsNonRoot` admission policy compares the numeric UID, and an image whose user is resolved
# only by name fails that check.
RUN groupadd --gid 10001 storeops \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin storeops

# The app is installed into the venv's site-packages, so no source tree is copied here. Nothing
# in the final image is writable by the runtime user.
COPY --from=builder --chown=root:root /opt/venv /opt/venv

USER 10001:10001

EXPOSE 8000

# Hits the same GET /health that app/main.py:70 serves and CI smoke-checks. Uses stdlib urllib
# rather than curl: python:slim ships no curl, and installing one to health-check would add a
# package to the runtime image for no other reason.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]

# Exec form, no shell: uvicorn becomes PID 1 and receives SIGTERM directly, so ECS task
# draining and `docker stop` shut down gracefully instead of waiting out the 10s kill timer.
# No --reload: that is a development flag and would watch a source tree this image does not have.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
