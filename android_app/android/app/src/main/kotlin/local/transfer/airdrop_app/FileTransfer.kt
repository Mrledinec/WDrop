package local.transfer.airdrop_app

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Environment
import android.os.SystemClock
import android.provider.MediaStore
import android.provider.OpenableColumns
import android.webkit.MimeTypeMap
import org.json.JSONObject
import java.io.IOException
import java.security.MessageDigest

internal fun mimeForName(name: String): String? =
    MimeTypeMap.getSingleton().getMimeTypeFromExtension(name.substringAfterLast('.', "").lowercase())

internal object FileTransfer {
    @Volatile var sending = false
        private set
    @Volatile var sendStatus = ""
        private set

    @Synchronized
    fun beginSend(): Boolean {
        if (sending) return false
        sending = true
        sendStatus = "Подготовка файла…"
        return true
    }

    fun send(context: Context, store: TransferStore, peer: Peer, files: List<Uri>) {
        var completed = 0
        try {
            for (uri in files) {
                sendFile(context, store, peer, uri)
                completed++
            }
            if (files.size > 1) sendStatus = "Отправлено файлов: $completed"
        } catch (error: Exception) {
            val detail = error.localizedMessage ?: "проверьте подключение"
            sendStatus = if (files.size == 1) "Ошибка отправки: $detail"
                else "Отправлено $completed из " + files.size + ". Ошибка: $detail"
        } finally {
            sending = false
        }
    }

    private fun sendFile(context: Context, store: TransferStore, peer: Peer, uri: Uri) {
        sendStatus = "Подготовка файла…"
        val resolver = context.contentResolver
        val name = resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
            if (it.moveToFirst()) it.getString(0) else null
        }?.take(255)?.takeIf { it.isNotBlank() } ?: "file"
        val buffer = ByteArray(BUFFER_SIZE)
        val digest = MessageDigest.getInstance("SHA-256")
        var size = 0L
        resolver.openInputStream(uri)?.use { input ->
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
                size += count
            }
        } ?: throw IOException("Не удалось открыть файл")
        val api = PeerApi(peer, store.network)
        val payload = JSONObject().put("name", name).put("size", size).put("sha256", digest.digest().hex())
        var offer = Offer.fromJson(api.objectRequest("/offers", payload))
        val id = offer.id
        val deadline = SystemClock.elapsedRealtime() + 65_000
        while (offer.state == "pending" && SystemClock.elapsedRealtime() < deadline) {
            sendStatus = "Ожидаем подтверждения на ПК · " + offer.secondsLeft + " с"
            Thread.sleep(750)
            offer = Offer.fromJson(api.objectRequest("/offers/$id"))
        }
        when (offer.state) {
            "accepted" -> Unit
            "rejected" -> throw IOException("ПК отклонил передачу")
            "expired", "pending" -> throw IOException("Время ожидания подтверждения истекло")
            else -> throw IOException("ПК не может принять файл")
        }
        api.request("/offers/$id/content", "PUT", timeout = 20_000) { connection ->
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/octet-stream")
            connection.setFixedLengthStreamingMode(size)
            val source = resolver.openInputStream(uri) ?: throw IOException("Исходный файл недоступен")
            source.use { input ->
                connection.outputStream.use { output ->
                    var sent = 0L
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        output.write(buffer, 0, count)
                        sent += count
                        sendStatus = "Отправка · " + progress(sent, size) + " %"
                    }
                }
            }
            api.check(connection)
        }
        store.record(id, name, "sent", size)
        sendStatus = "Отправлено: $name"
    }

    fun receive(
        context: Context, store: TransferStore, peer: Peer, api: PeerApi, offer: Offer,
        onProgress: (Int) -> Unit,
    ): Uri {
        val resolver = context.contentResolver
        if (!store.accepts(offer.size)) throw IOException("Файл превышает лимит приёма")
        val resolverVolume = Environment.getExternalStorageDirectory()
        if (offer.size > resolverVolume.usableSpace) throw IOException("На телефоне не хватает места")
        val name = offer.name
            .replace(Regex("[\\p{Cntrl}<>:\"/\\\\|?*]"), "_").trim(' ', '.').take(180)
            .ifBlank { "file" }
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, name)
            put(MediaStore.Downloads.MIME_TYPE, mimeForName(name) ?: "application/octet-stream")
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Local Transfer")
            put(MediaStore.Downloads.IS_PENDING, 1)
        }
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: throw IOException("Не удалось создать файл в загрузках")
        try {
            val digest = MessageDigest.getInstance("SHA-256")
            var total = 0L
            api.request("/offers/" + offer.id + "/content", timeout = 20_000) { connection ->
                api.check(connection)
                connection.inputStream.use { input ->
                    val target = resolver.openOutputStream(uri) ?: throw IOException("Не удалось открыть файл для записи")
                    target.use { output ->
                        val buffer = ByteArray(BUFFER_SIZE)
                        var previous = -1
                        while (true) {
                            if (Thread.currentThread().isInterrupted) throw IOException("Передача прервана")
                            val count = input.read(buffer)
                            if (count < 0) break
                            total += count
                            if (total > offer.size) throw IOException("Размер файла отличается от заявленного")
                            output.write(buffer, 0, count)
                            digest.update(buffer, 0, count)
                            val current = progress(total, offer.size)
                            if (current != previous) {
                                previous = current
                                onProgress(current)
                            }
                        }
                    }
                }
            }
            if (total != offer.size || digest.digest().hex() != offer.digest) {
                throw IOException("Проверка целостности файла не пройдена")
            }
            val published = ContentValues().apply { put(MediaStore.Downloads.IS_PENDING, 0) }
            if (resolver.update(uri, published, null, null) != 1) throw IOException("Не удалось сохранить файл")
            store.record(offer.id, offer.name, "received", offer.size, uri.toString(), peer.pin)
            return uri
        } catch (error: Exception) {
            runCatching { resolver.delete(uri, null, null) }
            throw error
        }
    }

    private fun progress(bytes: Long, size: Long) =
        if (size == 0L) 100 else (bytes.toDouble() * 100 / size).toInt().coerceIn(0, 100)
}

