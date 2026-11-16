package local.transfer.airdrop_app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.IBinder
import android.os.Build
import android.os.PowerManager
import android.os.SystemClock
import android.util.Log
import java.net.Inet4Address
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

internal data class Incoming(val peer: Peer, val offer: Offer, val expires: Long) {
    fun display() = mapOf(
        "id" to offer.id, "name" to offer.name, "size" to offer.size, "device" to peer.displayName,
        "seconds" to ((expires - SystemClock.elapsedRealtime() + 999) / 1000).coerceAtLeast(0),
    )
}

class ReceiveService : Service() {
    private val poller = Executors.newSingleThreadScheduledExecutor()
    private val downloads = Executors.newSingleThreadExecutor()
    private val connections = ConcurrentHashMap<String, PeerApi>()
    private val reachable = ConcurrentHashMap<String, Boolean>()
    private lateinit var store: TransferStore
    private lateinit var notifications: NotificationManager
    private var discovery: LanDiscovery? = null
    private var discoveryNetwork = ""
    private var started = false
    private var lastStatusUpdate = 0L

    override fun onCreate() {
        super.onCreate()
        store = transferStore(this)
        notifications = getSystemService(NotificationManager::class.java)
        notifications.createNotificationChannel(
            NotificationChannel(SERVICE_CHANNEL, "Готовность к приёму", NotificationManager.IMPORTANCE_LOW)
        )
        notifications.createNotificationChannel(
            NotificationChannel(OFFERS_CHANNEL, "Входящие файлы", NotificationManager.IMPORTANCE_HIGH)
        )
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == STOP || !store.ready) {
            store.ready = false
            stopSelf()
            return START_NOT_STICKY
        }
        if (!started) {
            started = true
            running = true
            startForeground(SERVICE_NOTIFICATION, readyNotification())
            poller.scheduleWithFixedDelay({
                runCatching { poll() }.onFailure { Log.w("LocalTransfer", "Receive polling failed", it) }
            }, 0, 1500, TimeUnit.MILLISECONDS)
        }
        val id = intent?.getStringExtra("id")
        val action = intent?.action
        if (id != null && (action == ACCEPT || action == REJECT)) {
            pending[id]?.let { item -> handle(item, action == ACCEPT) }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        running = false
        online = emptySet()
        discovery?.close()
        poller.shutdownNow()
        downloads.shutdownNow()
        pending.values.forEach { notifications.cancel(offerNotificationId(it.offer.id)) }
        pending.clear()
        super.onDestroy()
    }

    private fun api(peer: Peer): PeerApi {
        val key = peer.pin + "|" + peer.host + "|" + peer.port + "|" + peer.token
        return connections.computeIfAbsent(key) { PeerApi(peer, store.network) }
    }

    private fun poll() {
        val key = store.network.selected + ":" + runCatching { store.network.current()?.networkHandle }.getOrNull()
        if (key != discoveryNetwork) {
            discoveryNetwork = key
            discovery?.close()
            discovery = LanDiscovery(
                getSystemService(NsdManager::class.java), store.network, resolved = { device ->
                    runCatching { poller.execute { runCatching { store.reconnect(device) } } }
                },
            ).also { it.start() }
        }
        val now = SystemClock.elapsedRealtime()
        pending.values.filter { it.expires <= now }.forEach { removePrompt(it.offer.id) }
        val peers = store.peers()
        val completed = store.receivedIds()
        reachable.keys.retainAll(peers.map { it.pin }.toSet())
        for (peer in peers) {
            val api = api(peer)
            try {
                val offers = api.offers()
                reachable[peer.pin] = true
                val receipts = store.receipts(peer).toSet()
                for (id in receipts) deliverReceipt(api, id)
                for (offer in offers) {
                    if (offer.id in active || offer.id in receipts || offer.id in completed) continue
                    val item = Incoming(peer, offer, SystemClock.elapsedRealtime() + offer.secondsLeft * 1000L)
                    when {
                        offer.state == "accepted" || offer.state == "transferring" -> handle(item, true)
                        offer.state != "pending" || offer.secondsLeft == 0 -> Unit
                        !store.accepts(offer.size) -> handle(item, false)
                        peer.trusted -> handle(item, true)
                        pending.putIfAbsent(offer.id, item) == null -> notifyOffer(item)
                    }
                }
                val available = offers.map { it.id }.toSet()
                pending.values.filter { it.peer.pin == peer.pin && it.offer.id !in available }
                    .forEach { removePrompt(it.offer.id) }
            } catch (error: Exception) {
                reachable[peer.pin] = false
                Log.d("LocalTransfer", "PC unavailable: " + error.javaClass.simpleName)
            }
        }
        if (now - lastStatusUpdate >= 3000) {
            lastStatusUpdate = now
            online = reachable.filterValues { it }.keys.toSet()
            notifications.notify(SERVICE_NOTIFICATION, readyNotification())
        }
    }

