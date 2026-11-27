// Load test for the ShopFlow checkout flow, through the Istio ingress gateway.
//
//   task test:k6s                       # K6_PROFILE=load (default), ~2 min, 10 VUs
//   task test:k6s K6_PROFILE=smoke      # 1 VU for 30s: "does it work under any load"
//
// Every iteration is a full customer journey: browse products → place an order → read the
// order and its payment → cancel it (refund + stock release). Cancelling keeps stock net
// neutral, so repeated runs don't sell out the catalogue the E2E suite relies on. WIDGET-001,
// which the E2E suite asserts on, is never ordered here.
//
// Thresholds make k6 exit non-zero, which is what fails `task test:k6s` (and CI).
import http from "k6/http";
import { check, fail, group, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";

const BASE = (__ENV.GATEWAY_URL || "http://localhost:30080").replace(/\/$/, "");
const ORDERS = `${BASE}/order-service/api/orders`;
const PRODUCTS = `${BASE}/inventory-service/api/inventory/products`;
const PAYMENTS = `${BASE}/payment-service/api/payments`;
const JSON_HEADERS = { headers: { "Content-Type": "application/json" } };

// Products reserved for the E2E suite or created by it.
const EXCLUDED = /^(WIDGET-001|TEST-)/;
// Only order products with comfortable headroom: VUs order concurrently before cancelling.
const MIN_STOCK = 20;

const PROFILES = {
  smoke: { executor: "constant-vus", vus: 1, duration: "30s" },
  load: {
    executor: "ramping-vus",
    startVUs: 0,
    stages: [
      { duration: "30s", target: 10 },
      { duration: "1m", target: 10 },
      { duration: "15s", target: 0 },
    ],
    gracefulRampDown: "10s",
  },
};
const PROFILE = __ENV.K6_PROFILE || "load";
if (!PROFILES[PROFILE]) {
  throw new Error(`unknown K6_PROFILE '${PROFILE}' (one of: ${Object.keys(PROFILES).join(", ")})`);
}

export const options = {
  scenarios: { checkout: PROFILES[PROFILE] },
  thresholds: {
    // Every request in the journey is expected to succeed.
    http_req_failed: ["rate<0.01"],
    checks: ["rate>0.99"],
    // Checkout = order-service calling inventory (reserve) and payment (charge).
    "http_req_duration{name:create_order}": ["p(95)<1000"],
    "http_req_duration{name:cancel_order}": ["p(95)<1000"],
    "http_req_duration{name:list_products}": ["p(95)<300"],
    "http_req_duration{name:get_order}": ["p(95)<300"],
    "http_req_duration{name:get_payment}": ["p(95)<300"],
    orders_completed: ["count>0"],
  },
};

const checkoutDuration = new Trend("checkout_duration", true);
const ordersCompleted = new Counter("orders_completed");
const ordersCancelled = new Counter("orders_cancelled");

export function setup() {
  for (const svc of ["order-service", "payment-service", "inventory-service"]) {
    const res = http.get(`${BASE}/${svc}/health`, { tags: { name: "health" } });
    if (res.status !== 200) {
      fail(`${svc} is not healthy through the gateway at ${BASE} (HTTP ${res.status})`);
    }
  }
  const res = http.get(PRODUCTS, { tags: { name: "list_products" } });
  if (res.status !== 200) fail(`cannot list products (HTTP ${res.status})`);
  const products = res
    .json()
    .filter((p) => !EXCLUDED.test(p.product_id) && p.quantity >= MIN_STOCK)
    .map((p) => p.product_id);
  if (products.length === 0) {
    fail(`no product outside ${EXCLUDED} has at least ${MIN_STOCK} units in stock`);
  }
  return { products };
}

export default function ({ products }) {
  const productId = products[Math.floor(Math.random() * products.length)];
  const customerId = `k6-${__VU}-${__ITER}`;
  let order;

  group("browse", () => {
    const res = http.get(PRODUCTS, { tags: { name: "list_products" } });
    check(res, { "products listed": (r) => r.status === 200 });
  });

  group("checkout", () => {
    const res = http.post(
      ORDERS,
      JSON.stringify({ productId, quantity: 1, customerId }),
      Object.assign({ tags: { name: "create_order" } }, JSON_HEADERS),
    );
    checkoutDuration.add(res.timings.duration);
    const ok = check(res, {
      "order created (201)": (r) => r.status === 201,
      "order completed": (r) => r.status === 201 && r.json("status") === "COMPLETED",
    });
    if (ok) {
      order = res.json();
      ordersCompleted.add(1);
    }
  });
  if (!order) return;

  group("track", () => {
    const res = http.get(`${ORDERS}/${order.id}`, { tags: { name: "get_order" } });
    check(res, { "order readable": (r) => r.status === 200 && r.json("id") === order.id });
    const pay = http.get(`${PAYMENTS}/${order.paymentId}`, { tags: { name: "get_payment" } });
    check(pay, { "payment processed": (r) => r.status === 200 && r.json("status") === "PROCESSED" });
  });

  sleep(Math.random() * 0.5);

  group("cancel", () => {
    const res = http.post(`${ORDERS}/${order.id}/cancel`, null, { tags: { name: "cancel_order" } });
    const ok = check(res, {
      "order cancelled": (r) => r.status === 200 && r.json("status") === "CANCELLED",
    });
    if (ok) ordersCancelled.add(1);
  });

  sleep(Math.random());
}
