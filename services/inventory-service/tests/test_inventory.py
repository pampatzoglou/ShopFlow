"""Unit tests for the inventory service API routes.

Uses FastAPI's TestClient with a mocked asyncpg pool so no real database is needed.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# We need to mock the pool before importing the app, because the app
# lifespan calls init_db() which connects to a real DB.
@pytest.fixture(autouse=True)
def mock_pool():
    """Patch get_pool to return a mock pool for all tests."""
    pool = AsyncMock()
    with patch("app.routes.inventory.get_pool", return_value=pool) as _mock:
        yield pool


@pytest.fixture()
def client():
    """Create a TestClient that skips the real lifespan (no DB init)."""
    from app.routes.inventory import router
    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(router)
    return TestClient(test_app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_product_row(product_id="WIDGET-001", name="Standard Widget", quantity=100, price=24.99):
    """Return a dict-like mock row mimicking asyncpg.Record."""
    row = MagicMock()
    data = {"product_id": product_id, "name": name, "quantity": quantity, "price": price}
    row.__getitem__ = lambda self, key: data[key]
    row.__iter__ = lambda self: iter(data)
    row.keys = lambda: data.keys()
    row.values = lambda: data.values()
    row.items = lambda: data.items()
    return row


def _make_reservation_row(rid=None, product_id="WIDGET-001", quantity=2, order_id=None):
    row = MagicMock()
    data = {
        "id": rid or str(uuid.uuid4()),
        "product_id": product_id,
        "quantity": quantity,
        "order_id": order_id,
        "created_at": datetime.now(UTC),
    }
    row.__getitem__ = lambda self, key: data[key]
    row.__iter__ = lambda self: iter(data)
    row.keys = lambda: data.keys()
    row.values = lambda: data.values()
    row.items = lambda: data.items()
    return row


# ---------------------------------------------------------------------------
# List products
# ---------------------------------------------------------------------------


class TestListProducts:
    def test_list_products(self, client, mock_pool):
        rows = [
            _make_product_row("WIDGET-001", "Standard Widget", 100, 24.99),
            _make_product_row("GADGET-001", "Basic Gadget", 200, 9.99),
        ]
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=rows)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        resp = client.get("/api/inventory/products")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["product_id"] == "WIDGET-001"

    def test_list_products_in_stock(self, client, mock_pool):
        rows = [_make_product_row("WIDGET-001", "Standard Widget", 100, 24.99)]
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=rows)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        resp = client.get("/api/inventory/products?in_stock=true")
        assert resp.status_code == 200
        # Verify the query had the WHERE clause
        call_args = conn.fetch.call_args[0][0]
        assert "quantity > 0" in call_args


# ---------------------------------------------------------------------------
# Get single product
# ---------------------------------------------------------------------------


class TestGetProduct:
    def test_get_product(self, client, mock_pool):
        row = _make_product_row()
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=row)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        resp = client.get("/api/inventory/products/WIDGET-001")
        assert resp.status_code == 200
        assert resp.json()["product_id"] == "WIDGET-001"

    def test_get_product_not_found(self, client, mock_pool):
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        resp = client.get("/api/inventory/products/NONEXISTENT")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Create product
# ---------------------------------------------------------------------------


class TestCreateProduct:
    def test_create_product(self, client, mock_pool):
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)  # no existing product
        conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        resp = client.post(
            "/api/inventory/products",
            json={"product_id": "NEW-001", "name": "New Product", "quantity": 10, "price": 5.99},
        )
        assert resp.status_code == 201
        assert resp.json()["product_id"] == "NEW-001"

    def test_create_duplicate_product(self, client, mock_pool):
        existing = _make_product_row()
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=existing)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        resp = client.post(
            "/api/inventory/products",
            json={"product_id": "WIDGET-001", "name": "Dup", "quantity": 1, "price": 1.0},
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Restock
# ---------------------------------------------------------------------------


class TestRestockProduct:
    def test_restock_product(self, client, mock_pool):
        updated_row = _make_product_row(quantity=110)
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=updated_row)
        # Mock transaction context manager
        txn = AsyncMock()
        conn.transaction.return_value.__aenter__ = AsyncMock(return_value=txn)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        resp = client.patch(
            "/api/inventory/products/WIDGET-001/stock",
            json={"quantity": 10},
        )
        assert resp.status_code == 200
        assert resp.json()["quantity"] == 110

    def test_restock_nonexistent(self, client, mock_pool):
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        txn = AsyncMock()
        conn.transaction.return_value.__aenter__ = AsyncMock(return_value=txn)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        resp = client.patch(
            "/api/inventory/products/NONEXISTENT/stock",
            json={"quantity": 10},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Reserve inventory
# ---------------------------------------------------------------------------


class TestReserveInventory:
    def test_reserve_inventory(self, client, mock_pool):
        product_row = MagicMock()
        product_row.__getitem__ = lambda self, key: {"quantity": 100}[key]

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=product_row)
        conn.execute = AsyncMock()
        txn = AsyncMock()
        conn.transaction.return_value.__aenter__ = AsyncMock(return_value=txn)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        resp = client.post(
            "/api/inventory/reserve",
            json={"product_id": "WIDGET-001", "quantity": 5},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "RESERVED"

    def test_reserve_zero_quantity(self, client, mock_pool):
        resp = client.post(
            "/api/inventory/reserve",
            json={"product_id": "WIDGET-001", "quantity": 0},
        )
        assert resp.status_code == 422

    def test_reserve_negative_quantity(self, client, mock_pool):
        resp = client.post(
            "/api/inventory/reserve",
            json={"product_id": "WIDGET-001", "quantity": -5},
        )
        assert resp.status_code == 422

    def test_reserve_insufficient_stock(self, client, mock_pool):
        product_row = MagicMock()
        product_row.__getitem__ = lambda self, key: {"quantity": 2}[key]

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=product_row)
        txn = AsyncMock()
        conn.transaction.return_value.__aenter__ = AsyncMock(return_value=txn)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        resp = client.post(
            "/api/inventory/reserve",
            json={"product_id": "WIDGET-001", "quantity": 10},
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Release reservation
# ---------------------------------------------------------------------------


class TestReleaseReservation:
    def test_release_reservation(self, client, mock_pool):
        res_row = MagicMock()
        res_data = {"id": "res-123", "product_id": "WIDGET-001", "quantity": 3}
        res_row.__getitem__ = lambda self, key: res_data[key]

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=res_row)
        conn.execute = AsyncMock()
        txn = AsyncMock()
        conn.transaction.return_value.__aenter__ = AsyncMock(return_value=txn)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        resp = client.delete("/api/inventory/reservations/res-123")
        assert resp.status_code == 200
        assert resp.json()["status"] == "RELEASED"

    def test_release_nonexistent_reservation(self, client, mock_pool):
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        txn = AsyncMock()
        conn.transaction.return_value.__aenter__ = AsyncMock(return_value=txn)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

        resp = client.delete("/api/inventory/reservations/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Ready endpoint (from app.main, not the inventory router)
# ---------------------------------------------------------------------------


class TestReadyEndpoint:
    @pytest.fixture()
    def ready_client(self):
        """Client using the full app with lifespan disabled."""
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch("app.main.close_db", new_callable=AsyncMock),
        ):
            from app.main import app

            return TestClient(app)

    def test_ready_returns_200_when_db_up(self, ready_client):
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value=1)

        acquire_cm = AsyncMock()
        acquire_cm.__aenter__ = AsyncMock(return_value=conn)
        acquire_cm.__aexit__ = AsyncMock(return_value=False)

        pool = MagicMock()
        pool.acquire.return_value = acquire_cm

        with patch("app.main.get_pool", new_callable=AsyncMock, return_value=pool):
            resp = ready_client.get("/ready")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_ready_returns_503_when_db_down(self, ready_client):
        with patch("app.main.get_pool", side_effect=Exception("connection refused")):
            resp = ready_client.get("/ready")

        assert resp.status_code == 503
        assert resp.json()["status"] == "not_ready"
