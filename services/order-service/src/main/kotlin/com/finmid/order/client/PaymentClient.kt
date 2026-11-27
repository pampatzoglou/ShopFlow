package com.finmid.order.client

import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import org.springframework.web.client.RestTemplate
import org.springframework.http.HttpEntity
import org.springframework.http.HttpHeaders
import org.springframework.http.MediaType
import java.math.BigDecimal

@Component
class PaymentClient(
    @Value("\${payment.service.url}") private val baseUrl: String
) {
    private val restTemplate = RestTemplate()

    data class CreatePaymentRequest(
        val order_id: String,
        val amount: BigDecimal,
        val currency: String = "EUR",
        val customer_id: String
    )

    data class PaymentResponse(
        val id: String,
        val order_id: String,
        val amount: BigDecimal,
        val currency: String,
        val customer_id: String,
        val status: String
    )

    fun processPayment(orderId: String, amount: BigDecimal, customerId: String): PaymentResponse {
        val headers = HttpHeaders().apply { contentType = MediaType.APPLICATION_JSON }
        val request = HttpEntity(
            CreatePaymentRequest(orderId, amount, "EUR", customerId),
            headers
        )
        return restTemplate.postForObject(
            "$baseUrl/api/payments",
            request,
            PaymentResponse::class.java
        )!!
    }

    fun getPayment(paymentId: String): PaymentResponse {
        return restTemplate.getForObject(
            "$baseUrl/api/payments/$paymentId",
            PaymentResponse::class.java
        )!!
    }

    fun refundPayment(paymentId: String): PaymentResponse {
        return restTemplate.postForObject(
            "$baseUrl/api/payments/$paymentId/refund",
            null,
            PaymentResponse::class.java
        )!!
    }

    fun checkHealth(): Boolean {
        return try {
            val response = restTemplate.getForEntity("$baseUrl/health", String::class.java)
            response.statusCode.is2xxSuccessful
        } catch (e: Exception) {
            false
        }
    }
}
