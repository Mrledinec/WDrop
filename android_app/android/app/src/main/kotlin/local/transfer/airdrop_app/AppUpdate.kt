package local.transfer.airdrop_app

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest

private const val REPOSITORY = "Mrledinec/WDrop"
private const val MAX_APK_SIZE = 512L * 1024 * 1024
private val versionPattern = Regex("""v?(\d+)\.(\d+)\.(\d+)""")
private val digestPattern = Regex("sha256:([0-9a-fA-F]{64})")

internal class AppUpdate(private val context: Context) {
    private data class Release(val version: String, val url: String, val digest: String, val size: Long)

    private val packages = context.packageManager
    private val installed = packages.getPackageInfo(context.packageName, 0)
    val version = checkNotNull(installed.versionName)
    private var release: Release? = null

    @Synchronized
    fun check(): String? {
        release = null
        val data = connect("https://api.github.com/repos/$REPOSITORY/releases/latest") { connection ->
            connection.setRequestProperty("Accept", "application/vnd.github+json")
            require(connection.responseCode != HttpURLConnection.HTTP_NOT_FOUND) {
                "Репозиторий недоступен или в нём ещё нет опубликованных выпусков."
            }
            connection.requireSuccess()
            connection.inputStream.bufferedReader(Charsets.UTF_8).use { JSONObject(it.readText()) }
        }
        val tag = data.getString("tag_name")
        val target = versionParts(tag)
        val firstDifference = target.zip(versionParts(version)).firstOrNull { (next, current) -> next != current }
        if (firstDifference == null || firstDifference.first < firstDifference.second) return null

        val newVersion = target.joinToString(".")
        val name = "LocalTransfer-Android-$newVersion.apk"
        val url = "https://github.com/$REPOSITORY/releases/download/$tag/$name"
        val assets = data.getJSONArray("assets")
        val asset = (0 until assets.length()).asSequence().map(assets::getJSONObject)
            .firstOrNull { it.optString("name") == name }
        require(asset != null && asset.optString("browser_download_url").equals(url, ignoreCase = true)) {
            "В выпуске отсутствует установщик $name."
        }
        val digest = digestPattern.matchEntire(asset.optString("digest"))?.groupValues?.get(1)
            ?: error("GitHub не предоставил SHA-256 установщика.")
        val size = asset.optLong("size")
        require(size in 1..MAX_APK_SIZE) { "Недопустимый размер установщика." }
        release = Release(newVersion, url, digest.lowercase(), size)
        return newVersion
    }

    @Synchronized
    fun download(): File {
        val update = checkNotNull(release) { "Сначала проверьте наличие обновления." }
        val directory = File(context.cacheDir, "updates")
        check(directory.isDirectory || directory.mkdirs()) { "Не удалось создать папку для обновления." }
        val pending = File.createTempFile("download-", ".apk", directory)
        try {
            var received = 0L
            val digest = MessageDigest.getInstance("SHA-256")
            connect(update.url) { connection ->
                connection.requireSuccess()
                connection.inputStream.buffered().use { input ->
                    pending.outputStream().buffered().use { output ->
                        val buffer = ByteArray(256 * 1024)
                        while (true) {
                            val count = input.read(buffer)
                            if (count == -1) break
                            received += count
                            check(received <= update.size) { "Размер скачанного установщика превышает ожидаемый." }
                            digest.update(buffer, 0, count)
                            output.write(buffer, 0, count)
                        }
                    }
                }
            }
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            check(received == update.size && actual == update.digest) {
                "Размер или контрольная сумма установщика не совпали."
            }
            val apk = packages.getPackageArchiveInfo(pending.path, 0)
            check(apk?.packageName == context.packageName && apk.versionName == update.version &&
                  apk.longVersionCode > installed.longVersionCode) {
                "APK не соответствует приложению или версии обновления."
            }
            val verified = File(directory, "update.apk")
            Files.move(pending.toPath(), verified.toPath(), StandardCopyOption.REPLACE_EXISTING)
            return verified
        } finally {
            pending.delete()
        }
    }

    private fun versionParts(value: String): List<Int> {
        val match = versionPattern.matchEntire(value) ?: error("Версия должна иметь формат X.Y.Z.")
        return match.groupValues.drop(1).map { it.toInt() }
    }

    private fun HttpURLConnection.requireSuccess() {
        check(responseCode == HttpURLConnection.HTTP_OK) { "GitHub вернул ошибку HTTP $responseCode." }
    }

    private fun <T> connect(url: String, request: (HttpURLConnection) -> T): T {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = 12_000
        connection.readTimeout = 30_000
        connection.setRequestProperty("User-Agent", "LocalTransfer/$version")
        return try {
            request(connection)
        } finally {
            connection.disconnect()
        }
    }
}
