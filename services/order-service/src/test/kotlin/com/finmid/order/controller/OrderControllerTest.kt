package com.finmid.order.controller

import com.fasterxml.jackson.databind.ObjectMapper
import com.finmid.order.client.InventoryClient
import com.finmid.order.client.PaymentClient
import com.finmid.order.model.CreateOrderRequest
import com.finmid.order.model.Order
import com.finmid.order.service.OrderNotFoundException
import com.finmid.order.service.OrderNotCancellableException
import com.finmid.order.service.OrderService
import io.mockk.every
import io.mockk.mockk
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.boot.test.context.TestConfiguration
import org.springframework.context.annotation.Bean
import org.springframework.http.MediaType
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.*
import java.math.BigDecimal
import java.time.Instant

@WebMvcTest(OrderController::class)
class OrderControllerTest {

    @Autowired
    private lateinit var mockMvc: MockMvc

    @Autowired
    private lateinit var orderService: OrderService

    @Autowired
    private lateinit var inventoryClient: InventoryClient

    @Autowired
    private lateinit var paymentClient: PaymentClient

    @Autowired
    private lateinit var objectMapper: ObjectMapper

    @TestConfiguration
    class Config {
        @Bean fun orderService(): OrderService = mockk(relaxed = true)
        @Bean fun inventoryClient(): InventoryClient = mockk(relaxed = true)
        @Bean fun paymentClient(): PaymentClient = mockk(relaxed = true)
    }

    private fun sampleOrder(
        id: String = "order-1",
        status: String = "COMPLETED",
        paymentId: String? = "pay-1",
        reservationId: String? = "res-1"
    ) = Order(
        id = id,
        productId = "WIDGET-001",
        quantity = 2,
        customerId = "cust-1",
        status = status,
        paymentId = paymentId,
        reservationId = reservationId,
        totalAmount = BigDecimal("49.98"),
        createdAt = Instant.now(),
        updatedAt = Instant.now()
    )

    // -----------------------------------------------------------------------
    // GET /api/orders
    // -----------------------------------------------------------------------

    @Test
    fun `list orders returns 200 with list`() {
        every { orderService.listOrders(null, null) } returns listOf(sampleOrder())

        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isOk)
            .andExpect(jsonPath("$[0].id").value("order-1"))
    }

    @Test
    fun `list orders with customer filter`() {
        every { orderService.listOrders("cust-1", null) } returns listOf(sampleOrder())

        mockMvc.perform(get("/api/orders").param("customerId", "cust-1"))
            .andExpect(status().isOk)
            .andExpect(jsonPath("$[0].customerId").value("cust-1"))
    }

    // -----------------------------------------------------------------------
    // GET /api/orders/{orderId}
    // -----------------------------------------------------------------------

    @Test
    fun `get order returns 404 for unknown id`() {
        every { orderService.getOrder("unknown") } returns null

        mockMvc.perform(get("/api/orders/unknown"))
            .andExpect(status().isNotFound)
    }

    // -----------------------------------------------------------------------
    // POST /api/orders/{orderId}/cancel
    // -----------------------------------------------------------------------

    @Test
    fun `cancel order returns 200`() {
        val cancelled = sampleOrder(status = "CANCELLED")
        every { orderService.cancelOrder("order-1") } returns cancelled

        mockMvc.perform(post("/api/orders/order-1/cancel"))
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.status").value("CANCELLED"))
    }

    @Test
    fun `cancel order returns 404 for unknown id`() {
        every { orderService.cancelOrder("unknown") } throws
                OrderNotFoundException("Order unknown not found")

        mockMvc.perform(post("/api/orders/unknown/cancel"))
            .andExpect(status().isNotFound)
    }

    @Test
    fun `cancel order returns 409 for non-completed`() {
        every { orderService.cancelOrder("order-1") } throws
                OrderNotCancellableException("Order order-1 cannot be cancelled: current status is PENDING")

        mockMvc.perform(post("/api/orders/order-1/cancel"))
            .andExpect(status().isConflict)
    }

    // -----------------------------------------------------------------------
    // GET /api/orders/{orderId}/details
    // -----------------------------------------------------------------------

    @Test
    fun `get order details returns enriched response`() {
        val order = sampleOrder()
        every { orderService.getOrder("order-1") } returns order
        every { paymentClient.getPayment("pay-1") } returns PaymentClient.PaymentResponse(
            id = "pay-1", order_id = "order-1", amount = BigDecimal("49.98"),
            currency = "EUR", customer_id = "cust-1", status = "PROCESSED"
        )
        every { inventoryClient.getProduct("WIDGET-001") } returns InventoryClient.ProductResponse(
            product_id = "WIDGET-001", name = "Standard Widget", quantity = 98, price = 24.99
        )

        mockMvc.perform(get("/api/orders/order-1/details"))
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.order.id").value("order-1"))
            .andExpect(jsonPath("$.payment.status").value("PROCESSED"))
            .andExpect(jsonPath("$.product.product_id").value("WIDGET-001"))
    }

    // -----------------------------------------------------------------------
    // POST /api/orders — create order failure
    // -----------------------------------------------------------------------

    @Test
    fun `create order returns 422 on failure`() {
        every { orderService.createOrder(any()) } throws RuntimeException("Insufficient stock")

        mockMvc.perform(
            post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(
                    CreateOrderRequest("WIDGET-001", 999, "cust-1")
                ))
        )
            .andExpect(status().isUnprocessableEntity)
    }
}
