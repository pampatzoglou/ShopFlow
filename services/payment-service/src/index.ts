import { initDb } from "./db";
import app from "./app";
import { startMetricsServer } from "./metrics";

const PORT = parseInt(process.env.PORT || "8081");
const METRICS_PORT = parseInt(process.env.METRICS_PORT || "9090");

// Up before the DB is, so a DB outage is still visible in metrics.
startMetricsServer(METRICS_PORT);

// Start server
async function start() {
  try {
    await initDb();
    console.log("Database initialized");
  } catch (err) {
    console.error("Failed to initialize database, retrying in 5s...", err);
    setTimeout(start, 5000);
    return;
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Payment service listening on port ${PORT}`);
  });
}

start();
