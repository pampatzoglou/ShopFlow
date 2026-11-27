package com.finmid.order.service

import com.finmid.order.client.InventoryClient
import com.finmid.order.client.PaymentClient
import com.finmid.order.model.Order
import io.micrometer.core.instrument.simple.SimpleMeterRegistry
import io.mockk.*
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.jdbc.core.RowMapper
import java.math.BigDecimal
import java.time.Instant

class OrderServiceTest {

    private val jdbcTemplate: JdbcTemplate = mockk(relaxed = true)
    private val inventoryClient: InventoryClient = mockk(relaxed = true)
    private val paymentClient: PaymentClient = mockk(relaxed = true)

    private lateinit var orderService: OrderService

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

    @BeforeEach
    fun setUp() {
        clearAllMocks()
        // Skip the init block's CREATE TABLE by mocking execute
        every { jdbcTemplate.execute(any<String>()) } just Runs
        orderService = OrderService(jdbcTemplate, inventoryClient, paymentClient, SimpleMeterRegistry())
    }

    @Test
    fun `cancelOrder calls refund then release then updates status`() {
        val order = sampleOrder()
        val cancelledOrder = sampleOrder(status = "CANCELLED")

        // getOrder called twice: once to check status, once to return final result
        every { jdbcTemplate.query(any<String>(), any<RowMapper<Order>>(), eq("order-1")) } returnsMany listOf(
            listOf(order),        // first call: check status
            listOf(cancelledOrder) // second call: return updated
        )
        every { paymentClient.refundPayment("pay-1") } returns PaymentClient.PaymentResponse(
            id = "pay-1", order_id = "order-1", amount = BigDecimal("49.98"),
            currency = "EUR", customer_id = "cust-1", status = "REFUNDED"
        )
        every { inventoryClient.releaseReservation("res-1") } just Runs
        every { jdbcTemplate.update(any<String>(), eq("order-1")) } returns 1

        val result = orderService.cancelOrder("order-1")

        assertEquals("CANCELLED", result.status)
        verify { paymentClient.refundPayment("pay-1") }
        verify { inventoryClient.releaseReservation("res-1") }
    }

    @Test
    fun `cancelOrder throws when order not found`() {
        every { jdbcTemplate.query(any<String>(), any<RowMapper<Order>>(), eq("nonexistent")) } returns emptyList()

        assertThrows(OrderNotFoundException::class.java) {
            orderService.cancelOrder("nonexistent")
        }
    }

    @Test
    fun `cancelOrder throws when order not COMPLETED`() {
        val pendingOrder = sampleOrder(status = "PENDING")
        every { jdbcTemplate.query(any<String>(), any<RowMapper<Order>>(), eq("order-1")) } returns listOf(pendingOrder)

        assertThrows(OrderNotCancellableException::class.java) {
            orderService.cancelOrder("order-1")
        }
    }
}
