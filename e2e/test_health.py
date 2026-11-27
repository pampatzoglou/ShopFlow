import requests


class TestServiceHealth:
    """Verify all services are running and responding to health checks."""

    def test_order_service_is_healthy(self, order_url):
        r = requests.get(f"{order_url}/health", timeout=10)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        body = r.json()
        assert body["status"] == "ok"
        assert body["service"] == "order-service"

    def test_payment_service_is_healthy(self, payment_url):
        r = requests.get(f"{payment_url}/health", timeout=10)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        body = r.json()
        assert body["status"] == "ok"
        assert body["service"] == "payment-service"

    def test_inventory_service_is_healthy(self, inventory_url):
        r = requests.get(f"{inventory_url}/health", timeout=10)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        body = r.json()
        assert body["status"] == "ok"
        assert body["service"] == "inventory-service"
