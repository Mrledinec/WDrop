package local.transfer.airdrop_app

import android.Manifest
import android.app.Activity
import android.app.DownloadManager
import android.app.NotificationManager
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.net.nsd.NsdManager
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.provider.DocumentsContract
import android.provider.MediaStore
import android.provider.OpenableColumns
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.security.MessageDigest
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
    private data class HistorySelection(val id: String, val location: Boolean, val result: MethodChannel.Result)

    private val store by lazy { transferStore(this) }
    private val update by lazy { AppUpdate(applicationContext) }
    private val executor = Executors.newCachedThreadPool()
    private var picking: Pair<Peer, MethodChannel.Result>? = null
    private var historySelection: HistorySelection? = null
    private var sharedFiles = emptyList<Uri>()
    private var sharedGrantFlags = 0
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
        sharedGrantFlags = persistableFlags(intent.flags)
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
                        "updateVersion" -> result.success(update.version)
                        "checkUpdate" -> executor.execute {
                            val operation = runCatching { update.check() }
                            runOnUiThread {
                                operation.fold(result::success) { error -> fail(result, error) }
                            }
                        }
                        "installUpdate" -> installUpdate(result)
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
                            startSending(peer, sharedFiles, sharedGrantFlags)
                            sharedFiles = emptyList()
                            result.success(null)
                        }
                        "clearShared" -> {
                            sharedFiles = emptyList()
                            result.success(null)
                        }
                        "clearHistory" -> {
                            store.forgetHistory()
                            result.success(null)
                        }
                        "forgetFile" -> {
                            require(id.isNotEmpty())
                            store.forgetHistory(id)
                            result.success(null)
                        }
                        "deleteHistoryFile" -> {
                            deleteHistoryFile(id)
                            result.success(null)
                        }
                        "historyFileInfo" -> result.success(historyFileInfo(id))
                        "historyFileLocation", "openHistoryFile" ->
                            historyAction(HistorySelection(id, call.method == "historyFileLocation", result))
                        else -> result.notImplemented()
                    }
                } catch (error: Exception) {
                    fail(result, error)
                }
            }
    }

    private fun historyItem(id: String): Map<String, Any> =
        requireNotNull(store.history().find { it["id"] == id }) {
            "Запись о файле недоступна."
        }

    private fun historyUri(item: Map<String, Any>): Uri? =
        Uri.parse(item["uri"] as? String ?: "").takeIf { it.scheme == "content" }

    private fun historyFileInfo(id: String): Map<String, Any> {
        val item = historyItem(id)
        val info = item.toMutableMap()
        val uri = historyUri(item)
        if (item["direction"] == "received") info["folder"] = "Download/Local Transfer"
        val available = uri != null && runCatching {
            val fields = if (uri.authority == "media") {
                arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE, MediaStore.MediaColumns.RELATIVE_PATH)
            } else {
                arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE)
            }
            contentResolver.query(uri, fields, null, null, null)?.use { cursor ->
                if (!cursor.moveToFirst()) return@use false
                val name = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                val size = cursor.getColumnIndex(OpenableColumns.SIZE)
                val folder = cursor.getColumnIndex(MediaStore.MediaColumns.RELATIVE_PATH)
                if (name >= 0) cursor.getString(name)?.let { info["name"] = it }
                if (size >= 0 && !cursor.isNull(size)) info["size"] = cursor.getLong(size)
                if (folder >= 0) cursor.getString(folder)?.let { info["folder"] = it.trimEnd('/') }
                true
            } ?: false
        }.getOrDefault(false)
        if (uri != null) runCatching { contentResolver.getType(uri) }.getOrNull()?.let { info["type"] = it }
        info["available"] = available
        return info
    }

    private fun deleteHistoryFile(id: String) {
        val uri = requireNotNull(historyUri(historyItem(id))) { "Ссылка на исходный файл не сохранилась." }
        val deleted = try {
            when {
                DocumentsContract.isDocumentUri(this, uri) -> DocumentsContract.deleteDocument(contentResolver, uri)
                uri.authority == "media" -> contentResolver.delete(uri, null, null) > 0
                else -> throw SecurityException()
            }
        } catch (_: SecurityException) {
            throw IllegalArgumentException("Источник не разрешает удалить файл из приложения. Удалите его через «Файлы».")
        }
        require(deleted) { "Файл недоступен или источник не поддерживает удаление." }
        store.forgetHistory(id)
    }

    private fun historyAction(selection: HistorySelection) {
        val item = historyItem(selection.id)
        val received = item["direction"] == "received"
        executor.execute {
            val target = runCatching {
                historyUri(item)?.let { uri ->
                    val available = runCatching {
                        contentResolver.openFileDescriptor(uri, "r")?.use { true } ?: false
                    }.getOrDefault(false)
                    when {
                        selection.location && (received || available) -> historyFolder(selection.id, uri)
                        available -> uri
                        else -> null
                    }
                }
            }
            runOnUiThread {
                try {
                    val uri = target.getOrThrow()
                    if (uri == null && !received) {
                        selectHistoryFile(selection)
                    } else {
                        requireNotNull(uri) { "Файл недоступен." }
                        launchHistoryAction(selection, item, uri)
                        selection.result.success(null)
                    }
                } catch (error: Exception) {
                    fail(selection.result, error)
                }
            }
        }
    }

    private fun historyFolder(id: String, uri: Uri): Uri? {
        if (DocumentsContract.isDocumentUri(this, uri)) {
            if (uri.authority == "com.android.externalstorage.documents") {
                val document = DocumentsContract.getDocumentId(uri)
                val volume = document.substringBefore(':')
                val folder = document.substringAfter(':').substringBeforeLast('/', "")
                return DocumentsContract.buildDocumentUri(uri.authority, "$volume:$folder")
            }
            return uri
        }
        val path = historyFileInfo(id)["folder"] as? String ?: return null
        return DocumentsContract.buildDocumentUri("com.android.externalstorage.documents", "primary:$path")
    }

    private fun launchHistoryAction(selection: HistorySelection, item: Map<String, Any>, target: Uri) {
        if (!selection.location) {
            val mime = contentResolver.getType(target) ?: mimeForName(item["name"].toString())
                ?: "application/octet-stream"
            val intent = Intent(Intent.ACTION_VIEW).setDataAndType(target, mime)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            require(intent.resolveActivity(packageManager) != null) { "Для этого типа файла нет приложения." }
            startActivity(Intent.createChooser(intent, "Открыть файл"))
            return
        }
        try {
            startActivity(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "*/*"
                putExtra(DocumentsContract.EXTRA_INITIAL_URI, target)
            })
        } catch (_: ActivityNotFoundException) {
            if (item["direction"] == "received") {
                startActivity(Intent(DownloadManager.ACTION_VIEW_DOWNLOADS))
            } else {
                throw IllegalArgumentException("Системное приложение «Файлы» недоступно.")
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun selectHistoryFile(selection: HistorySelection) {
        require(historySelection == null && picking == null) { "Сначала закройте выбор файла." }
        historySelection = selection
        try {
            startActivityForResult(
                Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*"),
                PICK_HISTORY_FILE,
            )
        } catch (error: Exception) {
            historySelection = null
            throw error
        }
    }

    private fun finishHistorySelection(resultCode: Int, data: Intent?) {
        val selection = historySelection ?: return
        historySelection = null
        val uri = data?.data
        if (resultCode != Activity.RESULT_OK || uri == null) {
            selection.result.success(null)
            return
        }
        executor.execute {
            val target = runCatching {
                val item = historyItem(selection.id)
                val expectedHash = item["sha256"] as? String ?: ""
                if (expectedHash.isEmpty()) {
                    val name = contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
                        ?.use { if (it.moveToFirst()) it.getString(0) else null }
                    require(name?.take(255) == item["name"]) { "Выберите исходный файл «${item["name"]}»." }
                }
                val expectedSize = (item["size"] as Number).toLong()
                var size = 0L
                val digest = MessageDigest.getInstance("SHA-256")
                requireNotNull(contentResolver.openInputStream(uri)) { "Не удалось открыть выбранный файл." }.use { input ->
                    val buffer = ByteArray(256 * 1024)
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        size += count
                        require(size <= expectedSize) { "Размер файла отличается от записи в истории." }
                        digest.update(buffer, 0, count)
                    }
                }
                val hash = digest.digest().hex()
                require(size == expectedSize) { "Размер файла отличается от записи в истории." }
                require(expectedHash.isEmpty() || expectedHash == hash) { "Выбранный файл отличается от отправленного." }
                store.linkSentFile(selection.id, uri, persistableFlags(data.flags), hash)
                val destination = if (selection.location) {
                    requireNotNull(historyFolder(selection.id, uri)) { "Источник не предоставил расположение файла." }
                } else uri
                item to destination
            }
            runOnUiThread {
                try {
                    val (item, destination) = target.getOrThrow()
                    launchHistoryAction(selection, item, destination)
                    selection.result.success(null)
                } catch (error: Exception) {
                    fail(selection.result, error)
                }
            }
        }
    }

    private fun installUpdate(result: MethodChannel.Result) {
        if (!packageManager.canRequestPackageInstalls()) {
            startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
            result.success(false)
            return
        }
        executor.execute {
            val operation = runCatching { update.download() }
            runOnUiThread {
                runCatching {
                    val uri = FileProvider.getUriForFile(this, "$packageName.updates", operation.getOrThrow())
                    startActivity(Intent(Intent.ACTION_VIEW).apply {
                        setDataAndType(uri, "application/vnd.android.package-archive")
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    })
                    true
                }.fold(result::success) { error -> fail(result, error) }
            }
        }
    }

    private fun snapshot(): Map<String, Any?> {
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
            "sendProgress" to FileTransfer.sendProgress,
            "receiveStatus" to ReceiveService.receiveMessage,
            "receiveProgress" to ReceiveService.receiveProgress,
        )
    }

    @Suppress("DEPRECATION")
    private fun pickFile(id: String, result: MethodChannel.Result) {
        require(!FileTransfer.sending && picking == null && historySelection == null) { "Завершите выбор файла или отправку." }
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
        if (requestCode == PICK_HISTORY_FILE) {
            finishHistorySelection(resultCode, data)
            return
        }
        if (requestCode != PICK_FILE) return
        val (peer, result) = picking ?: return
        picking = null
        val uri = data?.data
        if (resultCode != Activity.RESULT_OK || uri == null) {
            result.success(false)
            return
        }
        try {
            startSending(peer, listOf(uri), persistableFlags(data.flags))
            result.success(true)
        } catch (error: Exception) {
            fail(result, error)
        }
    }

    private fun persistableFlags(flags: Int): Int =
        if (flags and Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION != 0) {
            flags and (Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        } else 0

    private fun startSending(peer: Peer, files: List<Uri>, grantFlags: Int) {
        require(picking == null) { "Сначала закройте выбор файла" }
        require(FileTransfer.beginSend()) { "Уже выполняется отправка" }
        executor.execute { FileTransfer.send(applicationContext, store, peer, files, grantFlags) }
    }

    private fun fail(result: MethodChannel.Result, error: Throwable) {
        result.error("transfer", error.localizedMessage ?: "Операция не выполнена", null)
    }

    companion object {
        private const val PICK_FILE = 401
        private const val PICK_HISTORY_FILE = 402
    }
}

