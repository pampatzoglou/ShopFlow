import requests


class TestDatabaseConnectivity:
    """Verify all services can connect to their databases."""

    def test_order_service_db_ready(self, order_url):
        r = requests.get(f"{order_url}/ready", timeout=10)
        assert r.status_code == 200, f"Order service not ready: {r.text}"
        body = r.json()
        assert body["checks"]["database"]["status"] == "up", (
            f"Order service database is not up: {body['checks']['database']}"
        )

    def test_payment_service_db_ready(self, payment_url):
        r = requests.get(f"{payment_url}/ready", timeout=10)
        assert r.status_code == 200, f"Payment service not ready: {r.text}"
        body = r.json()
        assert body["checks"]["database"]["status"] == "up", (
            f"Payment service database is not up: {body['checks']['database']}"
        )

    def test_inventory_service_db_ready(self, inventory_url):
        r = requests.get(f"{inventory_url}/ready", timeout=10)
        assert r.status_code == 200, f"Inventory service not ready: {r.text}"
        body = r.json()
        assert body["checks"]["database"]["status"] == "up", (
            f"Inventory service database is not up: {body['checks']['database']}"
        )