    private fun handle(item: Incoming, accept: Boolean) {
        val id = item.offer.id
        if (!active.add(id)) return
        removePrompt(id)
        try {
            downloads.execute {
                val currentPeer = store.peers().find { it.pin == item.peer.pin }
                if (currentPeer == null || id in store.receivedIds() || id in store.receipts(currentPeer)) {
                    active.remove(id)
                    return@execute
                }
                val api = api(currentPeer)
                var accepted = item.offer.state in setOf("accepted", "transferring")
                try {
                    if (!accepted) {
                        val decision = api.decide(id, accept)
                        accepted = decision.state == "accepted"
                    }
                    if (accepted) {
                        receiveMessage = ""
                        notifyProgress(item, 0)
                        val wake = getSystemService(PowerManager::class.java)
                            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "LocalTransfer:receive")
                        wake.acquire()
                        try {
                            FileTransfer.receive(this, store, currentPeer, api, item.offer) { notifyProgress(item, it) }
                        } finally {
                            wake.release()
                        }
                        deliverReceipt(api, id)
                        notifyResult(item, "Сохранено в Download/Local Transfer")
                    }
                } catch (error: Exception) {
                    if (accepted && id !in store.receipts(currentPeer)) runCatching { api.receipt(id, false) }
                    val message = error.localizedMessage ?: "Проверьте подключение"
                    receiveMessage = "Ошибка приёма: $message"
                    if (accept) notifyResult(item, message)
                } finally {
                    receiveProgress = emptyMap()
                    active.remove(id)
                }
            }
        } catch (error: java.util.concurrent.RejectedExecutionException) {
            active.remove(id)
        }
    }

    private fun deliverReceipt(api: PeerApi, id: String) {
        try {
            api.receipt(id, true)
            store.sentReceipt(id)
        } catch (error: ApiException) {
            if (error.status == 404 || error.status == 409) store.sentReceipt(id)
        } catch (error: Exception) {
            Log.d("LocalTransfer", "Receipt will be retried")
        }
    }

    private fun openApp() = PendingIntent.getActivity(
        this, 0, Intent(this, MainActivity::class.java).setAction(Intent.ACTION_MAIN)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK), PendingIntent.FLAG_IMMUTABLE,
    )

    private fun action(action: String, id: String? = null): PendingIntent {
        val intent = Intent(this, ReceiveService::class.java).setAction(action)
        if (id != null) intent.putExtra("id", id)
        return PendingIntent.getService(
            this, id?.hashCode() ?: 0, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
    }

    private fun readyNotification() = Notification.Builder(this, SERVICE_CHANNEL)
        .setSmallIcon(android.R.drawable.stat_sys_download)
        .setContentTitle("Готов принимать файлы")
        .setContentText(if (online.isEmpty()) "Ожидаем подключения ПК" else "Подключено устройств: " + online.size)
        .setContentIntent(openApp())
        .setOngoing(true)
        .addAction(Notification.Action.Builder(null, "Остановить", action(STOP)).build())
        .build()

    private fun notifyOffer(item: Incoming) {
        val id = item.offer.id
        val notification = Notification.Builder(this, OFFERS_CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle("Файл от " + item.peer.displayName)
            .setContentText(item.offer.name + " · " + item.offer.size + " Б")
            .setContentIntent(openApp())
            .setVisibility(Notification.VISIBILITY_PRIVATE)
            .setTimeoutAfter(item.offer.secondsLeft * 1000L)
            .addAction(Notification.Action.Builder(null, "Принять", action(ACCEPT, id)).build())
            .addAction(Notification.Action.Builder(null, "Отклонить", action(REJECT, id)).build())
            .build()
        notifications.notify(offerNotificationId(id), notification)
    }

    private fun notifyProgress(item: Incoming, progress: Int) {
        receiveProgress = mapOf("name" to item.offer.name, "percent" to progress)
        val notification = Notification.Builder(this, SERVICE_CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle("Приём файла")
            .setContentText(item.offer.name)
            .setProgress(100, progress, false)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(openApp())
            .build()
        notifications.notify(offerNotificationId(item.offer.id), notification)
    }

    private fun notifyResult(item: Incoming, message: String) {
        val notification = Notification.Builder(this, OFFERS_CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle(item.offer.name)
            .setContentText(message)
            .setContentIntent(openApp())
            .setAutoCancel(true)
            .setOnlyAlertOnce(true)
            .build()
        notifications.notify(offerNotificationId(item.offer.id), notification)
    }

    private fun removePrompt(id: String) {
        if (pending.remove(id) != null) notifications.cancel(offerNotificationId(id))
    }

    companion object {
        const val ACCEPT = "local.transfer.ACCEPT"
        const val REJECT = "local.transfer.REJECT"
        const val STOP = "local.transfer.STOP"
        private const val SERVICE_CHANNEL = "receive_service"
        private const val OFFERS_CHANNEL = "receive_offers"
        private const val SERVICE_NOTIFICATION = 100
        private fun offerNotificationId(id: String) = id.hashCode().let { if (it == SERVICE_NOTIFICATION) 101 else it }

        @Volatile var running = false
            private set
        @Volatile var online: Set<String> = emptySet()
            private set
        @Volatile var receiveMessage = ""
            private set
        @Volatile var receiveProgress: Map<String, Any> = emptyMap()
            private set
        internal val pending = ConcurrentHashMap<String, Incoming>()
        private val active = ConcurrentHashMap.newKeySet<String>()
    }
}

internal data class LanDevice(
    val service: String, val pin: String, val name: String, val host: String, val port: Int, val ready: Boolean,
)

@Suppress("DEPRECATION")
internal class LanDiscovery(
    private val manager: NsdManager,
    private val network: LocalNetwork,
    private val resolved: (LanDevice) -> Unit,
    private val lost: (String) -> Unit = {},
) : NsdManager.DiscoveryListener {
    private val services = ConcurrentLinkedQueue<NsdServiceInfo>()
    private val resolving = AtomicBoolean(false)
    @Volatile private var started = false
    @Volatile private var closed = false

    fun start() {
        val result = runCatching {
            val selected = network.current()
            if (selected != null && Build.VERSION.SDK_INT >= 33) {
                manager.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, selected, { it.run() }, this)
            } else {
                manager.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, this)
            }
        }
        if (result.isFailure) Log.d("LocalTransfer", "mDNS discovery unavailable")
    }

    fun close() {
        started = false
        closed = true
        runCatching { manager.stopServiceDiscovery(this) }
        services.clear()
    }

    override fun onDiscoveryStarted(serviceType: String) {
        if (closed) return
        started = true
        resolveNext()
    }
    override fun onDiscoveryStopped(serviceType: String) { started = false }
    override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) { close() }
    override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) { started = false }
    override fun onServiceLost(serviceInfo: NsdServiceInfo) { lost(serviceInfo.serviceName) }
    override fun onServiceFound(serviceInfo: NsdServiceInfo) {
        if (closed) return
        services.add(serviceInfo)
        resolveNext()
    }

    private fun resolveNext() {
        if (!started || !resolving.compareAndSet(false, true)) return
        val info = services.poll()
        if (info == null) {
            resolving.set(false)
            return
        }
        val listener = object : NsdManager.ResolveListener {
            override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) = finished()
            override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
                val pin = serviceInfo.attributes["id"]?.toString(Charsets.UTF_8)
                val address = (serviceInfo.host as? Inet4Address)?.hostAddress
                if (!closed && pin != null && pin.matches(Regex("[0-9a-f]{64}"))
                    && address != null && serviceInfo.port in 1..65535
                ) {
                    val name = serviceInfo.attributes["name"]?.toString(Charsets.UTF_8) ?: serviceInfo.serviceName
                    val ready = serviceInfo.attributes["ready"]?.toString(Charsets.UTF_8) == "1"
                    resolved(LanDevice(serviceInfo.serviceName, pin, name, address, serviceInfo.port, ready))
                }
                finished()
            }
            private fun finished() {
                resolving.set(false)
                resolveNext()
            }
        }
        if (runCatching { manager.resolveService(info, listener) }.isFailure) resolving.set(false)
    }
}

