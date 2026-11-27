# syntax=docker/dockerfile:1
# ── base ──────────────────────────────────────────────────────────────────────
# Shared foundation: JDK + WORKDIR. No application code, no app user.
FROM eclipse-temurin:21-jdk AS base
WORKDIR /app

# ── build ─────────────────────────────────────────────────────────────────────
# Gradle cache lives in a layer (not a cache mount) so `develop` inherits the
# resolved dependencies and bootRun starts without re-downloading them.
FROM base AS build
ENV GRADLE_USER_HOME=/gradle

# 1. Wrapper + build scripts first — this layer survives source-only edits.
COPY --chmod=0755 gradlew ./
COPY gradle/wrapper/ gradle/wrapper/
COPY settings.gradle.kts build.gradle.kts ./
RUN ./gradlew dependencies --no-daemon --quiet

# 2. Source, then the boot jar.
COPY src/ src/
RUN ./gradlew bootJar --no-daemon --quiet

# 3. Explode the jar into Spring Boot layers (deps change rarely, app code often),
#    so production copies them as separate, independently cached image layers.
RUN java -Djarmode=tools -jar build/libs/*.jar \
        extract --layers --launcher --destination /app/extracted && \
    mkdir -p /app/extracted/dependencies /app/extracted/spring-boot-loader \
             /app/extracted/snapshot-dependencies /app/extracted/application

# ── develop ───────────────────────────────────────────────────────────────────
# Used by docker-compose / skaffold. Bind-mount src/ and restart to pick up edits.
FROM build AS develop
EXPOSE 8080 9090
CMD ["./gradlew", "bootRun", "--no-daemon"]

# ── production ────────────────────────────────────────────────────────────────
# Distroless JRE, built-in nonroot user (65532 — mirrored by the chart's runAsUser).
# Digest is the multi-arch manifest list for gcr.io/distroless/java21-debian13:nonroot.
FROM gcr.io/distroless/java21-debian13:nonroot@sha256:6b60e44d652d66a9e2e584364c96adac4df7133674b2834b6f71741b7cdb1ff3 AS production
LABEL org.opencontainers.image.title="order-service"

WORKDIR /app
# Least → most frequently changing, so a code change only ships the last layer.
COPY --from=build --chown=65532:65532 /app/extracted/dependencies/ ./
COPY --from=build --chown=65532:65532 /app/extracted/spring-boot-loader/ ./
COPY --from=build --chown=65532:65532 /app/extracted/snapshot-dependencies/ ./
COPY --from=build --chown=65532:65532 /app/extracted/application/ ./

# Embedded Tomcat writes its work/upload dirs under java.io.tmpdir.
VOLUME ["/tmp"]
USER 65532:65532
EXPOSE 8080 9090
ENTRYPOINT ["/usr/bin/java", "org.springframework.boot.loader.launch.JarLauncher"]
