import express from "express";
import axios from "axios";
import { checkDbHealth } from "./db";
import paymentsRouter from "./routes/payments";
import { httpMetrics } from "./metrics";

const app = express();

app.use(httpMetrics);

const ORDER_SERVICE_URL =
  process.env.ORDER_SERVICE_URL || "http://localhost:8080";
const INVENTORY_SERVICE_URL =
  process.env.INVENTORY_SERVICE_URL || "http://localhost:8082";

app.use(express.json());

// Health check — liveness
app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    service: "payment-service",
    timestamp: new Date().toISOString(),
  });
});

// Readiness check — includes DB
app.get("/ready", async (_req, res) => {
  const dbUp = await checkDbHealth();
  const checks = {
    database: { status: dbUp ? "up" : "down" },
  };

  if (!dbUp) {
    res.status(503).json({ status: "not_ready", checks });
    return;
  }

  res.json({ status: "ready", checks });
});

// Connectivity check — can we reach other services?
app.get("/api/connectivity", async (_req, res) => {
  const checkService = async (
    name: string,
    url: string
  ): Promise<Record<string, unknown>> => {
    try {
      const start = Date.now();
      const response = await axios.get(`${url}/health`, { timeout: 5000 });
      return {
        reachable: response.status === 200,
        url,
        latency_ms: Date.now() - start,
      };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return { reachable: false, url, error: message };
    }
  };

  const [orderStatus, inventoryStatus] = await Promise.all([
    checkService("order-service", ORDER_SERVICE_URL),
    checkService("inventory-service", INVENTORY_SERVICE_URL),
  ]);

  res.json({
    service: "payment-service",
    connections: {
      "order-service": orderStatus,
      "inventory-service": inventoryStatus,
    },
  });
});

// Payment routes
app.use("/api/payments", paymentsRouter);

export default app;
