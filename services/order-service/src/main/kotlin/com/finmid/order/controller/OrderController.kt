package com.finmid.order.controller

import com.finmid.order.client.InventoryClient
import com.finmid.order.client.PaymentClient
import com.finmid.order.model.CreateOrderRequest
import com.finmid.order.model.Order
import com.finmid.order.service.OrderNotFoundException
import com.finmid.order.service.OrderNotCancellableException
import com.finmid.order.service.OrderService
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.web.bind.annotation.*
import java.time.Instant

@RestController
class OrderController(
    private val orderService: OrderService,
    private val inventoryClient: InventoryClient,
    private val paymentClient: PaymentClient,
    private val jdbcTemplate: JdbcTemplate
) {

    @GetMapping("/health")
    fun health(): ResponseEntity<Map<String, Any>> {
        return ResponseEntity.ok(mapOf(
            "status" to "ok",
            "service" to "order-service",
            "timestamp" to Instant.now().toString()
        ))
    }

    @GetMapping("/ready")
    fun ready(): ResponseEntity<Map<String, Any>> {
        val checks = mutableMapOf<String, Any>()

        // Check database
        val dbUp = try {
            jdbcTemplate.queryForObject("SELECT 1", Int::class.java)
            true
        } catch (e: Exception) {
            false
        }
        checks["database"] = mapOf("status" to if (dbUp) "up" else "down")

        if (!dbUp) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(mapOf("status" to "not_ready", "checks" to checks))
        }

        return ResponseEntity.ok(mapOf("status" to "ready", "checks" to checks))
    }

    @GetMapping("/api/connectivity")
    fun connectivity(): ResponseEntity<Map<String, Any>> {
        val inventoryReachable = inventoryClient.checkHealth()
        val paymentReachable = paymentClient.checkHealth()

        return ResponseEntity.ok(mapOf(
            "service" to "order-service",
            "connections" to mapOf(
                "inventory-service" to mapOf("reachable" to inventoryReachable),
                "payment-service" to mapOf("reachable" to paymentReachable)
            )
        ))
    }

    @GetMapping("/api/orders")
    fun listOrders(
        @RequestParam(required = false) customerId: String?,
        @RequestParam(required = false) status: String?
    ): ResponseEntity<Any> {
        val orders = orderService.listOrders(customerId, status)
        return ResponseEntity.ok(orders)
    }

    @PostMapping("/api/orders")
    fun createOrder(@RequestBody request: CreateOrderRequest): ResponseEntity<Any> {
        return try {
            val order = orderService.createOrder(request)
            ResponseEntity.status(HttpStatus.CREATED).body(order)
        } catch (e: Exception) {
            ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY).body(mapOf(
                "error" to (e.message ?: "Failed to create order")
            ))
        }
    }

    @GetMapping("/api/orders/{orderId}")
    fun getOrder(@PathVariable orderId: String): ResponseEntity<Any> {
        val order = orderService.getOrder(orderId)
        return if (order != null) {
            ResponseEntity.ok(order)
        } else {
            ResponseEntity.status(HttpStatus.NOT_FOUND).body(mapOf("error" to "Order not found"))
        }
    }

    @PostMapping("/api/orders/{orderId}/cancel")
    fun cancelOrder(@PathVariable orderId: String): ResponseEntity<Any> {
        return try {
            val order = orderService.cancelOrder(orderId)
            ResponseEntity.ok(order)
        } catch (e: OrderNotFoundException) {
            ResponseEntity.status(HttpStatus.NOT_FOUND).body(mapOf("error" to e.message))
        } catch (e: OrderNotCancellableException) {
            ResponseEntity.status(HttpStatus.CONFLICT).body(mapOf("error" to e.message))
        } catch (e: Exception) {
            ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY).body(mapOf(
                "error" to (e.message ?: "Failed to cancel order")
            ))
        }
    }

    @GetMapping("/api/orders/{orderId}/details")
    fun getOrderDetails(@PathVariable orderId: String): ResponseEntity<Any> {
        val order = orderService.getOrder(orderId)
            ?: return ResponseEntity.status(HttpStatus.NOT_FOUND).body(mapOf("error" to "Order not found"))

        val payment = try {
            if (order.paymentId != null) paymentClient.getPayment(order.paymentId) else null
        } catch (e: Exception) {
            null
        }

        val product = try {
            inventoryClient.getProduct(order.productId)
        } catch (e: Exception) {
            null
        }

        return ResponseEntity.ok(mapOf(
            "order" to order,
            "payment" to payment,
            "product" to product
        ))
    }
}
