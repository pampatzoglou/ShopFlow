# ShopFlow

[![Default](https://github.com/pampatzoglou/ShopFlow/actions/workflows/default.yaml/badge.svg)](https://github.com/pampatzoglou/ShopFlow/actions/workflows/default.yaml)

Order processing on Kubernetes: three services (orders, payments, inventory) behind an Istio
ingress gateway, with PostgreSQL, Kafka, Prometheus/Grafana and a kind-based local platform
that CI also runs end to end. The original challenge brief is in
[docs/CHALLENGE.md](docs/CHALLENGE.md).

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- One of:
  - [devbox](https://www.jetify.com/devbox): `devbox shell` (or `direnv allow` once) installs the
    pinned toolchain from `devbox.json`: kind, kubectl, helm, istioctl, skaffold, go-task, k6,
    Java, Node, Python and the linters.
  - The [devcontainer](.devcontainer/) (prebuilt
    [`ghcr.io/pampatzoglou/devcontainer`](https://github.com/pampatzoglou/devcontainer) image):
    the same tools at the same versions (`task ci:versions` keeps devbox, the devcontainer and
    CI identical).

## Quick start

```bash
task deploy    # kind cluster → Istio → shopflow-infra umbrella → dashboards → services
task test      # E2E suite, then the k6 load test, through the gateway
```

`task deploy` converges an existing cluster, so it is also the upgrade command. Then:

| URL | |
|---|---|
| `http://localhost:30080/<service>/…` | `order-service`, `payment-service`, `inventory-service` ([API](docs/api.md)) |
| `http://localhost:30080/grafana` | Grafana, no login; dashboards in the ShopFlow folder |
| `http://localhost:30080/kafka` | Kafka UI |

Everyday tasks (`task --list` has them all):

| Task | |
|---|---|
| `task dev` | skaffold watch loop (`MODULE=<service>` for one) |
| `task run` / `task undeploy` | deploy / remove the services only |
| `task test:e2e` / `task test:k6s` | one suite (`K6_PROFILE=smoke` for a 30 s k6 run) |
| `task lint` | hadolint, helm lint, kubescape, dashboards, toolchain parity |
| `task status` | pods, Helm releases, routes, warning events |
| `task destroy` | delete the cluster, its port-forwards, built images and generated files: back to before `task deploy` |

All cluster tasks only ever target the local kind context (`kind-shopflow`) and refuse
anything else.

## Repository layout

```
services/<service>/     source + Dockerfile (base → build → develop | production)
deploy/charts/<svc>/    service Helm charts; values.yaml → defaults/ → dev|prod|local/
deploy/local/           kind config, Istio (istioctl) and the shopflow-infra umbrella chart
deploy/dashboards/      GrafanaDashboard custom resources
deploy/argo/            ArgoCD ApplicationSet: services × dev/prod clusters
e2e/                    pytest E2E suite (through the gateway)
.k6s/                   k6 load test
.github/                CI, release/promotion and devbox-update workflows
scripts/                helpers called by tasks (version parity, promotion, change detection)
skaffold.yaml           local build + deploy of the services
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): components, request flows, environments,
  CI/CD, observability, security
- [docs/api.md](docs/api.md): HTTP API of the three services
- Charts: [order-service](deploy/charts/order-service/README.md),
  [payment-service](deploy/charts/payment-service/README.md),
  [inventory-service](deploy/charts/inventory-service/README.md),
  [shopflow-infra](deploy/local/charts/shopflow-infra/README.md)
- [TODO.md](TODO.md): open work
