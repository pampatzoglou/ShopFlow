package com.finmid.order.model

import java.math.BigDecimal
import java.time.Instant

data class Order(
    val id: String,
    val productId: String,
    val quantity: Int,
    val customerId: String,
    val status: String,
    val paymentId: String? = null,
    val reservationId: String? = null,
    val totalAmount: BigDecimal? = null,
    val createdAt: Instant? = null,
    val updatedAt: Instant? = null
)

data class CreateOrderRequest(
    val productId: String,
    val quantity: Int,
    val customerId: String
)
