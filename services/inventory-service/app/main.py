import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.db import close_db, get_pool, init_db
from app.metrics import HTTPMetricsMiddleware, start_metrics_server
from app.routes.inventory import router as inventory_router

ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://localhost:8080")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8081")
METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Up before the DB is, so a DB outage is still visible in metrics.
    metrics_server, _ = start_metrics_server(METRICS_PORT)
    try:
        await init_db()
        yield
        await close_db()
    finally:
        metrics_server.shutdown()


app = FastAPI(title="Inventory Service", lifespan=lifespan)
app.add_middleware(HTTPMetricsMiddleware)
app.include_router(inventory_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "inventory-service",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.get("/ready")
async def ready():
    checks: dict = {}

    # Check database
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["database"] = {"status": "up"}
    except Exception as e:  # noqa: BLE001 - readiness reports any DB failure as down
        checks["database"] = {"status": "down", "error": str(e)}
        return JSONResponse(status_code=503, content={"status": "not_ready", "checks": checks})

    return {"status": "ready", "checks": checks}


async def _check_service(client: httpx.AsyncClient, name: str, url: str) -> dict:
    try:
        r = await client.get(f"{url}/health", timeout=5.0)
        return {"reachable": r.status_code == 200, "url": url, "status_code": r.status_code}
    except Exception as e:  # noqa: BLE001 - any probe failure means unreachable
        return {"reachable": False, "url": url, "error": str(e)}


@app.get("/api/connectivity")
async def connectivity():
    async with httpx.AsyncClient() as client:
        order = await _check_service(client, "order-service", ORDER_SERVICE_URL)
        payment = await _check_service(client, "payment-service", PAYMENT_SERVICE_URL)

    return {
        "service": "inventory-service",
        "connections": {
            "order-service": order,
            "payment-service": payment,
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8082"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
