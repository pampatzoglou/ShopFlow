"""Prometheus metrics: HTTP RED, DB pool state, and business counters.

Served on a separate port (METRICS_PORT, default 9090) so /metrics is never reachable
through the Service or the ingress gateway. Metric names match payment-service.
"""

import time

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    disable_created_metrics,
    start_http_server,
)

from app import db

# Drop the *_created series: nothing queries them and they double the series count.
disable_created_metrics()

HTTP_DURATION = Histogram(
    "http_server_request_duration_seconds",
    "HTTP request duration by method, route template and status code",
    ["method", "route", "status_code"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

# Business outcomes decided by the handler. Unexpected failures are not counted here:
# they surface as status_code="500" in HTTP_DURATION.
# outcome: reserved | not_found | insufficient_stock
RESERVATIONS = Counter(
    "shopflow_inventory_reservations",
    "Inventory reservation attempts by outcome",
    ["outcome"],
)

# outcome: released | not_found
RELEASES = Counter(
    "shopflow_inventory_releases",
    "Reservation releases by outcome",
    ["outcome"],
)


def _pool_value(read) -> float:
    pool = db.pool
    return float(read(pool)) if pool is not None else 0.0


# asyncpg has no waiter count; exhaustion = idle == 0 while size == max.
Gauge("shopflow_db_pool_connections", "Open DB connections").set_function(
    lambda: _pool_value(lambda p: p.get_size())
)
Gauge("shopflow_db_pool_idle_connections", "Idle DB connections").set_function(
    lambda: _pool_value(lambda p: p.get_idle_size())
)
Gauge("shopflow_db_pool_max_connections", "Configured pool size").set_function(
    lambda: _pool_value(lambda p: p.get_max_size())
)


class HTTPMetricsMiddleware:
    """Pure ASGI middleware. Labels by route *template* (FastAPI sets scope["route"] once
    routing has matched) to keep label cardinality bounded."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status = {"code": 500}
        start = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = getattr(scope.get("route"), "path", None) or "unmatched"
            HTTP_DURATION.labels(scope["method"], route, str(status["code"])).observe(
                time.perf_counter() - start
            )


def start_metrics_server(port: int):
    """Returns (server, thread); call server.shutdown() on exit."""
    return start_http_server(port, addr="0.0.0.0")
