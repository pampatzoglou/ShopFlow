# order-service

Helm chart for the order-service (Kotlin, Spring Boot): order orchestration over inventory-service and payment-service: Deployment, Service, ServiceAccount, the `-db` credentials
Secret, and optionally an Istio VirtualService, PodMonitor, PrometheusRule, HPA and PDB.

## Usage

The chart is rendered with layered values files; later files override earlier ones:

| Layer | File | Used by |
|---|---|---|
| base | `values.yaml` | everything; renders on a bare cluster (no Istio, no Prometheus CRDs) |
| cluster defaults | `defaults/values.yaml` | everything: hardening, sizing, metrics + alerts, gateway route |
| local | `local/values.yaml` | skaffold only: the Dockerfile `develop` stage runs as root with a writable root filesystem |
| dev / prod | `dev/values.yaml`, `prod/values.yaml` | ArgoCD (`deploy/argo/applicationset.yaml`) |

```bash
task template:order-service       # values.yaml + defaults → .argo/order-service/
task run MODULE=order-service     # build + deploy to the local kind cluster (adds local/)
helm template order-service . -n shopflow \
  -f values.yaml -f defaults/values.yaml -f dev/values.yaml
```

The release name is the Service name the other services call and the gateway prefix
(`/order-service`): keep it `order-service`.

`defaults/values.yaml` sets, for every cluster:
- non-root UID 65532, read-only root filesystem with a `/tmp` emptyDir, all capabilities
  dropped, `RuntimeDefault` seccomp
- resources: 250m / 512Mi requests, 1 CPU / 512Mi limits
- `JAVA_TOOL_OPTIONS=-XX:MaxRAMPercentage=75.0` (heap from the container limit)
- `networkPolicy` on, with the service's exact callers and callees (see the values table)
- `authorizationPolicy` on: the L7 counterpart, with the exact methods and paths per caller
- `virtualService` on `shopflow/shopflow-gateway`, `metrics` and `metrics.prometheusRule` on
  (scraped through the Istio sidecar, so `metrics.podMonitor` stays off)

## Values

| Key | Default | Description |
|---|---|---|
| `image.repository` / `image.tag` | `order-service` / `latest` | dev and prod use `ghcr.io/pampatzoglou/shopflow/order-service:main` |
| `image.digest` | `""` | `sha256:…`; takes precedence over the tag (prod: set by the ApplicationSet) |
| `image.requireDigest` | `false` | fail rendering without a digest (`true` in prod) |
| `image.pullPolicy` | `Never` | images loaded into kind; `Always` in dev/prod |
| `replicaCount` | `1` | ignored when `autoscaling.enabled` |
| `service.port` / `containerPort` | `8080` / `8080` | API port |
| `database.host` / `port` / `database` | `postgres.shopflow.svc.cluster.local` / `"5432"` / `orders` | `DB_HOST`, `DB_PORT`, `DB_NAME` |
| `database.username` / `password` | `postgres` / `postgres` | chart-internal Secret `<release>-db` |
| `database.externalSecret.enable` / `.name` | `false` / `""` | use an existing Secret instead (`usernameKey`, `passwordKey`) |
| `database.vault.enable` / `.path` + `vault.role` | `false` / `""` / `""` | Vault dynamic credentials via a VaultDynamicSecret + ExternalSecret |
| `env.SERVER_PORT` | `"8080"` | |
| `env.INVENTORY_SERVICE_URL` | `http://inventory-service:8080` | |
| `env.PAYMENT_SERVICE_URL` | `http://payment-service:8080` | |
| `env.*` | | any further plain env var (map, so layers merge) |
| `virtualService.enabled` | `false` | Istio route `<prefix>/*` → this Service, prefix stripped |
| `virtualService.prefix` / `gateways` / `timeout` | `/<release>` / `[]` / `""` | `gateways` as `<namespace>/<name>` |
| `metrics.enabled` / `port` / `path` | `false` / `9090` / `/metrics` | metrics port + `prometheus.io/*` annotations for Istio metrics merging |
| `metrics.podMonitor.enabled` | `false` | direct scrape, for clusters without the sidecar (never together with the mesh scrape) |
| `metrics.prometheusRule.enabled` | `false` | ship the alerts below |
| `metrics.prometheusRule.errorRate` | `threshold: 0.05`, `minRequestRate: 0.1`, `for: 10m` | 5xx ratio of inbound requests |
| `metrics.prometheusRule.latency` | `p99Milliseconds: 1000`, `for: 10m` | inbound p99 |
| `metrics.prometheusRule.upstreamErrorRate` | `threshold: 0.05`, `minRequestRate: 0.1`, `for: 10m` | failed outbound calls per destination |
| `metrics.prometheusRule.memory` | `limitRatio: 0.9`, `for: 15m` | working set / memory limit |
| `metrics.prometheusRule.jvmHeap` | `ratio: 0.9`, `for: 10m` | JVM heap used / max |
| `metrics.prometheusRule.dbPoolPending` | `for: 5m` | HikariCP threads waiting for a connection |
| `metrics.prometheusRule.orderFailureRate` | `threshold: 0.1`, `minRate: 0.05`, `for: 10m` | failed / all orders (`shopflow_orders_total`) |
| `metrics.prometheusRule.extraRules` | `[]` | extra raw rules, appended as a group |
| `autoscaling.enabled` | `false` | HPA (`minReplicas` 1, `maxReplicas` 3, 80% CPU); needs metrics-server |
| `pdb.enabled` | `false` | PodDisruptionBudget (`maxUnavailable: 1`) |
| `authorizationPolicy.enabled` / `rules` | `false` / `[]` | Istio ALLOW rules (by caller principal, method, path; `{*}` = one segment), rendered through `tpl`. `defaults/` enables: the ingress gateway gets everything, peers only the calls they make. The chart's `helm test` pod may `GET /health` |
| `networkPolicy.enabled` / `ingress` / `egress` | `false` / `[]` / `[]` | allow-list NetworkPolicy; rules through `tpl`. `defaults/` enables: ingress from the ingress gateway, payment-service, inventory-service and Prometheus (:15020, `metrics`); egress to DNS, istiod :15012, PostgreSQL :5432, inventory-service, payment-service :8080. The chart's `helm test` pod is always allowed in |
| `resources`, `podSecurityContext`, `securityContext` | `{}` | set in `defaults/values.yaml` |
| `extraObjects` | `[]` | extra manifests, rendered through `tpl` |

`values.schema.json` validates the types of the main keys at `helm lint` / `helm template`.
