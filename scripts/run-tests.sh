#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-shopflow}"
GATEWAY_PORT="${GATEWAY_PORT:-30080}"

cleanup() {
    echo "Cleaning up port-forwards..."
    kill $PF_GW 2>/dev/null || true
}
trap cleanup EXIT

# Port-forward the Istio ingress gateway
kubectl port-forward svc/istio-ingressgateway -n istio-system "${GATEWAY_PORT}:80" &
PF_GW=$!

# Wait for the port-forward to be ready and verify it stays alive
MAX_WAIT=10
for _ in $(seq 1 $MAX_WAIT); do
    if ! kill -0 $PF_GW 2>/dev/null; then
        echo ""
        echo "ERROR: port-forward to istio-ingressgateway died."
        echo "The Istio ingress gateway is not accepting connections on port 8080."
        exit 1
    fi
    # Check if the port is actually reachable
    if curl -sf -o /dev/null "http://localhost:${GATEWAY_PORT}" 2>/dev/null || \
       curl -sf -o /dev/null --max-time 1 "http://localhost:${GATEWAY_PORT}" 2>/dev/null; then
        break
    fi
    sleep 1
done

# Final check that port-forward is still alive
if ! kill -0 $PF_GW 2>/dev/null; then
    echo ""
    echo "ERROR: port-forward to istio-ingressgateway died."
    echo "The Istio ingress gateway is not accepting connections on port 8080."
    exit 1
fi

# Setup venv and run tests
cd "$(dirname "$0")/../e2e"
python3 -m venv .venv 2>/dev/null || true
# shellcheck source=/dev/null
. .venv/bin/activate
pip install -q -r requirements.txt

GATEWAY_URL="http://localhost:${GATEWAY_PORT}" \
pytest -v --tb=short --timeout=180
