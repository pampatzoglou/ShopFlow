# syntax=docker/dockerfile:1
# Every stage uses the same digest-pinned interpreter: the venv built in `build`
# links to /usr/local/bin/python3, which must be byte-identical in `production`.
# Not distroless: distroless Python ships the distro interpreter (3.11 on debian12,
# 3.13 on debian13), and the service and its compiled wheels target 3.12.
ARG PYTHON_IMAGE=python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

# ── base ──────────────────────────────────────────────────────────────────────
FROM ${PYTHON_IMAGE} AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# ── build ─────────────────────────────────────────────────────────────────────
# Dependencies into a self-contained venv, then source, then precompiled bytecode
# (the read-only production rootfs can't write __pycache__ at runtime).
FROM base AS build
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY app/ app/
RUN python -m compileall -q app

# ── develop ───────────────────────────────────────────────────────────────────
# Used by docker-compose / skaffold. Bind-mount app/ for hot reload
# (watchfiles ships with uvicorn[standard]).
FROM build AS develop
ENV UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8080
EXPOSE 8080 9090
CMD ["uvicorn", "app.main:app", "--reload"]

# ── production ────────────────────────────────────────────────────────────────
FROM ${PYTHON_IMAGE} AS production
LABEL org.opencontainers.image.title="inventory-service"

# uid/gid 65532 to match the distroless images and the chart's runAsUser.
RUN groupadd --system --gid 65532 app && \
    useradd --system --uid 65532 --gid app --no-create-home --shell /usr/sbin/nologin app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8080
WORKDIR /app
COPY --from=build --chown=app:app /opt/venv /opt/venv
COPY --from=build --chown=app:app /app/app ./app

VOLUME ["/tmp"]
USER 65532:65532
EXPOSE 8080 9090
CMD ["uvicorn", "app.main:app"]
