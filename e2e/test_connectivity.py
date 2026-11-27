import requests


class TestServiceConnectivity:
    """Verify services can communicate with each other inside the cluster."""

    def test_order_can_reach_payment(self, order_url):
        r = requests.get(f"{order_url}/api/connectivity", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["connections"]["payment-service"]["reachable"] is True, (
            f"Order service cannot reach payment service: {body['connections']['payment-service']}"
        )

    def test_order_can_reach_inventory(self, order_url):
        r = requests.get(f"{order_url}/api/connectivity", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["connections"]["inventory-service"]["reachable"] is True, (
            f"Order service cannot reach inventory service: {body['connections']['inventory-service']}"
        )

    def test_payment_can_reach_inventory(self, payment_url):
        r = requests.get(f"{payment_url}/api/connectivity", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["connections"]["inventory-service"]["reachable"] is True, (
            f"Payment service cannot reach inventory service: {body['connections']['inventory-service']}"
        )
