import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

from app.db import get_pool
from app.metrics import RELEASES, RESERVATIONS

router = APIRouter(prefix="/api/inventory")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ReserveRequest(BaseModel):
    product_id: str
    quantity: int
    order_id: str | None = None

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v


class ReserveResponse(BaseModel):
    reservation_id: str
    product_id: str
    quantity: int
    status: str


class ProductResponse(BaseModel):
    product_id: str
    name: str
    quantity: int
    price: float


class CreateProductRequest(BaseModel):
    product_id: str
    name: str
    quantity: int
    price: float

    @field_validator("quantity")
    @classmethod
    def quantity_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("quantity must be >= 0")
        return v

    @field_validator("price")
    @classmethod
    def price_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("price must be > 0")
        return v


class RestockRequest(BaseModel):
    quantity: int

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v


class ReservationResponse(BaseModel):
    id: str
    product_id: str
    quantity: int
    order_id: str | None
    created_at: datetime | None


class ReleaseReservationResponse(BaseModel):
    reservation_id: str
    product_id: str
    quantity: int
    status: str


# ---------------------------------------------------------------------------
# Reservation endpoints
# ---------------------------------------------------------------------------


@router.post("/reserve", response_model=ReserveResponse, status_code=201)
async def reserve_inventory(req: ReserveRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:  # noqa: SIM117 - transaction scope reads clearer nested
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT quantity FROM products WHERE product_id = $1 FOR UPDATE",
                req.product_id,
            )
            if row is None:
                RESERVATIONS.labels("not_found").inc()
                raise HTTPException(status_code=404, detail=f"Product {req.product_id} not found")

            if row["quantity"] < req.quantity:
                RESERVATIONS.labels("insufficient_stock").inc()
                raise HTTPException(
                    status_code=409,
                    detail=f"Insufficient stock for {req.product_id}: available={row['quantity']}, requested={req.quantity}",
                )

            await conn.execute(
                "UPDATE products SET quantity = quantity - $1 WHERE product_id = $2",
                req.quantity,
                req.product_id,
            )

            reservation_id = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO reservations (id, product_id, quantity, order_id) VALUES ($1, $2, $3, $4)",
                reservation_id,
                req.product_id,
                req.quantity,
                req.order_id,
            )

    RESERVATIONS.labels("reserved").inc()
    return ReserveResponse(
        reservation_id=reservation_id,
        product_id=req.product_id,
        quantity=req.quantity,
        status="RESERVED",
    )


@router.get("/reservations", response_model=list[ReservationResponse])
async def list_reservations(order_id: str | None = Query(default=None)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if order_id:
            rows = await conn.fetch(
                "SELECT id, product_id, quantity, order_id, created_at FROM reservations WHERE order_id = $1",
                order_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, product_id, quantity, order_id, created_at FROM reservations"
            )
    return [ReservationResponse(**dict(r)) for r in rows]


@router.delete("/reservations/{reservation_id}", response_model=ReleaseReservationResponse)
async def release_reservation(reservation_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT id, product_id, quantity FROM reservations WHERE id = $1",
            reservation_id,
        )
        if row is None:
            RELEASES.labels("not_found").inc()
            raise HTTPException(status_code=404, detail=f"Reservation {reservation_id} not found")

        await conn.execute(
            "UPDATE products SET quantity = quantity + $1 WHERE product_id = $2",
            row["quantity"],
            row["product_id"],
        )
        await conn.execute(
            "DELETE FROM reservations WHERE id = $1",
            reservation_id,
        )

    RELEASES.labels("released").inc()
    return ReleaseReservationResponse(
        reservation_id=row["id"],
        product_id=row["product_id"],
        quantity=row["quantity"],
        status="RELEASED",
    )


# ---------------------------------------------------------------------------
# Product endpoints
# ---------------------------------------------------------------------------


@router.get("/products", response_model=list[ProductResponse])
async def list_products(in_stock: bool = Query(default=False)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if in_stock:
            rows = await conn.fetch(
                "SELECT product_id, name, quantity, price FROM products WHERE quantity > 0"
            )
        else:
            rows = await conn.fetch("SELECT product_id, name, quantity, price FROM products")
    return [ProductResponse(**dict(r)) for r in rows]


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(req: CreateProductRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT product_id FROM products WHERE product_id = $1",
            req.product_id,
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail=f"Product {req.product_id} already exists")

        await conn.execute(
            "INSERT INTO products (product_id, name, quantity, price) VALUES ($1, $2, $3, $4)",
            req.product_id,
            req.name,
            req.quantity,
            req.price,
        )
    return ProductResponse(
        product_id=req.product_id,
        name=req.name,
        quantity=req.quantity,
        price=req.price,
    )


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT product_id, name, quantity, price FROM products WHERE product_id = $1",
            product_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    return ProductResponse(**dict(row))


@router.patch("/products/{product_id}/stock", response_model=ProductResponse)
async def restock_product(product_id: str, req: RestockRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:  # noqa: SIM117 - transaction scope reads clearer nested
        async with conn.transaction():
            row = await conn.fetchrow(
                "UPDATE products SET quantity = quantity + $1 WHERE product_id = $2 RETURNING product_id, name, quantity, price",
                req.quantity,
                product_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    return ProductResponse(**dict(row))
