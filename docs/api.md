# HTTP API

The three services speak JSON over HTTP on port 8080.

**Authentication**: none. The services trust their callers; access is controlled at the
network level (gateway, mesh).

**Base URL**: through the Istio ingress gateway, each service under its prefix, which the
gateway strips before forwarding:

| Service | Locally (kind) | Inside the cluster |
|---|---|---|
| order-service | `http://localhost:30080/order-service` | `http://order-service:8080` |
| payment-service | `http://localhost:30080/payment-service` | `http://payment-service:8080` |
| inventory-service | `http://localhost:30080/inventory-service` | `http://inventory-service:8080` |

Paths below are relative to the base URL. Errors are JSON: `{"error": "..."}` (order,
payment) or `{"detail": "..."}` (inventory).

## Common (all services)

| Method | Path | Response |
|---|---|---|
| GET | `/health` | `200 {"status": "ok", "service", "timestamp"}`: liveness, no dependencies |
| GET | `/ready` | `200 {"status": "ready", "checks": {"database": {"status": "up"}}}`, `503` when the database is down |
| GET | `/api/connectivity` | `200 {"service", "connections": {<peer>: {"reachable": bool, ...}}}`: can this service reach its peers |

## order-service

Order: `{id, productId, quantity, customerId, status, paymentId, reservationId, totalAmount,
createdAt, updatedAt}`, `status` one of `PENDING`, `COMPLETED`, `FAILED`, `CANCELLED`.

| Method | Path | Request | Responses |
|---|---|---|---|
| GET | `/api/orders` | query `customerId`, `status` (both optional) | `200 [Order]` |
| POST | `/api/orders` | `{productId, quantity, customerId}` | `201 Order` (`COMPLETED`): stock reserved and payment taken · `422`: the order failed (unknown product, insufficient stock, payment or database error); it is stored as `FAILED` |
| GET | `/api/orders/{id}` | | `200 Order` · `404` |
| GET | `/api/orders/{id}/details` | | `200 {order, payment, product}`; `payment` / `product` are `null` if their service can't be reached · `404` |
| POST | `/api/orders/{id}/cancel` | | `200 Order` (`CANCELLED`): payment refunded, reservation released · `404` · `409`: not `COMPLETED` · `422`: refund or release failed |

## payment-service

Payment: a row of `{id, order_id, customer_id, amount, currency, status, ...}`, `status`
`PROCESSED` or `REFUNDED`, `currency` default `EUR`.

| Method | Path | Request | Responses |
|---|---|---|---|
| GET | `/api/payments` | query `order_id`, `customer_id` (both optional) | `200 [Payment]` |
| POST | `/api/payments` | `{order_id, amount, customer_id, currency?}` | `201 Payment` (`PROCESSED`) · `400`: missing field or `amount <= 0` |
| GET | `/api/payments/summary` | query `customer_id` (required) | `200 {total_payments, total_amount, by_status: {<status>: {count, amount}}}` · `400` |
| GET | `/api/payments/order/{orderId}` | | `200 [Payment]` |
| GET | `/api/payments/{id}` | | `200 Payment` · `404` |
| POST | `/api/payments/{id}/refund` | | `200 Payment` (`REFUNDED`) · `404` · `409`: not refundable in its current status |

Unexpected failures return `500`.

## inventory-service

Product: `{product_id, name, quantity, price}`.

| Method | Path | Request | Responses |
|---|---|---|---|
| GET | `/api/inventory/products` | query `in_stock` (bool, default `false`) | `200 [Product]` |
| POST | `/api/inventory/products` | `{product_id, name, quantity, price}` | `201 Product` · `409`: already exists |
| GET | `/api/inventory/products/{id}` | | `200 Product` · `404` |
| PATCH | `/api/inventory/products/{id}/stock` | `{quantity}`: added to the stock | `200 Product` · `404` |
| POST | `/api/inventory/reserve` | `{product_id, quantity, order_id?}` | `201 {reservation_id, product_id, quantity, status}`: stock decremented · `404`: unknown product · `409`: insufficient stock |
| GET | `/api/inventory/reservations` | query `order_id` (optional) | `200 [{id, product_id, quantity, order_id, created_at}]` |
| DELETE | `/api/inventory/reservations/{id}` | | `200 {reservation_id, product_id, quantity, status}`: stock returned · `404` |

## Example

```bash
G=http://localhost:30080
curl -s $G/inventory-service/api/inventory/products?in_stock=true
curl -s -X POST $G/order-service/api/orders -H 'Content-Type: application/json' \
  -d '{"productId": "WIDGET-002", "quantity": 1, "customerId": "c-1"}'
curl -s -X POST $G/order-service/api/orders/<id>/cancel
```
