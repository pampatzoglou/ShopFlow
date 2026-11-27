package com.finmid.order.service

import com.finmid.order.client.InventoryClient
import com.finmid.order.client.PaymentClient
import com.finmid.order.model.CreateOrderRequest
import com.finmid.order.model.Order
import io.micrometer.core.instrument.Counter
import io.micrometer.core.instrument.MeterRegistry
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.sql.ResultSet
import java.time.Instant
import java.util.UUID

@Service
class OrderService(
    private val jdbcTemplate: JdbcTemplate,
    private val inventoryClient: InventoryClient,
    private val paymentClient: PaymentClient,
    private val meterRegistry: MeterRegistry
) {

    // shopflow_orders_total{outcome, step}: step is where a failed order broke
    // (inventory | payment | database), "none" for completed orders.
    private fun countOrder(outcome: String, step: String) =
        Counter.builder("shopflow.orders")
            .description("Orders processed, by outcome and failing step")
            .tag("outcome", outcome)
            .tag("step", step)
            .register(meterRegistry)
            .increment()

    // shopflow_order_cancellations_total{outcome}
    private fun countCancellation(outcome: String) =
        Counter.builder("shopflow.order.cancellations")
            .description("Order cancellations attempted on cancellable orders, by outcome")
            .tag("outcome", outcome)
            .register(meterRegistry)
            .increment()

    init {
        jdbcTemplate.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                customer_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                payment_id TEXT,
                reservation_id TEXT,
                total_amount NUMERIC(10, 2),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
    }

    fun createOrder(request: CreateOrderRequest): Order {
        val orderId = UUID.randomUUID().toString()

        // Insert pending order
        jdbcTemplate.update(
            "INSERT INTO orders (id, product_id, quantity, customer_id, status) VALUES (?, ?, ?, ?, 'PENDING')",
            orderId, request.productId, request.quantity, request.customerId
        )

        var step = "inventory"
        try {
            // Step 1: Get product price and reserve inventory
            val product = inventoryClient.getProduct(request.productId)
            val reservation = inventoryClient.reserveInventory(request.productId, request.quantity, orderId)

            val totalAmount = BigDecimal.valueOf(product.price).multiply(BigDecimal.valueOf(request.quantity.toLong()))

            // Step 2: Process payment
            step = "payment"
            val payment = paymentClient.processPayment(orderId, totalAmount, request.customerId)

            // Step 3: Update order as completed
            step = "database"
            jdbcTemplate.update(
                """UPDATE orders SET status = 'COMPLETED', payment_id = ?, reservation_id = ?,
                   total_amount = ?, updated_at = NOW() WHERE id = ?""",
                payment.id, reservation.reservation_id, totalAmount, orderId
            )

            countOrder("completed", "none")
            return getOrder(orderId)!!
        } catch (e: Exception) {
            countOrder("failed", step)
            // Mark order as failed
            jdbcTemplate.update(
                "UPDATE orders SET status = 'FAILED', updated_at = NOW() WHERE id = ?",
                orderId
            )
            throw e
        }
    }

    fun getOrder(orderId: String): Order? {
        val orders = jdbcTemplate.query(
            "SELECT * FROM orders WHERE id = ?",
            { rs: ResultSet, _: Int -> mapOrder(rs) },
            orderId
        )
        return orders.firstOrNull()
    }

    fun listOrders(customerId: String?, status: String?): List<Order> {
        val conditions = mutableListOf<String>()
        val params = mutableListOf<Any>()

        if (customerId != null) {
            conditions.add("customer_id = ?")
            params.add(customerId)
        }
        if (status != null) {
            conditions.add("status = ?")
            params.add(status)
        }

        val whereClause = if (conditions.isNotEmpty()) " WHERE " + conditions.joinToString(" AND ") else ""
        val sql = "SELECT * FROM orders$whereClause ORDER BY created_at DESC"

        return jdbcTemplate.query(sql, { rs: ResultSet, _: Int -> mapOrder(rs) }, *params.toTypedArray())
    }

    fun cancelOrder(orderId: String): Order {
        val order = getOrder(orderId)
            ?: throw OrderNotFoundException("Order $orderId not found")

        if (order.status != "COMPLETED") {
            throw OrderNotCancellableException("Order $orderId cannot be cancelled: current status is ${order.status}")
        }

        try {
            // Step 1: Refund payment
            if (order.paymentId != null) {
                paymentClient.refundPayment(order.paymentId)
            }

            // Step 2: Release inventory reservation
            if (order.reservationId != null) {
                inventoryClient.releaseReservation(order.reservationId)
            }

            // Step 3: Update order status
            jdbcTemplate.update(
                "UPDATE orders SET status = 'CANCELLED', updated_at = NOW() WHERE id = ?",
                orderId
            )

            countCancellation("cancelled")
            return getOrder(orderId)!!
        } catch (e: OrderNotFoundException) {
            throw e
        } catch (e: OrderNotCancellableException) {
            throw e
        } catch (e: Exception) {
            countCancellation("failed")
            throw RuntimeException("Failed to cancel order $orderId: ${e.message}", e)
        }
    }

    private fun mapOrder(rs: ResultSet): Order {
        return Order(
            id = rs.getString("id"),
            productId = rs.getString("product_id"),
            quantity = rs.getInt("quantity"),
            customerId = rs.getString("customer_id"),
            status = rs.getString("status"),
            paymentId = rs.getString("payment_id"),
            reservationId = rs.getString("reservation_id"),
            totalAmount = rs.getBigDecimal("total_amount"),
            createdAt = rs.getTimestamp("created_at")?.toInstant(),
            updatedAt = rs.getTimestamp("updated_at")?.toInstant()
        )
    }
}

class OrderNotFoundException(message: String) : RuntimeException(message)
class OrderNotCancellableException(message: String) : RuntimeException(message)
