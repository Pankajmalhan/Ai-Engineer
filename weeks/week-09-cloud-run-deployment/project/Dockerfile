# syntax=docker/dockerfile:1

# ---- builder ------------------------------------------------------------
# Resolves and installs dependencies into .venv only, in a stage that never ships --
# keeps uv, the lockfile, and pip's build cache out of the runtime image entirely.
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Deps first, code after: cache-friendly (dependency layer only invalidates when
# pyproject.toml/uv.lock change, not on every app/*.py edit).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY app/ ./app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ---- runtime --------------------------------------------------------------
FROM python:3.13-slim AS runtime

# Cloud Run's own guidance (docs.cloud.google.com/run/docs/deploying#non-root-user):
# containers should run as a non-root user to shrink the attack surface.
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --no-create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/.venv ./.venv
COPY --chown=appuser:appuser app/ ./app/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    HOME=/tmp

USER appuser
EXPOSE 8080

# Cloud Run ignores this for routing traffic (it uses its own startup/liveness probes,
# configured separately -- see project README) but `docker run` locally still reports
# container health through it, which is what we test in CI/local smoke checks.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/health', timeout=2)" || exit 1

# Shell form (not exec-array) so $PORT expands -- Cloud Run injects PORT at runtime and
# the container must listen on whatever value that is, not a value baked in at build time.
CMD exec gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers 1 --threads 8 --timeout 0 \
    --bind :$PORT
