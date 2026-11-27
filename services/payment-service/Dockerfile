# syntax=docker/dockerfile:1
# ── base ──────────────────────────────────────────────────────────────────────
# Shared foundation. Node 22 LTS — Node 20 is end-of-life. Debian 13 (glibc) to match
# the distroless runtime, so any native module built here runs there.
FROM node:22-trixie-slim AS base
WORKDIR /app

# ── build ─────────────────────────────────────────────────────────────────────
# All dependencies (incl. TypeScript) → compile to dist/.
FROM base AS build
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY tsconfig.json ./
COPY src/ src/
RUN npm run build

# ── prod-deps ─────────────────────────────────────────────────────────────────
# Runtime-only node_modules, resolved independently of the compile so dev
# dependencies never reach the production image.
FROM base AS prod-deps
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev --no-audit --no-fund

# ── develop ───────────────────────────────────────────────────────────────────
# Used by docker-compose / skaffold. Bind-mount src/ for restart-on-change.
FROM build AS develop
ENV PORT=8080
EXPOSE 8080 9090
CMD ["node", "--watch", "--require", "ts-node/register", "src/index.ts"]

# ── production ────────────────────────────────────────────────────────────────
# Distroless Node 22, built-in nonroot user (65532 — mirrored by the chart's runAsUser).
# Digest is the multi-arch manifest list for gcr.io/distroless/nodejs22-debian13:nonroot.
FROM gcr.io/distroless/nodejs22-debian13:nonroot@sha256:39c66687298417dbf3ff2fb8b6012c20554494e16414ef7afd07b9abbb45b501 AS production
LABEL org.opencontainers.image.title="payment-service"

ENV NODE_ENV=production \
    PORT=8080
WORKDIR /app
COPY --from=prod-deps --chown=65532:65532 /app/node_modules ./node_modules
COPY --from=build --chown=65532:65532 /app/package.json ./package.json
COPY --from=build --chown=65532:65532 /app/dist ./dist

VOLUME ["/tmp"]
USER 65532:65532
EXPOSE 8080 9090
# The distroless entrypoint is the node binary; CMD is its argument.
CMD ["dist/index.js"]
