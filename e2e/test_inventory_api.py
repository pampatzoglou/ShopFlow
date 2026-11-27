import uuid

import pytest
import requests


class TestInventoryAPI:
    """Tests for the inventory service extended API."""

    @pytest.mark.timeout(30)
    def test_list_all_products(self, inventory_url):
        """GET /api/inventory/products returns all products including seed data."""
        resp = requests.get(f"{inventory_url}/api/inventory/products", timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        products = resp.json()
        assert isinstance(products, list)
        assert len(products) >= 3, f"Expected at least 3 seed products, got {len(products)}"

        product_ids = [p["product_id"] for p in products]
        for expected_id in ["WIDGET-001", "WIDGET-002", "GADGET-001"]:
            assert expected_id in product_ids, f"Seed product {expected_id} not found in listing"

        for product in products:
            assert "product_id" in product
            assert "name" in product
            assert "quantity" in product
            assert "price" in product

    @pytest.mark.timeout(30)
    def test_list_products_in_stock_filter(self, inventory_url):
        """GET /api/inventory/products?in_stock=true returns only products with qty > 0."""
        resp = requests.get(
            f"{inventory_url}/api/inventory/products",
            params={"in_stock": "true"},
            timeout=10,
        )
        assert resp.status_code == 200
        products = resp.json()
        assert isinstance(products, list)

        for product in products:
            assert product["quantity"] > 0, (
                f"Product {product['product_id']} has quantity {product['quantity']} "
                "but should only be returned when in_stock=true"
            )

    @pytest.mark.timeout(30)
    def test_create_product(self, inventory_url):
        """POST /api/inventory/products creates a new product, retrievable via GET."""
        product_id = f"TEST-{uuid.uuid4().hex[:8].upper()}"
        create_resp = requests.post(
            f"{inventory_url}/api/inventory/products",
            json={
                "product_id": product_id,
                "name": "E2E Test Product",
                "quantity": 10,
                "price": 5.99,
            },
            timeout=10,
        )
        assert create_resp.status_code == 201, (
            f"Expected 201, got {create_resp.status_code}: {create_resp.text}"
        )

        created = create_resp.json()
        assert created["product_id"] == product_id
        assert created["name"] == "E2E Test Product"
        assert created["quantity"] == 10

        # Verify via GET
        get_resp = requests.get(f"{inventory_url}/api/inventory/products/{product_id}", timeout=10)
        assert get_resp.status_code == 200
        assert get_resp.json()["product_id"] == product_id

    @pytest.mark.timeout(30)
    def test_create_duplicate_product_returns_409(self, inventory_url):
        """POST /api/inventory/products with an existing product_id returns 409."""
        resp = requests.post(
            f"{inventory_url}/api/inventory/products",
            json={
                "product_id": "WIDGET-001",
                "name": "Duplicate Widget",
                "quantity": 5,
                "price": 1.00,
            },
            timeout=10,
        )
        assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"

    @pytest.mark.timeout(30)
    def test_restock_product(self, inventory_url):
        """PATCH /api/inventory/products/{id}/stock increases the product quantity."""
        # Get current stock
        before = requests.get(f"{inventory_url}/api/inventory/products/GADGET-001", timeout=10)
        assert before.status_code == 200
        initial_qty = before.json()["quantity"]

        # Restock
        restock_resp = requests.patch(
            f"{inventory_url}/api/inventory/products/GADGET-001/stock",
            json={"quantity": 10},
            timeout=10,
        )
        assert restock_resp.status_code == 200, (
            f"Expected 200, got {restock_resp.status_code}: {restock_resp.text}"
        )

        updated = restock_resp.json()
        assert updated["quantity"] == initial_qty + 10, (
            f"Expected quantity {initial_qty + 10}, got {updated['quantity']}"
        )

    @pytest.mark.timeout(30)
    def test_restock_nonexistent_product_returns_404(self, inventory_url):
        """PATCH /api/inventory/products/NONEXISTENT/stock returns 404."""
        resp = requests.patch(
            f"{inventory_url}/api/inventory/products/NONEXISTENT-PRODUCT/stock",
            json={"quantity": 10},
            timeout=10,
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    @pytest.mark.timeout(60)
    def test_release_reservation_restores_stock(self, inventory_url):
        """Reserve inventory, then release it, verifying stock is restored."""
        # Get initial stock
        before = requests.get(f"{inventory_url}/api/inventory/products/WIDGET-002", timeout=10)
        assert before.status_code == 200
        initial_qty = before.json()["quantity"]
        assert initial_qty >= 3, f"Not enough stock for test: {initial_qty}"

        # Reserve 3 units
        reserve_resp = requests.post(
            f"{inventory_url}/api/inventory/reserve",
            json={"product_id": "WIDGET-002", "quantity": 3},
            timeout=10,
        )
        assert reserve_resp.status_code == 201, f"Reserve failed: {reserve_resp.text}"
        reservation_id = reserve_resp.json()["reservation_id"]

        # Verify stock decreased
        after_reserve = requests.get(
            f"{inventory_url}/api/inventory/products/WIDGET-002", timeout=10
        )
        assert after_reserve.json()["quantity"] == initial_qty - 3

        # Release the reservation
        release_resp = requests.delete(
            f"{inventory_url}/api/inventory/reservations/{reservation_id}", timeout=10
        )
        assert release_resp.status_code == 200, f"Release failed: {release_resp.text}"
        assert release_resp.json()["status"] == "RELEASED"

        # Verify stock restored
        after_release = requests.get(
            f"{inventory_url}/api/inventory/products/WIDGET-002", timeout=10
        )
        assert after_release.json()["quantity"] == initial_qty, (
            f"Expected stock restored to {initial_qty}, got {after_release.json()['quantity']}"
        )
