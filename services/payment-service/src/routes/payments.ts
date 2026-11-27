import { Router, Request, Response } from "express";
import { v4 as uuidv4 } from "uuid";
import pool from "../db";
import { paymentsTotal } from "../metrics";

const router = Router();

interface CreatePaymentBody {
  order_id: string;
  amount: number;
  currency?: string;
  customer_id: string;
}

// ---------------------------------------------------------------------------
// List payments (with optional filters)
// ---------------------------------------------------------------------------

router.get("/", async (req: Request, res: Response) => {
  const { order_id, customer_id } = req.query;

  try {
    let query = "SELECT * FROM payments";
    const params: string[] = [];
    const conditions: string[] = [];

    if (order_id) {
      params.push(order_id as string);
      conditions.push(`order_id = $${params.length}`);
    }
    if (customer_id) {
      params.push(customer_id as string);
      conditions.push(`customer_id = $${params.length}`);
    }

    if (conditions.length > 0) {
      query += " WHERE " + conditions.join(" AND ");
    }

    query += " ORDER BY created_at DESC";

    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch (err) {
    console.error("Error listing payments:", err);
    res.status(500).json({ error: "Failed to list payments" });
  }
});

// ---------------------------------------------------------------------------
// Create payment
// ---------------------------------------------------------------------------

router.post("/", async (req: Request, res: Response) => {
  const { order_id, amount, currency, customer_id } =
    req.body as CreatePaymentBody;

  if (!order_id || !amount || !customer_id) {
    paymentsTotal.inc({ operation: "create", outcome: "rejected" });
    res.status(400).json({ error: "Missing required fields: order_id, amount, customer_id" });
    return;
  }

  if (amount <= 0) {
    paymentsTotal.inc({ operation: "create", outcome: "rejected" });
    res.status(400).json({ error: "Amount must be positive" });
    return;
  }

  const id = uuidv4();
  const paymentCurrency = currency || "EUR";

  try {
    // Simulate payment processing (always succeeds for this challenge)
    const result = await pool.query(
      `INSERT INTO payments (id, order_id, amount, currency, customer_id, status)
       VALUES ($1, $2, $3, $4, $5, 'PROCESSED')
       RETURNING *`,
      [id, order_id, amount, paymentCurrency, customer_id]
    );

    paymentsTotal.inc({ operation: "create", outcome: "processed" });
    res.status(201).json(result.rows[0]);
  } catch (err) {
    paymentsTotal.inc({ operation: "create", outcome: "error" });
    console.error("Error creating payment:", err);
    res.status(500).json({ error: "Failed to process payment" });
  }
});

// ---------------------------------------------------------------------------
// Payment summary by customer
// IMPORTANT: must be before /:id to avoid being captured as an ID
// ---------------------------------------------------------------------------

router.get("/summary", async (req: Request, res: Response) => {
  const { customer_id } = req.query;

  if (!customer_id) {
    res.status(400).json({ error: "Missing required query parameter: customer_id" });
    return;
  }

  try {
    const result = await pool.query(
      `SELECT status, COUNT(*)::int AS count, COALESCE(SUM(amount), 0)::numeric AS amount
       FROM payments WHERE customer_id = $1 GROUP BY status`,
      [customer_id as string]
    );

    const byStatus: Record<string, { count: number; amount: string }> = {};
    let totalPayments = 0;
    let totalAmount = 0;

    for (const row of result.rows) {
      byStatus[row.status] = { count: row.count, amount: String(row.amount) };
      totalPayments += row.count;
      totalAmount += parseFloat(row.amount);
    }

    res.json({
      customer_id,
      total_payments: totalPayments,
      total_amount: totalAmount.toFixed(2),
      by_status: byStatus,
    });
  } catch (err) {
    console.error("Error fetching payment summary:", err);
    res.status(500).json({ error: "Failed to fetch payment summary" });
  }
});

// ---------------------------------------------------------------------------
// Get payments by order
// IMPORTANT: must be before /:id to avoid "order" being captured as an ID
// ---------------------------------------------------------------------------

router.get("/order/:orderId", async (req: Request, res: Response) => {
  const { orderId } = req.params;

  try {
    const result = await pool.query(
      "SELECT * FROM payments WHERE order_id = $1 ORDER BY created_at DESC",
      [orderId]
    );
    res.json(result.rows);
  } catch (err) {
    console.error("Error fetching payments by order:", err);
    res.status(500).json({ error: "Failed to fetch payments" });
  }
});

// ---------------------------------------------------------------------------
// Get payment by ID
// ---------------------------------------------------------------------------

router.get("/:id", async (req: Request, res: Response) => {
  const { id } = req.params;

  try {
    const result = await pool.query("SELECT * FROM payments WHERE id = $1", [
      id,
    ]);

    if (result.rows.length === 0) {
      res.status(404).json({ error: "Payment not found" });
      return;
    }

    res.json(result.rows[0]);
  } catch (err) {
    console.error("Error fetching payment:", err);
    res.status(500).json({ error: "Failed to fetch payment" });
  }
});

// ---------------------------------------------------------------------------
// Refund a payment
// ---------------------------------------------------------------------------

router.post("/:id/refund", async (req: Request, res: Response) => {
  const { id } = req.params;

  try {
    const existing = await pool.query("SELECT * FROM payments WHERE id = $1", [id]);

    if (existing.rows.length === 0) {
      paymentsTotal.inc({ operation: "refund", outcome: "not_found" });
      res.status(404).json({ error: "Payment not found" });
      return;
    }

    const payment = existing.rows[0];
    if (payment.status !== "PROCESSED") {
      paymentsTotal.inc({ operation: "refund", outcome: "conflict" });
      res.status(409).json({
        error: `Payment cannot be refunded: current status is ${payment.status}`,
      });
      return;
    }

    const result = await pool.query(
      "UPDATE payments SET status = 'REFUNDED', updated_at = NOW() WHERE id = $1 RETURNING *",
      [id]
    );

    paymentsTotal.inc({ operation: "refund", outcome: "refunded" });
    res.json(result.rows[0]);
  } catch (err) {
    paymentsTotal.inc({ operation: "refund", outcome: "error" });
    console.error("Error refunding payment:", err);
    res.status(500).json({ error: "Failed to refund payment" });
  }
});

export default router;
