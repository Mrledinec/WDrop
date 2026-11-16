package local.transfer.airdrop_app

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import org.json.JSONArray
import org.json.JSONObject

internal class TransferStore(context: Context) {
    private val prefs = context.getSharedPreferences("transfer", Context.MODE_PRIVATE)
    private val resolver = context.contentResolver
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
        val legacyCode = token.matches(Regex("[0-9a-f]{16}[0-9]{8}")) && token.startsWith(device.pin.take(16))
        require(token.matches(Regex("[0-9]{6}")) || legacyCode) {
            "Введите шестизначный код из окна сопряжения на ПК."
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
    fun record(
        id: String, name: String, direction: String, size: Long, uri: String = "",
        receipt: String? = null, grantFlags: Int = 0, hash: String = "",
    ) {
        val history = history()
        if (history.any { it["id"] == id }) return
        if (direction == "sent") keepGrant(Uri.parse(uri), grantFlags)
        val newItem = mapOf(
            "id" to id, "name" to name, "direction" to direction, "size" to size,
            "uri" to uri, "time" to System.currentTimeMillis(), "sha256" to hash,
        )
        val items = listOf(newItem) + history
        val kept = items.take(20)
        val editor = historyEditor(kept, items)
        if (receipt != null) {
            val receipts = JSONObject(prefs.getString("receipts", "{}")).put(id, receipt)
            editor.putString("receipts", receipts.toString())
        }
        if (editor.commit()) releaseUnusedGrants(items, kept)
    }

    @Synchronized
    fun linkSentFile(id: String, uri: Uri, grantFlags: Int, hash: String) {
        val entries = history()
        require(entries.any { it["id"] == id && it["direction"] == "sent" }) { "Запись о файле недоступна." }
        keepGrant(uri, grantFlags)
        val linked = entries.map {
            if (it["id"] == id) it + mapOf("uri" to uri.toString(), "sha256" to hash) else it
        }
        if (historyEditor(linked, entries).commit()) releaseUnusedGrants(entries, linked)
    }

    private fun keepGrant(uri: Uri, flags: Int) {
        if (flags == 0) return
        try {
            resolver.takePersistableUriPermission(uri, flags)
        } catch (_: SecurityException) {
            // Some shares grant access only while their activity is active.
        }
    }

    @Synchronized
    fun forgetHistory(id: String? = null) {
        val entries = history()
        val kept = if (id == null) emptyList() else entries.filterNot { it["id"] == id }
        historyEditor(kept, entries).apply()
        releaseUnusedGrants(entries, kept)
    }

    private fun releaseUnusedGrants(entries: List<Map<String, Any>>, kept: List<Map<String, Any>>) {
        val used = kept.map { it["uri"] }.toSet()
        val removed = entries.filter { it["direction"] == "sent" && it["uri"] !in used }
            .mapNotNull { it["uri"] as? String }.toSet()
        if (removed.isEmpty()) return
        for (permission in resolver.persistedUriPermissions.filter { it.uri.toString() in removed }) {
            var flags = 0
            if (permission.isReadPermission) flags = flags or Intent.FLAG_GRANT_READ_URI_PERMISSION
            if (permission.isWritePermission) flags = flags or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            runCatching { resolver.releasePersistableUriPermission(permission.uri, flags) }
        }
    }

    @Synchronized
    fun receivedIds(): Set<String> = recentReceives(history()).keys().asSequence().toSet()

    private fun historyEditor(kept: List<Map<String, Any>>, entries: List<Map<String, Any>>) =
        prefs.edit()
            .putString("history", JSONArray(kept.map { JSONObject(it) }).toString())
            .putString("recent_receives", recentReceives(entries).toString())

    private fun recentReceives(entries: List<Map<String, Any>>): JSONObject {
        // Preserve delivery deduplication when the user removes visible history.
        val cutoff = System.currentTimeMillis() - 60 * 60 * 1000L
        val recent = JSONObject(prefs.getString("recent_receives", "{}"))
        recent.keys().asSequence().filter { recent.optLong(it) < cutoff }.toList().forEach { recent.remove(it) }
        for (item in entries) {
            val time = (item["time"] as? Number)?.toLong() ?: continue
            if (item["direction"] == "received" && time >= cutoff) recent.put(item["id"] as String, time)
        }
        return recent
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

