import pytest
import requests


class TestOrderFlow:
    """End-to-end test of the full order processing flow."""

    @pytest.mark.timeout(60)
    def test_create_order_reserves_inventory_and_processes_payment(
        self, order_url, payment_url, inventory_url
    ):
        # 1. Check initial inventory for WIDGET-001
        inv_resp = requests.get(f"{inventory_url}/api/inventory/products/WIDGET-001", timeout=10)
        assert inv_resp.status_code == 200, f"Could not fetch product: {inv_resp.text}"
        initial_stock = inv_resp.json()["quantity"]
        assert initial_stock > 0, "WIDGET-001 has no stock — seed data may be missing"

        # 2. Create an order
        order_resp = requests.post(
            f"{order_url}/api/orders",
            json={
                "productId": "WIDGET-001",
                "quantity": 2,
                "customerId": "test-customer-e2e",
            },
            timeout=30,
        )
        assert order_resp.status_code == 201, f"Failed to create order: {order_resp.text}"
        order = order_resp.json()
        order_id = order["id"]
        assert order["status"] == "COMPLETED", (
            f"Order status is {order['status']}, expected COMPLETED"
        )

        # 3. Verify order can be retrieved
        get_resp = requests.get(f"{order_url}/api/orders/{order_id}", timeout=10)
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "COMPLETED"

        # 4. Verify payment was created
        payment_id = order.get("paymentId") or order.get("payment_id")
        assert payment_id is not None, f"Order response missing paymentId: {order}"
        pay_resp = requests.get(f"{payment_url}/api/payments/{payment_id}", timeout=10)
        assert pay_resp.status_code == 200, f"Payment not found: {pay_resp.text}"
        assert pay_resp.json()["status"] == "PROCESSED"

        # 5. Verify inventory was decremented
        inv_after = requests.get(f"{inventory_url}/api/inventory/products/WIDGET-001", timeout=10)
        assert inv_after.status_code == 200
        new_stock = inv_after.json()["quantity"]
        assert new_stock == initial_stock - 2, (
            f"Expected stock {initial_stock - 2}, got {new_stock}"
        )
