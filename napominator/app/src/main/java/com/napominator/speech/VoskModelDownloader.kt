package com.napominator.speech

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.util.zip.ZipInputStream
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.coroutineContext

/**
 * Скачивает и распаковывает модель Vosk для русского языка.
 *
 * Размер архива: ~50 МБ
 * Итоговая папка: [Context.filesDir]/vosk-model-small-ru/
 *
 * Использование:
 * ```
 * downloader.download().collect { progress ->
 *     when (progress) {
 *         is Progress.Downloading -> updateBar(progress.percent)
 *         is Progress.Extracting  -> showText("Распаковка…")
 *         is Progress.Done        -> startVosk(progress.modelDir)
 *         is Progress.Error       -> showError(progress.message)
 *     }
 * }
 * ```
 */
@Singleton
class VoskModelDownloader @Inject constructor(
    @ApplicationContext private val context: Context,
    private val okHttpClient: OkHttpClient
) {

    companion object {
        private const val MODEL_URL =
            "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
        // Реальное имя папки внутри архива
        private const val MODEL_DIR_NAME_IN_ZIP = "vosk-model-small-ru-0.22"
        // Имя под которым храним у себя
        private const val MODEL_DIR_NAME = "vosk-model-small-ru"
        private const val ZIP_TEMP_NAME = "vosk-model-small-ru.zip"
    }

    sealed class Progress {
        /** Процент загрузки (0–100), текущие байты и полный размер */
        data class Downloading(val percent: Int, val bytesLoaded: Long, val totalBytes: Long) : Progress()
        object Extracting : Progress()
        data class Done(val modelDir: File) : Progress()
        data class Error(val message: String) : Progress()
    }

    /** Директория с распакованной моделью. Не null только если модель уже установлена. */
    fun getInstalledModelDir(): File? {
        val dir = File(context.filesDir, MODEL_DIR_NAME)
        return if (dir.exists() && dir.isDirectory) dir else null
    }

    fun isModelInstalled(): Boolean = getInstalledModelDir() != null

    /**
     * Скачать и распаковать модель. Если модель уже есть — сразу эмитит [Progress.Done].
     * Поддерживает отмену через cancellation корутины.
     */
    fun download(): Flow<Progress> = flow {
        val modelDir = File(context.filesDir, MODEL_DIR_NAME)
        if (modelDir.exists()) {
            emit(Progress.Done(modelDir))
            return@flow
        }

        val zipFile = File(context.cacheDir, ZIP_TEMP_NAME)

        // ── 1. Загрузка ───────────────────────────────────────────────────────
        try {
            val request = Request.Builder().url(MODEL_URL).build()
            val response = okHttpClient.newCall(request).execute()

            if (!response.isSuccessful) {
                emit(Progress.Error("Ошибка загрузки: HTTP ${response.code}"))
                return@flow
            }

            val body = response.body ?: run {
                emit(Progress.Error("Пустой ответ сервера"))
                return@flow
            }

            val totalBytes = body.contentLength()
            var bytesRead = 0L

            FileOutputStream(zipFile).use { fos ->
                body.byteStream().use { input ->
                    val buf = ByteArray(8 * 1024)
                    while (coroutineContext.isActive) {
                        val count = input.read(buf)
                        if (count == -1) break
                        fos.write(buf, 0, count)
                        bytesRead += count
                        val percent = if (totalBytes > 0) (bytesRead * 100 / totalBytes).toInt() else 0
                        emit(Progress.Downloading(percent, bytesRead, totalBytes))
                    }
                }
            }
        } catch (e: Exception) {
            zipFile.delete()
            emit(Progress.Error("Ошибка загрузки: ${e.message}"))
            return@flow
        }

        // ── 2. Распаковка ─────────────────────────────────────────────────────
        emit(Progress.Extracting)
        try {
            unzip(zipFile, context.filesDir)
            zipFile.delete()
        } catch (e: Exception) {
            zipFile.delete()
            modelDir.deleteRecursively()
            emit(Progress.Error("Ошибка распаковки: ${e.message}"))
            return@flow
        }

        // Архив распаковывается в папку с версией (vosk-model-small-ru-0.22),
        // переименовываем в стандартное имя (vosk-model-small-ru)
        val extractedDir = File(context.filesDir, MODEL_DIR_NAME_IN_ZIP)
        if (extractedDir.exists() && !modelDir.exists()) {
            extractedDir.renameTo(modelDir)
        }

        if (modelDir.exists()) {
            emit(Progress.Done(modelDir))
        } else {
            // Ищем любую папку vosk в filesDir как запасной вариант
            val anyVoskDir = context.filesDir.listFiles()
                ?.firstOrNull { it.isDirectory && it.name.startsWith("vosk-model") }
            if (anyVoskDir != null) {
                anyVoskDir.renameTo(modelDir)
                emit(Progress.Done(modelDir))
            } else {
                emit(Progress.Error("Папка модели не найдена после распаковки"))
            }
        }
    }.flowOn(Dispatchers.IO)

    private fun unzip(zipFile: File, destDir: File) {
        ZipInputStream(zipFile.inputStream().buffered()).use { zis ->
            var entry = zis.nextEntry
            while (entry != null) {
                val outFile = File(destDir, entry.name)
                if (entry.isDirectory) {
                    outFile.mkdirs()
                } else {
                    outFile.parentFile?.mkdirs()
                    FileOutputStream(outFile).use { fos ->
                        zis.copyTo(fos)
                    }
                }
                zis.closeEntry()
                entry = zis.nextEntry
            }
        }
    }

    /** Удалить установленную модель (для сброса / повторной загрузки) */
    suspend fun deleteModel() = withContext(Dispatchers.IO) {
        File(context.filesDir, MODEL_DIR_NAME).deleteRecursively()
    }
}
