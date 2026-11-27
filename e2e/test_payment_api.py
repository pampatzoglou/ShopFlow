import uuid

import pytest
import requests


class TestPaymentAPI:
    """Tests for the payment service extended API."""

    def _create_order(self, order_url, customer_id=None):
        """Helper: create an order and return (order_id, payment_id)."""
        cid = customer_id or f"test-pay-{uuid.uuid4().hex[:8]}"
        resp = requests.post(
            f"{order_url}/api/orders",
            json={
                "productId": "WIDGET-001",
                "quantity": 1,
                "customerId": cid,
            },
            timeout=30,
        )
        assert resp.status_code == 201, f"Failed to create order: {resp.text}"
        order = resp.json()
        payment_id = order.get("paymentId") or order.get("payment_id")
        assert payment_id is not None, f"Order missing paymentId: {order}"
        return order["id"], payment_id, cid

    @pytest.mark.timeout(60)
    def test_list_payments_by_order(self, order_url, payment_url):
        """GET /api/payments/order/:orderId returns payments for that order."""
        order_id, payment_id, _ = self._create_order(order_url)

        resp = requests.get(f"{payment_url}/api/payments/order/{order_id}", timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        payments = resp.json()
        assert isinstance(payments, list)
        assert len(payments) >= 1
        assert any(p["id"] == payment_id for p in payments), (
            f"Expected payment {payment_id} in response"
        )

    @pytest.mark.timeout(60)
    def test_refund_payment(self, order_url, payment_url):
        """POST /api/payments/:id/refund transitions a PROCESSED payment to REFUNDED."""
        _, payment_id, _ = self._create_order(order_url)

        # Refund
        refund_resp = requests.post(f"{payment_url}/api/payments/{payment_id}/refund", timeout=10)
        assert refund_resp.status_code == 200, f"Refund failed: {refund_resp.text}"
        assert refund_resp.json()["status"] == "REFUNDED"

        # Verify persisted
        get_resp = requests.get(f"{payment_url}/api/payments/{payment_id}", timeout=10)
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "REFUNDED"

    @pytest.mark.timeout(60)
    def test_refund_already_refunded_returns_409(self, order_url, payment_url):
        """Refunding an already-refunded payment returns 409."""
        _, payment_id, _ = self._create_order(order_url)

        # First refund succeeds
        first = requests.post(f"{payment_url}/api/payments/{payment_id}/refund", timeout=10)
        assert first.status_code == 200

        # Second refund returns 409
        second = requests.post(f"{payment_url}/api/payments/{payment_id}/refund", timeout=10)
        assert second.status_code == 409, f"Expected 409, got {second.status_code}: {second.text}"

    @pytest.mark.timeout(30)
    def test_refund_nonexistent_returns_404(self, payment_url):
        """Refunding a non-existent payment returns 404."""
        resp = requests.post(f"{payment_url}/api/payments/nonexistent-id/refund", timeout=10)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    @pytest.mark.timeout(60)
    def test_payment_summary(self, order_url, payment_url):
        """GET /api/payments/summary returns aggregate stats for a customer."""
        customer_id = f"summary-test-{uuid.uuid4().hex[:8]}"

        # Create 2 orders for this customer
        _, pay_id_1, _ = self._create_order(order_url, customer_id=customer_id)
        self._create_order(order_url, customer_id=customer_id)

        # Refund one payment
        refund_resp = requests.post(f"{payment_url}/api/payments/{pay_id_1}/refund", timeout=10)
        assert refund_resp.status_code == 200

        # Get summary
        summary_resp = requests.get(
            f"{payment_url}/api/payments/summary",
            params={"customer_id": customer_id},
            timeout=10,
        )
        assert summary_resp.status_code == 200, (
            f"Expected 200, got {summary_resp.status_code}: {summary_resp.text}"
        )

        summary = summary_resp.json()
        assert summary["customer_id"] == customer_id
        assert summary["total_payments"] == 2
        assert "by_status" in summary
        assert "PROCESSED" in summary["by_status"]
        assert "REFUNDED" in summary["by_status"]
        assert summary["by_status"]["PROCESSED"]["count"] == 1
        assert summary["by_status"]["REFUNDED"]["count"] == 1
