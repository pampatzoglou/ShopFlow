# shopflow-infra

Umbrella chart for everything the ShopFlow services need on the local kind cluster except
Istio: monitoring, Kafka, PostgreSQL, Kafka UI, Grafana and the ingress Gateway, as one Helm
release.

## Usage

```bash
task cluster:infra     # install / upgrade (part of `task cluster:up` and `task deploy`)
```

which runs, after registering the chart repositories and building the dependencies:

```bash
helm upgrade --install shopflow-infra deploy/local/charts/shopflow-infra \
  --kube-context kind-shopflow --namespace kafka-system --create-namespace \
  --wait=watcher --timeout 10m
```

- **Release namespace `kafka-system`**: the Strimzi chart can only install into the release
  namespace; every other component sets its own namespace.
- **Istio first**: the chart creates the `shopflow` pods, which only get sidecars if Istio's
  injector is already running (`task cluster:istio`).
- **No install hooks**: hooks run before the chart's Namespaces exist, so the
  kube-prometheus-stack admission webhooks (hook-provisioned) are disabled.

| Namespace | Component | Source |
|---|---|---|
| `kafka-system` | Strimzi cluster operator (watches `shopflow`) | `strimzi-kafka-operator` subchart |
| `monitoring` | Prometheus Operator, Prometheus, Alertmanager, stack Grafana, kube-state-metrics, node-exporter | `kube-prometheus-stack` subchart |
| `monitoring` | Grafana operator; stack Grafana registered as an external instance | `grafana-operator` subchart, `templates/monitoring/` |
| `kube-system` | metrics-server | `metrics-server` subchart |
| `shopflow` | Kafka cluster `shopflow` (KRaft, 1 node, pods opted out of the mesh), topics, metrics PodMonitor, Kafka Exporter | `templates/kafka/` |
| `shopflow` | PostgreSQL | `templates/postgres/` |
| `shopflow` | Kafka UI (kafbat) at `/kafka` | `templates/kafka-ui/` |
| `shopflow` | ShopFlow Grafana, its folder and datasources, at `/grafana` | `templates/grafana/` |
| `shopflow` | Gateway `shopflow-gateway` and the `/kafka`, `/grafana` VirtualServices | `templates/gateway/` |
| `shopflow` | AuthorizationPolicies: namespace default-deny, PostgreSQL, Kafka UI, Grafana | `templates/mesh/` |
| | Namespaces `shopflow` (Istio injection), `monitoring`; kept on uninstall | `templates/namespaces.yaml` |

Dashboards are not part of the chart: they are `GrafanaDashboard` resources in
`deploy/dashboards/`, applied by `task cluster:dashboards`. Dependency versions are locked in
`Chart.lock`; `task deps:update` re-resolves them.

## Values

| Key | Default | Description |
|---|---|---|
| `namespace` | `shopflow` | namespace of PostgreSQL, Kafka UI, Grafana and the Gateway |
| `namespaces.<name>.labels` | `shopflow: {istio-injection: enabled}` | namespaces created by the release |
| `postgres.enabled` | `true` | |
| `postgres.serviceName` | `postgres` | Service name the service charts connect to: keep it |
| `postgres.auth.username` / `password` | `postgres` / `postgres` | stored in the `postgres-auth` Secret |
| `postgres.databases` | `[orders, payments, inventory]` | created on first start only |
| `postgres.persistence.size` | `1Gi` | |
| `kafka.enabled` / `namespace` / `name` | `true` / `shopflow` / `shopflow` | bootstrap `<name>-kafka-bootstrap.<namespace>.svc:9092` |
| `kafka.version` / `replicas` | `4.3.2` / `1` | |
| `kafka.podLabels` | `sidecar.istio.io/inject: "false"` | on every Kafka pod: keeps Kafka out of the mesh |
| `kafka.autoCreateTopics` | `false` | topics must be declared in `kafka.topics` |
| `kafka.topics` | `[]` | `{name, partitions, replicas, config}` per KafkaTopic |
| `kafka.storage.size` / `deleteClaim` | `2Gi` / `true` | |
| `kafka.metrics.enabled` / `allowList` | `true` / broker, replica, controller, request, log, JVM families | Strimzi metrics reporter + Kafka Exporter |
| `kafkaUi.enabled` / `contextPath` | `true` / `/kafka` | served under the path the gateway routes |
| `grafana.enabled` / `version` | `true` / `13.3.1` | operator-managed instance in `namespace` |
| `grafana.anonymousAdmin` | `true` | no login; anonymous users are Admin |
| `grafana.rootUrl` / `route.prefix` | `http://localhost:30080/grafana/` / `/grafana` | must match each other |
| `grafana.instanceLabels` | `grafana: shopflow` | selector for datasources and dashboards |
| `grafana.datasources.kafka.enabled` | `true` | Kafka datasource plugin |
| `grafana.resyncPeriod` | `1m` | how fast a restarted (ephemeral) Grafana is repopulated |
| `mesh.authorization.enabled` | `true` | default-deny AuthorizationPolicy for `namespace`, plus allows for PostgreSQL (`databaseClients` on 5432), Kafka UI (gateway) and Grafana (gateway + operator) |
| `mesh.authorization.ingressGatewayPrincipal` / `grafanaOperatorPrincipal` | gateway and operator service accounts | identities the allows refer to |
| `gateway.enabled` / `name` / `selector` | `true` / `shopflow-gateway` / `istio: ingressgateway` | HTTP :80 on the ingress gateway, hosts `*` |
| `stackGrafana.enabled` | `true` | register the stack Grafana with the operator |
| `kube-prometheus-stack.*` | see `values.yaml` | names pinned to `kube-prometheus-stack-*`; envoy-stats PodMonitor and istiod ServiceMonitor |
| `grafana-operator.*` | | cluster-wide, in `monitoring` |
| `metrics-server.*` | | `kube-system`, `--kubelet-insecure-tls` for kind |
| `strimzi-kafka-operator.*` | `watchNamespaces: [shopflow]` | must include `kafka.namespace` |
