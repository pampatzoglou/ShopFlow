# TODO

Open work for the ShopFlow platform. Check items off (or delete them) in the same change that
completes them.

## Challenge status

| Task | Done | Open |
|---|---|---|
| 1. IaC | Helm charts per service (layered values), Istio VirtualServices with prefix strip, `task deploy` (kind → Istio → `shopflow-infra` → skaffold), E2E 30/30 | charts are three near-copies: a shared library chart would make the "reusable module" explicit |
| 2. Metrics + alerting | business counters (orders, cancellations, payments, reservations/releases), latency histograms, PodMonitors (app + Envoy), 11 PrometheusRule alerts, 3 GrafanaDashboard CRs | revenue amounts; partial-failure detection (see Observability) |
| 3. Kafka | Strimzi KRaft cluster in `shopflow`, Kafka UI at `/kafka`, broker metrics + Kafka Exporter, Grafana Kafka datasource | business events from the services (out of scope for now, below) |
| 4. mTLS + authz (bonus) | NetworkPolicies per service; default-deny AuthorizationPolicy + per-caller method/path rules; Grafana operator in the mesh | STRICT PeerAuthentication |
| Submission | `transcripts/` with exports | commit + push (SSH key, `gh` account), private repo + collaborators, final transcript export |

Also done beyond the brief: devbox with pinned tools and devcontainer parity
(`task ci:versions`), CI (lint/build on push, kind E2E + k6 on PRs to main), Dependabot +
devbox-update workflow, release/promotion workflow and ArgoCD ApplicationSet, k6 load test
(`task test:k6s`), `task destroy`, kind-context guard on every cluster task and skaffold,
anonymous Grafana for local dev, docs (README, ARCHITECTURE, api, chart READMEs).

## Retire `scripts/` (minikube era)

The kind-based Taskfile flow (`task deploy` / `test` / `cluster:down` / `clean`) replaces these
scripts. Each script stays until every step it performed is covered below; then delete it.
Only `scripts/run-tests.sh` is left.

### `scripts/setup-cluster.sh` → `task setup` (alias of `cluster:up`)

- [x] Create cluster → `cluster:create` (kind, `deploy/local/kind/cluster.yaml`)
- [x] Istio, demo profile, egress gateway disabled → `cluster:istio`
      (`deploy/local/istio/istio.yaml`, devbox-pinned istioctl instead of `downloadIstio`).
      Stays outside the umbrella: it must run before any shopflow pod is created.
- [x] Everything else is the `shopflow-infra` umbrella release (`cluster:infra`, release
      namespace `kafka-system`):
  - [x] `shopflow` namespace with `istio-injection=enabled` (plus `monitoring`),
        templated with `helm.sh/resource-policy: keep`
  - [x] Prometheus + Grafana addons → kube-prometheus-stack + Grafana operator subcharts
        (`monitoring`), envoy-stats PodMonitor and istiod ServiceMonitor
  - [x] PostgreSQL with `orders` / `payments` / `inventory` databases, wait for ready
  - [x] Kafka: Strimzi operator subchart (`kafka-system`) + KRaft cluster (`shopflow`, pods out of the mesh), Kafka UI
        (own templates, `shopflow`), broker metrics + Kafka Exporter
  - [x] ShopFlow Grafana (`shopflow`) with Prometheus / Alertmanager / Kafka datasources;
        dashboards are `GrafanaDashboard` CRs in `deploy/dashboards/` (`cluster:dashboards`)
- [x] **Verify the umbrella from scratch**: fresh cluster → `cluster:up` → `run` → `test`
      (30/30). Kafka UI runs with a read-only root filesystem; re-running `cluster:infra` is
      an idempotent upgrade. Needed kube-prometheus-stack's admission webhooks off: their
      pre-install hook Jobs run before the chart's Namespaces exist.
- [x] **metrics-server** (minikube addon) → `metrics-server` subchart of `shopflow-infra`
      (`kube-system`, `--kubelet-insecure-tls`); `kubectl top` works.
- [x] Post-setup summary → `cluster:up` ends with endpoints and next steps.
- [x] Deleted `scripts/setup-cluster.sh`.

### `scripts/run-tests.sh` → `task test:e2e`

