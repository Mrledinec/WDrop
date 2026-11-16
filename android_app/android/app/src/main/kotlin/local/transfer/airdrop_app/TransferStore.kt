package local.transfer.airdrop_app

import android.content.Context
import android.os.Build
import org.json.JSONArray
import org.json.JSONObject

internal class TransferStore(context: Context) {
    private val prefs = context.getSharedPreferences("transfer", Context.MODE_PRIVATE)
    val network = LocalNetwork(context)

    var ready: Boolean
        get() = prefs.getBoolean("ready", false)
        set(value) { prefs.edit().putBoolean("ready", value).apply() }

    var limitMiB: Int
        get() = prefs.getInt("limit_mib", DEFAULT_LIMIT_MIB)
        set(value) { prefs.edit().putInt("limit_mib", value).apply() }

    @Synchronized
    fun peers(): List<Peer> {
        val items = JSONArray(prefs.getString("peers", "[]"))
        return List(items.length()) { Peer.fromJson(items.getJSONObject(it)) }
    }

    @Synchronized
    fun put(peer: Peer) {
        persistPeers(peers().filter { it.pin != peer.pin } + peer)
    }

    @Synchronized
    fun update(pin: String, change: (Peer) -> Peer) {
        persistPeers(peers().map { if (it.pin == pin) change(it) else it })
    }

    @Synchronized
    fun remove(pin: String) {
        persistPeers(peers().filter { it.pin != pin })
    }

    private fun persistPeers(peers: List<Peer>) {
        prefs.edit().putString("peers", JSONArray(peers.map { it.json() }).toString()).apply()
    }

    fun accepts(size: Long) = limitMiB.let { it == 0 || size <= it.toLong() * 1024 * 1024 }

    fun pair(code: String): Peer {
        val invite = JSONObject(code)
        require(invite.getInt("v") == 1) { "Версия приглашения не поддерживается" }
        val host = invite.getString("host")
        val pin = invite.getString("pin")
        val port = invite.getInt("port")
        require(ipv4(host) && port in 1..65535 && pin.matches(Regex("[0-9a-f]{64}"))) {
            "Некорректное приглашение"
        }
        return pairAt(Peer(pin, invite.getString("name"), host, port, ""), invite.getString("token"))
    }

    fun pairDiscovered(device: LanDevice, code: String): Peer {
        val token = code.filterNot { it.isWhitespace() || it == '-' }.lowercase()
        require(token.matches(Regex("[0-9a-f]{16}[0-9]{8}")) && token.startsWith(device.pin.take(16))) {
            "Код не соответствует найденному ПК. Проверьте код в окне сопряжения на ПК."
        }
        return pairAt(Peer(device.pin, device.name, device.host, device.port, ""), token)
    }

    private fun pairAt(temporary: Peer, token: String): Peer {
        val name = (Build.MANUFACTURER + " " + Build.MODEL).take(80)
        val response = PeerApi(temporary, network).objectRequest(
            "/pair", JSONObject().put("token", token).put("name", name), 65_000,
        )
        val existing = peers().find { it.pin == temporary.pin }
        val peer = temporary.copy(
            name = response.getString("name"), token = response.getString("token"), alias = existing?.alias.orEmpty(),
            trusted = existing?.trusted ?: false,
        )
        put(peer)
        return peer
    }

    fun reconnect(device: LanDevice) {
        val known = peers().find { it.pin == device.pin } ?: return
        if (known.host == device.host && known.port == device.port) return
        val candidate = known.copy(host = device.host, port = device.port)
        PeerApi(candidate, network).offers()
        update(known.pin) {
            if (it.token == known.token) it.copy(host = candidate.host, port = candidate.port) else it
        }
    }

    @Synchronized
    fun record(id: String, name: String, direction: String, size: Long, uri: String = "", receipt: String? = null) {
        val history = history()
        if (history.any { it["id"] == id }) return
        val newItem = mapOf(
            "id" to id, "name" to name, "direction" to direction, "size" to size,
            "uri" to uri, "time" to System.currentTimeMillis(),
        )
        val editor = prefs.edit().putString("history", JSONArray(
            (listOf(newItem) + history).take(20).map { JSONObject(it) },
        ).toString())
        if (receipt != null) {
            val receipts = JSONObject(prefs.getString("receipts", "{}")).put(id, receipt)
            editor.putString("receipts", receipts.toString())
        }
        editor.commit()
    }

    @Synchronized
    fun sentReceipt(id: String) {
        val receipts = JSONObject(prefs.getString("receipts", "{}"))
        receipts.remove(id)
        prefs.edit().putString("receipts", receipts.toString()).apply()
    }

    @Synchronized
    fun receipts(peer: Peer): List<String> {
        val receipts = JSONObject(prefs.getString("receipts", "{}"))
        return receipts.keys().asSequence().filter { receipts.getString(it) == peer.pin }.toList()
    }

    @Synchronized
    fun history(): List<Map<String, Any>> {
        val history = JSONArray(prefs.getString("history", "[]"))
        return List(history.length()) { index ->
            val item = history.getJSONObject(index)
            item.keys().asSequence().associateWith { item.get(it) }
        }
    }
}

internal fun ipv4(host: String): Boolean {
    val parts = host.split(".")
    return parts.size == 4 && parts.all { part ->
        part.isNotEmpty() && part.length <= 3 && part.all { it in '0'..'9' } &&
            part.toIntOrNull()?.let { it in 0..255 } == true
    }
}

