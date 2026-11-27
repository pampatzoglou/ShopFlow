import uuid

import pytest
import requests


class TestOrderAPI:
    """Tests for the order service extended API."""

    def _create_order(self, order_url, customer_id=None, product_id="WIDGET-001", quantity=1):
        """Helper: create an order and return the full order dict."""
        cid = customer_id or f"test-order-{uuid.uuid4().hex[:8]}"
        resp = requests.post(
            f"{order_url}/api/orders",
            json={
                "productId": product_id,
                "quantity": quantity,
                "customerId": cid,
            },
            timeout=30,
        )
        assert resp.status_code == 201, f"Failed to create order: {resp.text}"
        return resp.json()

    @pytest.mark.timeout(60)
    def test_list_orders(self, order_url):
        """GET /api/orders returns a list containing created orders."""
        order = self._create_order(order_url)

        resp = requests.get(f"{order_url}/api/orders", timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        orders = resp.json()
        assert isinstance(orders, list)
        order_ids = [o["id"] for o in orders]
        assert order["id"] in order_ids, f"Created order {order['id']} not found in listing"

    @pytest.mark.timeout(60)
    def test_list_orders_filter_by_customer(self, order_url):
        """GET /api/orders?customerId=x returns only that customer's orders."""
        customer_id = f"filter-cust-{uuid.uuid4().hex[:8]}"
        self._create_order(order_url, customer_id=customer_id)

        resp = requests.get(
            f"{order_url}/api/orders",
            params={"customerId": customer_id},
            timeout=10,
        )
        assert resp.status_code == 200

        orders = resp.json()
        assert len(orders) >= 1
        for order in orders:
            assert order["customerId"] == customer_id, (
                f"Expected customerId {customer_id}, got {order['customerId']}"
            )

    @pytest.mark.timeout(60)
    def test_list_orders_filter_by_status(self, order_url):
        """GET /api/orders?status=COMPLETED returns only completed orders."""
        resp = requests.get(
            f"{order_url}/api/orders",
            params={"status": "COMPLETED"},
            timeout=10,
        )
        assert resp.status_code == 200

        orders = resp.json()
        for order in orders:
            assert order["status"] == "COMPLETED", (
                f"Expected status COMPLETED, got {order['status']}"
            )

    @pytest.mark.timeout(90)
    def test_cancel_order_full_flow(self, order_url, payment_url, inventory_url):
        """Cancel a completed order: payment is refunded, inventory is restored."""
        # Get initial stock
        inv_before = requests.get(f"{inventory_url}/api/inventory/products/WIDGET-001", timeout=10)
        assert inv_before.status_code == 200
        initial_stock = inv_before.json()["quantity"]

        # Create an order
        order = self._create_order(order_url, product_id="WIDGET-001", quantity=1)
        order_id = order["id"]
        payment_id = order.get("paymentId") or order.get("payment_id")
        assert order["status"] == "COMPLETED"

        # Verify stock decreased
        inv_after_order = requests.get(
            f"{inventory_url}/api/inventory/products/WIDGET-001", timeout=10
        )
        assert inv_after_order.json()["quantity"] == initial_stock - 1

        # Cancel the order
        cancel_resp = requests.post(f"{order_url}/api/orders/{order_id}/cancel", timeout=30)
        assert cancel_resp.status_code == 200, f"Cancel failed: {cancel_resp.text}"
        cancelled = cancel_resp.json()
        assert cancelled["status"] == "CANCELLED"

        # Verify payment is refunded
        pay_resp = requests.get(f"{payment_url}/api/payments/{payment_id}", timeout=10)
        assert pay_resp.status_code == 200
        assert pay_resp.json()["status"] == "REFUNDED"

        # Verify inventory is restored
        inv_after_cancel = requests.get(
            f"{inventory_url}/api/inventory/products/WIDGET-001", timeout=10
        )
        assert inv_after_cancel.json()["quantity"] == initial_stock, (
            f"Expected stock restored to {initial_stock}, got {inv_after_cancel.json()['quantity']}"
        )

    @pytest.mark.timeout(30)
    def test_cancel_nonexistent_order_returns_404(self, order_url):
        """POST /api/orders/nonexistent/cancel returns 404."""
        resp = requests.post(f"{order_url}/api/orders/nonexistent-order-id/cancel", timeout=10)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    @pytest.mark.timeout(90)
    def test_cancel_already_cancelled_returns_409(self, order_url):
        """Cancelling an already-cancelled order returns 409."""
        order = self._create_order(order_url)
        order_id = order["id"]

        # Cancel first time
        first = requests.post(f"{order_url}/api/orders/{order_id}/cancel", timeout=30)
        assert first.status_code == 200

        # Cancel again
        second = requests.post(f"{order_url}/api/orders/{order_id}/cancel", timeout=10)
        assert second.status_code == 409, f"Expected 409, got {second.status_code}: {second.text}"

    @pytest.mark.timeout(60)
    def test_get_order_details(self, order_url):
        """GET /api/orders/{id}/details returns order with payment and product info."""
        order = self._create_order(order_url)
        order_id = order["id"]

        resp = requests.get(f"{order_url}/api/orders/{order_id}/details", timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        details = resp.json()
        assert "order" in details
        assert "payment" in details
        assert "product" in details

        assert details["order"]["id"] == order_id
        assert details["order"]["status"] == "COMPLETED"
        assert details["payment"] is not None
        assert details["payment"]["status"] == "PROCESSED"
        assert details["product"] is not None
        assert details["product"]["product_id"] == "WIDGET-001"

    @pytest.mark.timeout(60)
    def test_create_order_insufficient_stock_returns_422(self, order_url):
        """Creating an order with quantity exceeding stock returns 422."""
        resp = requests.post(
            f"{order_url}/api/orders",
            json={
                "productId": "GADGET-001",
                "quantity": 999999,
                "customerId": "test-insufficient-stock",
            },
            timeout=30,
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