`task test` now runs `test:e2e` then `test:k6s` (k6 load test, `.k6s/checkout.js`).

- [x] venv + `pip install -r requirements.txt` + `pytest -v --tb=short --timeout=180`
- [x] Gateway access: port-forward replaced by kind's `extraPortMappings` (localhost:30080)
- [ ] **Gateway readiness check**: the script verified the gateway accepted connections
      before running pytest and failed with a clear message. `task test:e2e` goes straight to
      pytest; add a `preconditions:` curl against `{{.GATEWAY_URL}}` (shared with
      `test:k6s`, whose `setup()` already fails fast on unhealthy services).
- [ ] Delete `scripts/run-tests.sh`.

### Tests

- [ ] **E2E suite drains stock**: each `test:e2e` run orders 10× WIDGET-001 without
      cancelling (and restocks GADGET-001 +10, and leaves a `TEST-*` product behind). After
      ~9 runs on one cluster, `test_create_order_reserves_inventory_and_processes_payment`
      fails on `initial_stock > 0`. The k6 test is stock-neutral (cancels every order) and
      never orders WIDGET-001. Fix in the suite (cancel/clean up) or reseed in a fixture.
- [ ] **`task test` needs k6**: the challenge is evaluated with `task test` on a fresh
      machine. k6 is pinned in devbox.json; outside devbox, `test:k6s` stops with a clear
      message. Decide whether `test` should skip k6 when absent, or document the requirement.

### `scripts/teardown-cluster.sh` → `task cluster:down`

- [x] Delete the cluster → `cluster:down` (with `prompt:`)
- [x] Remove the `istio-*` download dir: no longer created (istioctl comes from devbox)
- [x] Remove `e2e/.venv` → `task clean` (also `.argo/` and the charts' dependency `.tgz`);
      full teardown is `task cluster:down clean`.
- [x] Deleted `scripts/teardown-cluster.sh`.

## Delivery

- [x] **`task deploy`** = `cluster:up` (kind → Istio → `shopflow-infra` umbrella →
      dashboards) + `run` (skaffold: build, load into kind, deploy the service charts).
      Converges an existing cluster; CI's E2E job runs `task deploy` + `task test`.
- [ ] **Clean-clone run of `task deploy`**: verified on an existing cluster and in pieces
      from scratch (`cluster:up` → `run` → `test`), not yet as one `task deploy` on a fresh
      machine outside devbox. The first PR run of CI covers this.
- [ ] **What `task deploy` ships**: skaffold builds the Dockerfiles' `develop` stage with the
      charts' `local/values.yaml` overlay (root, writable rootfs). Decide whether `deploy`
      should ship the hardened `production` stage instead (a skaffold profile), keeping the
      develop build for `task dev`.

## GitOps (`deploy/argo/applicationset.yaml`)

- [x] **Publish images to ghcr**: `.github/workflows/release.yaml` → `task publish:<svc>`
      pushes `:main` and `:sha-<commit>` for each service changed on `main`.
- [x] **Prod promotion**: the same workflow runs `task promote:prod` and keeps one rolling PR
      (`promote/prod`) that pins prod's chart commit and image digests in the ApplicationSet.
- [ ] **Bootstrap prod**: prod's `revision` is still `8b7466b` (the initial commit, which has
      no `deploy/charts/`) and all digests are empty. After the first push to `main`, run the
      Release workflow by hand (workflow_dispatch builds every service) and merge its PR.
- [ ] **Repo settings for Release**: enable "Allow GitHub Actions to create and approve pull
      requests"; make the three ghcr packages public, or add an imagePullSecret to the
      charts and clusters (they are created private on first push).
- [ ] **Gate prod rollouts**: require review on `deploy/argo/` (CODEOWNERS + branch
      protection), since merging the promotion PR is the prod deploy.
- [ ] Promotion PRs are opened with `GITHUB_TOKEN`, so CI doesn't run on them. If CI must
      gate them, switch `create-pull-request` to a GitHub App token
      (`actions/create-github-app-token`).
- [ ] **Register the clusters** in ArgoCD as `dev` and `prod` (destination names), and add
      the app-of-apps in the platform repo pointing at `deploy/argo/`.
