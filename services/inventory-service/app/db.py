import os

import asyncpg

pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "inventory"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres"),
            min_size=2,
            max_size=10,
        )
    return pool


async def init_db():
    p = await get_pool()
    async with p.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                price NUMERIC(10, 2) NOT NULL DEFAULT 0.00
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL REFERENCES products(product_id),
                quantity INTEGER NOT NULL,
                order_id TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Seed data — upsert so it's idempotent
        await conn.execute("""
            INSERT INTO products (product_id, name, quantity, price) VALUES
                ('WIDGET-001', 'Standard Widget', 100, 24.99),
                ('WIDGET-002', 'Premium Widget', 50, 49.99),
                ('GADGET-001', 'Basic Gadget', 200, 9.99)
            ON CONFLICT (product_id) DO NOTHING
        """)


async def close_db():
    global pool
    if pool is not None:
        await pool.close()
        pool = None
