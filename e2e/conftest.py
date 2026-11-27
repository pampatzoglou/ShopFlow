import os
import time

import pytest
import requests

# kind maps the ingress gateway NodePort to localhost:30080 (deploy/local/kind/cluster.yaml).
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:30080")

ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", f"{GATEWAY_URL}/order-service")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", f"{GATEWAY_URL}/payment-service")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", f"{GATEWAY_URL}/inventory-service")


@pytest.fixture(scope="session")
def order_url():
    return ORDER_SERVICE_URL


@pytest.fixture(scope="session")
def payment_url():
    return PAYMENT_SERVICE_URL


@pytest.fixture(scope="session")
def inventory_url():
    return INVENTORY_SERVICE_URL


@pytest.fixture(scope="session", autouse=True)
def wait_for_services(order_url, payment_url, inventory_url):
    """Wait up to 120s for all services to become healthy."""
    services = {
        "order-service": f"{order_url}/health",
        "payment-service": f"{payment_url}/health",
        "inventory-service": f"{inventory_url}/health",
    }
    deadline = time.time() + 120

    for name, url in services.items():
        while time.time() < deadline:
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    break
            except requests.ConnectionError:
                pass
            time.sleep(2)
        else:
            pytest.fail(f"{name} did not become healthy within 120s at {url}")