- [ ] **Per-cluster dependencies**: each cluster needs Istio (with CNI: the namespace is PSA
      `restricted`), the `shopflow/shopflow-gateway` Gateway, PostgreSQL at `database.host`,
      and kube-prometheus-stack CRDs (PodMonitor/PrometheusRule). Today these come only from
      `task setup` on kind (Istio + the `shopflow-infra` umbrella, which is local-only:
      in-cluster PostgreSQL with static credentials, single-node Kafka).
- [ ] **Prod DB credentials**: base values carry `postgres`/`postgres` in a chart Secret.
      Switch prod to `database.externalSecret` or `database.vault`.
- [ ] Dedicated `AppProject` (source repo + destinations whitelist) instead of `default`.
- [ ] Verify generation against a real ArgoCD: `argocd appset generate deploy/argo/applicationset.yaml`.

## Business events to Kafka (out of scope for now)

Challenge Task 3 also asks the services to publish business events. Kafka and Kafka UI are
deployed (`shopflow-kafka-bootstrap.shopflow.svc.cluster.local:9092`, UI at `/kafka`); the
services don't produce anything yet.

- [ ] **Topics** in `shopflow-infra` `kafka.topics` (auto-create is off): `shopflow.orders`,
      `shopflow.payments`, `shopflow.inventory`, keyed by order id / product id.
- [ ] **Event envelope**: CloudEvents 1.0 JSON (`id`, `type`, `source`, `time`, `subject`,
      `data`), documented in `docs/events.md`.
- [ ] **order-service** (spring-kafka 3.3.1, managed by the Spring Boot BOM):
      `order.completed` (with amount), `order.failed` (failing `step`, and whether stock is
      still reserved: the "stock set aside, no payment" case), `order.cancelled`,
      `order.cancellation_failed` (which of refund / release went through).
- [ ] **payment-service** (`@platformatic/kafka`: pure TypeScript, maintained; kafkajs has had
      no release since 2023): `payment.processed`, `payment.rejected`, `payment.refunded`,
      `payment.refund_rejected`, all with amount and currency (closes most of the revenue gap).
- [ ] **inventory-service** (aiokafka 0.15): `stock.reserved`, `stock.reservation_rejected`
      (insufficient stock / unknown product), `stock.released`, `stock.restocked`,
      `product.created`, `product.out_of_stock` when stock reaches 0.
- [ ] **Delivery semantics**: start with publish-after-commit, best effort (a Kafka outage
      must not fail an order), counted in `shopflow_events_published_total{type, outcome}` with
      an alert on failures. A transactional outbox per service is the consistent follow-up.
- [ ] **Network policy egress to Kafka**: the service charts' NetworkPolicies (defaults/) only
      allow DNS, istiod, PostgreSQL and the peer services; add egress to the Kafka pods
      (`strimzi.io/cluster: shopflow`, port 9092) for producers.
- [ ] **Config**: `KAFKA_BOOTSTRAP_SERVERS` via each chart's `env`; publishing disabled when
      unset (dev/prod clusters have no Kafka yet), so unit tests need no broker.
- [ ] **Verification**: E2E test that places an order and finds its events through the Kafka
      UI API (`/kafka/api/clusters/shopflow/topics/<topic>/messages`); the Kafka dashboard's
      per-topic panels start showing data.

## Observability

- [ ] **Revenue metrics**: the business needs money collected and refunded, not just counts.
      `shopflow_payments_total` counts operations only. Add amount counters in
      payment-service (e.g. `shopflow_payment_amount_total{operation, currency}`), plus a
      Grafana dashboard and the README queries.
