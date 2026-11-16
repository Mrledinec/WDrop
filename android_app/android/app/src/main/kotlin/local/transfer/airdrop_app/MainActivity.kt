package local.transfer.airdrop_app

import android.Manifest
import android.app.Activity
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.net.nsd.NsdManager
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.util.concurrent.Executors
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

private lateinit var sharedStore: TransferStore

@Synchronized
internal fun transferStore(context: Context): TransferStore {
    if (!::sharedStore.isInitialized) sharedStore = TransferStore(context.applicationContext)
    return sharedStore
}

class MainActivity : FlutterActivity() {
    private val store by lazy { transferStore(this) }
    private val executor = Executors.newCachedThreadPool()
    private var picking: Pair<Peer, MethodChannel.Result>? = null
    private var sharedFiles = emptyList<Uri>()
    private val discoveries = ConcurrentHashMap<String, LanDevice>()
    private val probe = Executors.newSingleThreadScheduledExecutor()
    @Volatile private var reachable = emptySet<String>()
    private var probeTask: ScheduledFuture<*>? = null
    private var discovery: LanDiscovery? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) readSharedFiles(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        readSharedFiles(intent)
    }

    @Suppress("DEPRECATION")
    private fun readSharedFiles(intent: Intent) {
        val files = when (intent.action) {
            Intent.ACTION_SEND -> listOfNotNull(intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM))
            Intent.ACTION_SEND_MULTIPLE -> intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM).orEmpty()
            else -> return
        }
        val clip = intent.clipData
        val clipUris = if (clip == null) emptyList() else
            (0 until clip.itemCount).mapNotNull { clip.getItemAt(it).uri }
        sharedFiles = (files + clipUris).filter { it.scheme == "content" }.distinct()
    }

    override fun onPostResume() {
        super.onPostResume()
        if (store.ready && !ReceiveService.running) {
            startForegroundService(Intent(this, ReceiveService::class.java))
        }
    }

    override fun onStart() {
        super.onStart()
        startDiscovery()
        probeTask = probe.scheduleWithFixedDelay({
            reachable = store.peers().filter { peer ->
                runCatching { PeerApi(peer, store.network).offers() }.isSuccess
            }.map { it.pin }.toSet()
        }, 0, 3, TimeUnit.SECONDS)
    }

    override fun onStop() {
        discovery?.close()
        discovery = null
        probeTask?.cancel(true)
        super.onStop()
    }

    override fun onDestroy() {
        discovery?.close()
        probe.shutdownNow()
        executor.shutdown()
        super.onDestroy()
    }

    private fun startDiscovery() {
        discovery?.close()
        discoveries.clear()
        discovery = LanDiscovery(
            getSystemService(NsdManager::class.java), store.network,
            resolved = { device ->
                discoveries[device.service] = device
                runCatching { executor.execute { runCatching { store.reconnect(device) } } }
            },
            lost = { discoveries.remove(it) },
        ).also { it.start() }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "local.transfer/control")
            .setMethodCallHandler { call, result ->
                try {
                    val id = call.argument<String>("id").orEmpty()
                    when (call.method) {
                        "state" -> result.success(snapshot())
                        "discover" -> {
                            startDiscovery()
                            result.success(null)
                        }
                        "network" -> {
                            val network = call.argument<String>("network").orEmpty()
                            store.network.select(network)
                            reachable = emptySet()
                            startDiscovery()
                            result.success(null)
                        }
                        "pairDiscovered" -> {
                            val device = discoveries.values.find { it.pin == id && it.ready }
                                ?: throw IllegalArgumentException("ПК больше не готов к подключению. Повторите поиск.")
                            val code = call.argument<String>("code").orEmpty()
                            executor.execute {
                                val operation = runCatching { store.pairDiscovered(device, code).display() }
                                runOnUiThread { operation.fold(result::success) { error -> fail(result, error) } }
                            }
                        }
                        "pair" -> {
                            val code = call.argument<String>("code").orEmpty().trim()
                            require(code.length in 2..2048) { "Введите код подключения с ПК" }
                            executor.execute {
                                val operation = runCatching { store.pair(code).display() }
                                runOnUiThread {
                                    operation.fold(result::success) { error -> fail(result, error) }
                                }
                            }
                        }
                        "ready" -> {
                            val enabled = call.argument<Boolean>("enabled") == true
                            store.ready = enabled
                            val intent = Intent(this, ReceiveService::class.java)
                            if (enabled) {
                                try {
                                    startForegroundService(intent)
                                } catch (error: Exception) {
                                    store.ready = false
                                    throw error
                                }
                                if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(
                                        Manifest.permission.POST_NOTIFICATIONS
                                    ) != PackageManager.PERMISSION_GRANTED
                                ) {
                                    requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 99)
                                }
                            } else {
                                stopService(intent)
                            }
                            result.success(null)
                        }
                        "limit" -> {
                            val limit = call.argument<Int>("value") ?: DEFAULT_LIMIT_MIB
                            require(limit in 0..1_048_576) { "Некорректный лимит" }
                            store.limitMiB = limit
                            result.success(null)
                        }
                        "trust" -> {
                            val trusted = call.argument<Boolean>("value") == true
                            store.update(id) { it.copy(trusted = trusted) }
                            result.success(null)
                        }
                        "rename" -> {
                            val name = call.argument<String>("name").orEmpty().trim()
                            require(name.length in 1..80) { "Введите имя длиной от 1 до 80 символов" }
                            store.update(id) { it.copy(alias = name) }
                            result.success(null)
                        }
                        "address" -> {
                            val host = call.argument<String>("host").orEmpty().trim()
                            require(ipv4(host)) { "Укажите IPv4-адрес ПК" }
                            store.update(id) { it.copy(host = host) }
                            result.success(null)
                        }
                        "remove" -> {
                            store.remove(id)
                            result.success(null)
                        }
                        "decide" -> {
                            val item = ReceiveService.pending[id]
                            require(item != null && item.expires > SystemClock.elapsedRealtime()) {
                                "Время ожидания истекло"
                            }
                            val action = if (call.argument<Boolean>("accept") == true) {
                                ReceiveService.ACCEPT
                            } else {
                                ReceiveService.REJECT
                            }
                            startService(Intent(this, ReceiveService::class.java).setAction(action).putExtra("id", id))
                            result.success(null)
                        }
                        "send" -> pickFile(id, result)
                        "sendShared" -> {
                            require(sharedFiles.isNotEmpty()) { "Выберите файл через меню «Поделиться»" }
                            val peer = store.peers().find { it.pin == id }
                                ?: throw IllegalArgumentException("ПК удалён")
                            startSending(peer, sharedFiles)
                            sharedFiles = emptyList()
                            result.success(null)
                        }
                        "clearShared" -> {
                            sharedFiles = emptyList()
                            result.success(null)
                        }
                        "open" -> {
                            val uri = Uri.parse(call.argument<String>("uri").orEmpty())
                            require(uri.scheme == "content")
                            val filename = call.argument<String>("name").orEmpty()
                            val mime = mimeForName(filename) ?: contentResolver.getType(uri)
                                ?: "application/octet-stream"
                            contentResolver.openFileDescriptor(uri, "r")?.close()
                                ?: throw IllegalArgumentException("Файл недоступен в загрузках")
                            val intent = Intent(Intent.ACTION_VIEW).setDataAndType(uri, mime)
                                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                            require(intent.resolveActivity(packageManager) != null) {
                                "Для этого типа файла нет приложения. Файл сохранён в Download/Local Transfer."
                            }
                            startActivity(Intent.createChooser(intent, "Открыть файл"))
                            result.success(null)
                        }
                        else -> result.notImplemented()
                    }
                } catch (error: Exception) {
                    fail(result, error)
                }
            }
    }

    private fun snapshot(): Map<String, Any> {
        val online = reachable
        val peers = store.peers()
        return mapOf(
            "ready" to store.ready,
            "notifications" to getSystemService(NotificationManager::class.java).areNotificationsEnabled(),
            "limit" to store.limitMiB,
            "peers" to peers.map { it.display() + ("online" to (it.pin in online)) },
            "networks" to store.network.options(),
            "network" to store.network.selected,
            "discovered" to discoveries.values.filter { candidate -> candidate.ready && peers.none { it.pin == candidate.pin } }
                .distinctBy { it.pin }.map { mapOf("id" to it.pin, "name" to it.name, "host" to it.host) },
            "incoming" to ReceiveService.pending.values
                .filter { it.expires > SystemClock.elapsedRealtime() }
                .sortedBy { it.expires }.map { it.display() },
            "history" to store.history(),
            "sending" to FileTransfer.sending,
            "sharedCount" to sharedFiles.size,
            "sendStatus" to FileTransfer.sendStatus,
            "receiveStatus" to ReceiveService.receiveMessage,
        )
    }

    @Suppress("DEPRECATION")
    private fun pickFile(id: String, result: MethodChannel.Result) {
        require(!FileTransfer.sending && picking == null) { "Уже выполняется отправка" }
        val peer = store.peers().find { it.pin == id } ?: throw IllegalArgumentException("ПК удалён")
        val picker = Intent(Intent.ACTION_OPEN_DOCUMENT)
            .addCategory(Intent.CATEGORY_OPENABLE).setType("*/*")
        picking = peer to result
        try {
            startActivityForResult(picker, PICK_FILE)
        } catch (error: Exception) {
            picking = null
            throw error
        }
    }

    @Deprecated("Android result is used by the Flutter host activity")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != PICK_FILE) return
        val (peer, result) = picking ?: return
        picking = null
        val uri = data?.data
        if (resultCode != Activity.RESULT_OK || uri == null) {
            result.success(false)
            return
        }
        try {
            startSending(peer, listOf(uri))
            result.success(true)
        } catch (error: Exception) {
            fail(result, error)
        }
    }

    private fun startSending(peer: Peer, files: List<Uri>) {
        require(picking == null) { "Сначала закройте выбор файла" }
        require(FileTransfer.beginSend()) { "Уже выполняется отправка" }
        executor.execute { FileTransfer.send(applicationContext, store, peer, files) }
    }

    private fun fail(result: MethodChannel.Result, error: Throwable) {
        result.error("transfer", error.localizedMessage ?: "Операция не выполнена", null)
    }

    companion object {
        private const val PICK_FILE = 401
    }
}

