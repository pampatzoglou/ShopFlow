import request from "supertest";

// Mock the pg pool before importing the app
const mockQuery = jest.fn();
jest.mock("../../db", () => ({
  __esModule: true,
  default: { query: mockQuery },
  initDb: jest.fn(),
  checkDbHealth: jest.fn().mockResolvedValue(true),
}));

import app from "../../app";

beforeEach(() => {
  mockQuery.mockReset();
});

// ---------------------------------------------------------------------------
// POST /api/payments — Create payment
// ---------------------------------------------------------------------------

describe("POST /api/payments", () => {
  it("creates a payment and returns 201", async () => {
    const fakePayment = {
      id: "pay-123",
      order_id: "order-1",
      amount: "49.98",
      currency: "EUR",
      customer_id: "cust-1",
      status: "PROCESSED",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    mockQuery.mockResolvedValueOnce({ rows: [fakePayment] });

    const res = await request(app)
      .post("/api/payments")
      .send({ order_id: "order-1", amount: 49.98, customer_id: "cust-1" });

    expect(res.status).toBe(201);
    expect(res.body.status).toBe("PROCESSED");
    expect(res.body.order_id).toBe("order-1");
  });

  it("returns 400 when required fields are missing", async () => {
    const res = await request(app)
      .post("/api/payments")
      .send({ order_id: "order-1" }); // missing amount and customer_id

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/Missing required fields/);
  });

  it("returns 400 when amount is not positive", async () => {
    const res = await request(app)
      .post("/api/payments")
      .send({ order_id: "order-1", amount: -5, customer_id: "cust-1" });

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/positive/i);
  });
});

// ---------------------------------------------------------------------------
// GET /api/payments/:id — Get payment by ID
// ---------------------------------------------------------------------------

describe("GET /api/payments/:id", () => {
  it("returns a payment", async () => {
    const fakePayment = {
      id: "pay-123",
      order_id: "order-1",
      amount: "49.98",
      currency: "EUR",
      customer_id: "cust-1",
      status: "PROCESSED",
    };
    mockQuery.mockResolvedValueOnce({ rows: [fakePayment] });

    const res = await request(app).get("/api/payments/pay-123");

    expect(res.status).toBe(200);
    expect(res.body.id).toBe("pay-123");
  });

  it("returns 404 when payment not found", async () => {
    mockQuery.mockResolvedValueOnce({ rows: [] });

    const res = await request(app).get("/api/payments/nonexistent");

    expect(res.status).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// POST /api/payments/:id/refund — Refund a payment
// ---------------------------------------------------------------------------

describe("POST /api/payments/:id/refund", () => {
  it("refunds a PROCESSED payment", async () => {
    // First query: fetch existing payment
    mockQuery.mockResolvedValueOnce({
      rows: [{ id: "pay-1", status: "PROCESSED" }],
    });
    // Second query: update and return
    mockQuery.mockResolvedValueOnce({
      rows: [{ id: "pay-1", status: "REFUNDED" }],
    });

    const res = await request(app).post("/api/payments/pay-1/refund");

    expect(res.status).toBe(200);
    expect(res.body.status).toBe("REFUNDED");
  });

  it("returns 409 for non-PROCESSED payment", async () => {
    mockQuery.mockResolvedValueOnce({
      rows: [{ id: "pay-1", status: "REFUNDED" }],
    });

    const res = await request(app).post("/api/payments/pay-1/refund");

    expect(res.status).toBe(409);
    expect(res.body.error).toMatch(/cannot be refunded/i);
  });

  it("returns 404 for nonexistent payment", async () => {
    mockQuery.mockResolvedValueOnce({ rows: [] });

    const res = await request(app).post("/api/payments/nonexistent/refund");

    expect(res.status).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// GET /api/payments — List payments
// ---------------------------------------------------------------------------

describe("GET /api/payments", () => {
  it("lists all payments", async () => {
    const fakePayments = [
      { id: "pay-1", order_id: "o-1", status: "PROCESSED" },
      { id: "pay-2", order_id: "o-2", status: "REFUNDED" },
    ];
    mockQuery.mockResolvedValueOnce({ rows: fakePayments });

    const res = await request(app).get("/api/payments");

    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(2);
  });

  it("filters by order_id", async () => {
    mockQuery.mockResolvedValueOnce({
      rows: [{ id: "pay-1", order_id: "o-1" }],
    });

    const res = await request(app).get("/api/payments?order_id=o-1");

    expect(res.status).toBe(200);
    // Verify the query included the WHERE clause
    const queryStr = mockQuery.mock.calls[0][0] as string;
    expect(queryStr).toContain("order_id = $1");
  });
});

// ---------------------------------------------------------------------------
// GET /api/payments/summary — Payment summary
// ---------------------------------------------------------------------------

describe("GET /api/payments/summary", () => {
  it("returns aggregate stats", async () => {
    mockQuery.mockResolvedValueOnce({
      rows: [
        { status: "PROCESSED", count: 2, amount: "99.96" },
        { status: "REFUNDED", count: 1, amount: "49.98" },
      ],
    });

    const res = await request(app).get(
      "/api/payments/summary?customer_id=cust-1"
    );

    expect(res.status).toBe(200);
    expect(res.body.customer_id).toBe("cust-1");
    expect(res.body.total_payments).toBe(3);
    expect(res.body.by_status.PROCESSED.count).toBe(2);
    expect(res.body.by_status.REFUNDED.count).toBe(1);
  });

  it("returns 400 when customer_id is missing", async () => {
    const res = await request(app).get("/api/payments/summary");

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/customer_id/);
  });
});

// ---------------------------------------------------------------------------
// GET /api/payments/order/:orderId — Payments by order
// ---------------------------------------------------------------------------

describe("GET /api/payments/order/:orderId", () => {
  it("returns payments for a specific order", async () => {
    mockQuery.mockResolvedValueOnce({
      rows: [{ id: "pay-1", order_id: "o-1", status: "PROCESSED" }],
    });

    const res = await request(app).get("/api/payments/order/o-1");

    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(1);
    expect(res.body[0].order_id).toBe("o-1");
  });

  it("returns empty array when no payments for order", async () => {
    mockQuery.mockResolvedValueOnce({ rows: [] });

    const res = await request(app).get("/api/payments/order/no-such-order");

    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(0);
  });
});