- [ ] **Partial-failure detection without service code changes (future)**: a reconciliation
      exporter that reads the three databases and turns cross-service inconsistencies into
      metrics. Every inconsistency is a query: orders store `payment_id`/`reservation_id`,
      payments and reservations store `order_id`.
      - **Component**: [sql_exporter](https://github.com/burningalchemist/sql_exporter) in
        `shopflow-infra`, with a read-only DB user, a sidecar and an entry in the PostgreSQL
        AuthorizationPolicy (`mesh.authorization.databaseClients`). The databases are separate,
        so enable `dblink` (PostgreSQL contrib) for the cross-database joins.
      - **Gauges (count, plus amount where money is involved)**:
        - `FAILED` order that still holds a reservation: the create path marks the order
          FAILED without releasing stock;
        - payment `COMPLETED` whose order is `FAILED` or missing: charged, no order;
        - order `PENDING` for longer than N minutes: died mid-checkout;
        - order `COMPLETED` with payment `REFUNDED`: cancel refunded, then failed to release
          or update;
        - order `CANCELLED` with payment not `REFUNDED`, or with a reservation left.
      - **Alerts**: PrometheusRule per gauge with a grace period (`for: 2m`–`5m`) so in-flight
        orders don't fire, plus an alert on exporter query errors (a schema change breaks the
        queries silently).
      - **Bonus**: the same exporter can report revenue (`sum(amount)` by payment status), as
        a stop-gap for the revenue item above.
      - **Trade-offs**: couples to the services' table layouts; detection lags by scrape
        interval + grace period. The real fix (compensation on failure, proper cancellation
        handling) stays in the service code; the exporter remains a safety net.
      - **Cheaper early warning**: PromQL over the existing counters (successful reservations
        vs completed orders + releases). Rates only: no per-order view, no persistence.
- [ ] payment-service sets a default `application` label that nothing uses and the other
      services don't emit; drop it or apply it consistently.
- [ ] **Kafka panels** (per-topic throughput, consumer lag, log size) stay empty until the
      services publish events (Task 3). Revisit them, and add Kafka datasource panels for the
      business topics, once topics exist.
- [ ] **Two Grafanas**: the operator also registers kube-prometheus-stack's Grafana
      (`stackGrafana` in `shopflow-infra`). Keep it for cluster-level dashboards, or drop it
      and the stack Grafana if the ShopFlow instance is enough.

## Security posture
- [ ] **Ingress (prod)**: block `/health` and other internal endpoints at the gateway.
- [ ] **In-cluster kubescape** for environment-specific posture. `task lint` scans only the
      shared baseline (`values.yaml` + `defaults/values.yaml`); the ArgoCD overlays
      (`<chart>/dev|prod/values.yaml`) and the skaffold overlay (`<chart>/local/values.yaml`:
      root, writable rootfs for the `develop` stage) are intentionally not gated in CI.
      Install the kubescape operator in the cluster to cover what is actually running.
- [x] **Authorization policies (Task 4)**: default-deny in `shopflow` (shopflow-infra), per-service
      ALLOW rules by caller identity, method and path (service charts, `defaults/`), PostgreSQL /
      Kafka UI / Grafana allows. Verified: E2E + k6 pass; payment->order `/api/orders` 403 while
      `/health` 200; inventory->payment `POST /api/payments` 403; kafka-ui->PostgreSQL rejected.
- [x] **NetworkPolicies** in the three service charts (`defaults/`): ingress from the gateway,
      peers and Prometheus; egress to DNS, istiod, PostgreSQL and the called peers. Verified
      enforced on kind (non-listed callers time out); probes, scraping, E2E + k6 still pass.
- [x] **Kafka in `shopflow`** (was `kafka`): pods opted out of the mesh, Strimzi watches
      `shopflow`; Kafka UI, Grafana datasource and dashboard queries verified.
- [x] Grafana operator in the mesh (pod label `sidecar.istio.io/inject: "true"`): its Grafana API
      calls are mTLS with identity `monitoring/sa/grafana-operator`.
- [ ] **STRICT PeerAuthentication** for `shopflow` (the remaining Task 4 step).
- [ ] **Umbrella upgrades restart PostgreSQL and Kafka**: `shopflow-infra.labels` puts
      `helm.sh/chart` (with the chart version) on pod templates, so every chart version bump
      rolls every pod. Keep the version label off pod templates (metadata only).
- [ ] **payment-service crashes when PostgreSQL restarts**: `src/db.ts` has no
      `pool.on("error")`, so a dropped idle connection is an unhandled error and the process
      exits (under `node --watch` it then stays down until the liveness probe restarts it).
- [x] **STRICT mTLS exception: Grafana operator** (no sidecar, calling the Grafana API in
      `shopflow`): resolved by putting the operator in the mesh (above).
- [ ] **STRICT mTLS exception: Kafka** (in `shopflow`, pods opt out of the mesh) is reached in
      plaintext by meshed clients: still works under STRICT, but unencrypted. Enable a Strimzi
      TLS listener if that matters.
