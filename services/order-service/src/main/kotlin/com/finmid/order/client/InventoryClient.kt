package com.finmid.order.client

import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import org.springframework.web.client.RestTemplate
import org.springframework.http.HttpEntity
import org.springframework.http.HttpHeaders
import org.springframework.http.MediaType

@Component
class InventoryClient(
    @Value("\${inventory.service.url}") private val baseUrl: String
) {
    private val restTemplate = RestTemplate()

    data class ReserveRequest(
        val product_id: String,
        val quantity: Int,
        val order_id: String? = null
    )

    data class ReserveResponse(
        val reservation_id: String,
        val product_id: String,
        val quantity: Int,
        val status: String
    )

    data class ProductResponse(
        val product_id: String,
        val name: String,
        val quantity: Int,
        val price: Double
    )

    fun reserveInventory(productId: String, quantity: Int, orderId: String? = null): ReserveResponse {
        val headers = HttpHeaders().apply { contentType = MediaType.APPLICATION_JSON }
        val request = HttpEntity(ReserveRequest(productId, quantity, orderId), headers)
        return restTemplate.postForObject(
            "$baseUrl/api/inventory/reserve",
            request,
            ReserveResponse::class.java
        )!!
    }

    fun getProduct(productId: String): ProductResponse {
        return restTemplate.getForObject(
            "$baseUrl/api/inventory/products/$productId",
            ProductResponse::class.java
        )!!
    }

    fun releaseReservation(reservationId: String) {
        restTemplate.delete("$baseUrl/api/inventory/reservations/$reservationId")
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
