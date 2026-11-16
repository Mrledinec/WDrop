package local.transfer.airdrop_app

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import java.io.IOException
import java.net.Inet4Address

internal class LocalNetwork(context: Context) {
    private val connectivity = context.getSystemService(ConnectivityManager::class.java)
    private val preferences = context.getSharedPreferences("network", Context.MODE_PRIVATE)

    val selected: String get() = preferences.getString("interface", "").orEmpty()

    private data class Choice(val id: String, val label: String, val network: Network)

    @Suppress("DEPRECATION")
    private fun choices() = connectivity.allNetworks.mapNotNull { network ->
        val details = connectivity.getLinkProperties(network) ?: return@mapNotNull null
        val id = details.interfaceName ?: return@mapNotNull null
        val capabilities = connectivity.getNetworkCapabilities(network) ?: return@mapNotNull null
        val type = when {
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN) -> "VPN"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "Wi-Fi"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "Ethernet"
            else -> return@mapNotNull null
        }
        val address = details.linkAddresses.firstOrNull { it.address is Inet4Address }?.address?.hostAddress
        Choice(id, listOfNotNull(type, id, address).joinToString(" · "), network)
    }.distinctBy { it.id }

    fun options(): List<Map<String, String>> {
        val current = choices()
        val options = listOf(mapOf("id" to "", "name" to "Автоматически")) +
            current.map { mapOf("id" to it.id, "name" to it.label) }
        val id = selected
        return if (id.isNotEmpty() && current.none { it.id == id }) {
            options + mapOf("id" to id, "name" to "$id · недоступна")
        } else options
    }

    fun select(id: String) {
        require(id.isEmpty() || choices().any { it.id == id }) { "Сеть больше недоступна" }
        preferences.edit().putString("interface", id).apply()
    }

    fun current(): Network? {
        val id = selected
        return if (id.isEmpty()) null else choices().firstOrNull { it.id == id }?.network
            ?: throw IOException("Выбранная локальная сеть недоступна")
    }
}
