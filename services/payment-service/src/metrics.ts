import http from "http";
import { NextFunction, Request, Response } from "express";
import { Counter, Gauge, Histogram, Registry, collectDefaultMetrics } from "prom-client";
import pool from "./db";

export const register = new Registry();
register.setDefaultLabels({ application: "payment-service" });

// process_* and nodejs_* (heap, GC, event-loop lag, active handles).
collectDefaultMetrics({ register });

const httpDuration = new Histogram({
  name: "http_server_request_duration_seconds",
  help: "HTTP request duration by method, route template and status code",
  labelNames: ["method", "route", "status_code"] as const,
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
  registers: [register],
});

// Business events. outcome per operation:
//   create: processed | rejected (validation) | error
//   refund: refunded | not_found | conflict (not refundable) | error
export const paymentsTotal = new Counter({
  name: "shopflow_payments_total",
  help: "Payment operations by outcome",
  labelNames: ["operation", "outcome"] as const,
  registers: [register],
});

// pg.Pool state, read at scrape time. `waiting` > 0 means requests are queued for a
// connection: the pool (max) is too small or queries are slow.
const poolGauge = (name: string, help: string, read: () => number | undefined) =>
  new Gauge({
    name,
    help,
    registers: [register],
    collect() {
      this.set(read() ?? 0);
    },
  });
poolGauge("shopflow_db_pool_connections", "Open DB connections", () => pool.totalCount);
poolGauge("shopflow_db_pool_idle_connections", "Idle DB connections", () => pool.idleCount);
poolGauge("shopflow_db_pool_waiting_clients", "Requests waiting for a DB connection", () => pool.waitingCount);
poolGauge("shopflow_db_pool_max_connections", "Configured pool size", () => pool.options?.max);

// Route *template* (e.g. /api/payments/:id), never the raw URL, to bound cardinality.
export function httpMetrics(req: Request, res: Response, next: NextFunction): void {
  const end = httpDuration.startTimer();
  res.on("finish", () => {
    const route = req.route?.path !== undefined ? `${req.baseUrl}${req.route.path}` : "unmatched";
    end({ method: req.method, route, status_code: String(res.statusCode) });
  });
  next();
}

// Separate port so /metrics is never reachable through the Service or the ingress gateway.
export function startMetricsServer(port: number): http.Server {
  const server = http.createServer(async (req, res) => {
    if (req.method !== "GET" || req.url?.split("?")[0] !== "/metrics") {
      res.writeHead(404).end();
      return;
    }
    try {
      const body = await register.metrics();
      res.writeHead(200, { "Content-Type": register.contentType }).end(body);
    } catch (err) {
      console.error("Error collecting metrics:", err);
      res.writeHead(500).end();
    }
  });
  server.listen(port, "0.0.0.0", () => {
    console.log(`Metrics listening on port ${port}`);
  });
  return server;
}
