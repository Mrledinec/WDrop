package local.transfer.airdrop_app

import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.URL
import java.net.Proxy
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

internal const val API = "/api/v1"
internal const val BUFFER_SIZE = 256 * 1024
internal const val DEFAULT_LIMIT_MIB = 2048
internal const val SERVICE_TYPE = "_localtransfer._tcp."
internal fun ByteArray.hex() = joinToString("") { "%02x".format(it) }

internal data class Peer(
    val pin: String,
    val name: String,
    val host: String,
    val port: Int,
    val token: String,
    val trusted: Boolean = false,
    val alias: String = "",
) {
    val displayName get() = alias.ifBlank { name }

    fun json() = JSONObject()
        .put("pin", pin).put("name", name).put("host", host).put("port", port)
        .put("token", token).put("trusted", trusted).put("alias", alias)

    fun display() = mapOf("id" to pin, "name" to displayName, "host" to host, "trusted" to trusted)

    companion object {
        fun fromJson(value: JSONObject) = Peer(
            value.getString("pin"), value.getString("name"), value.getString("host"),
            value.getInt("port"), value.getString("token"), value.optBoolean("trusted"), value.optString("alias"),
        )
    }
}

internal data class Offer(
    val id: String,
    val name: String,
    val size: Long,
    val digest: String,
    val state: String,
    val secondsLeft: Int,
) {
    companion object {
        fun fromJson(value: JSONObject): Offer {
            val id = value.getString("id")
            val size = value.getLong("size")
            val digest = value.getString("sha256")
            require(id.matches(Regex("[0-9a-f]{32}")) && size >= 0 && digest.matches(Regex("[0-9a-f]{64}"))) {
                "Устройство сообщило некорректные параметры передачи"
            }
            return Offer(
                id, value.getString("name"), size, digest, value.getString("state"),
                value.optInt("seconds_left").coerceIn(0, 60),
            )
        }
    }
}

internal class ApiException(val status: Int, message: String) : IOException(message)

internal class PeerApi(private val peer: Peer, private val network: LocalNetwork) {
    private val tls = SSLContext.getInstance("TLS").apply {
        init(null, arrayOf(object : X509TrustManager {
            override fun getAcceptedIssuers() = emptyArray<X509Certificate>()
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {
                throw CertificateException("Client certificates are unsupported")
            }

            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                val certificate = chain.firstOrNull() ?: throw CertificateException("Сертификат ПК отсутствует")
                certificate.checkValidity()
                val actual = MessageDigest.getInstance("SHA-256").digest(certificate.encoded).hex()
                if (actual != peer.pin) throw CertificateException("Сертификат ПК не совпал с QR")
            }
        }), null)
    }

    fun <T> request(
        path: String,
        method: String = "GET",
        timeout: Int = 8_000,
        action: (HttpsURLConnection) -> T,
    ): T {
        val url = URL("https", peer.host, peer.port, API + path)
        val connection = (network.current()?.openConnection(url, Proxy.NO_PROXY)
            ?: url.openConnection(Proxy.NO_PROXY)) as HttpsURLConnection
        connection.sslSocketFactory = tls.socketFactory
        // The exact certificate from the QR replaces DNS-based hostname authentication.
        connection.hostnameVerifier = javax.net.ssl.HostnameVerifier { _, _ -> true }
        connection.instanceFollowRedirects = false
        connection.connectTimeout = 2_000
        connection.readTimeout = timeout
        connection.requestMethod = method
        if (peer.token.isNotEmpty()) connection.setRequestProperty("Authorization", "Bearer " + peer.token)
        try {
            return action(connection)
        } finally {
            connection.disconnect()
        }
    }

    fun check(connection: HttpsURLConnection) {
        val code = connection.responseCode
        if (code in 200..299) return
        val body = connection.errorStream?.use { input ->
            val buffer = ByteArray(4096)
            String(buffer, 0, input.read(buffer).coerceAtLeast(0), Charsets.UTF_8)
        }
        val detail = body?.let { runCatching { JSONObject(it).optString("detail") }.getOrNull() }
        throw ApiException(code, detail?.takeIf { it.isNotBlank() } ?: "Ошибка подключения ($code)")
    }

    fun objectRequest(path: String, payload: JSONObject? = null, timeout: Int = 8_000): JSONObject =
        request(path, if (payload == null) "GET" else "POST", timeout) { connection ->
            if (payload != null) {
                val data = payload.toString().toByteArray(Charsets.UTF_8)
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.setFixedLengthStreamingMode(data.size)
                connection.outputStream.use { it.write(data) }
            }
            check(connection)
            connection.inputStream.bufferedReader().use { JSONObject(it.readText()) }
        }

    fun offers() = request("/offers", timeout = 3_000) { connection ->
        check(connection)
        val values = connection.inputStream.bufferedReader().use { JSONArray(it.readText()) }
        List(values.length()) { Offer.fromJson(values.getJSONObject(it)) }
    }

    fun decide(id: String, accept: Boolean) =
        Offer.fromJson(objectRequest("/offers/$id/decision", JSONObject().put("accept", accept)))

    fun receipt(id: String, success: Boolean) =
        objectRequest("/offers/$id/complete", JSONObject().put("success", success))
}

