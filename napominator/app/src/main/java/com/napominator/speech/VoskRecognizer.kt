package com.napominator.speech

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import java.io.File
import java.io.FileInputStream
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Офлайн-распознавание речи через Vosk.
 *
 * Инициализируется лениво при первом вызове [recognize].
 * Перед использованием модель должна быть загружена [VoskModelDownloader].
 */
@Singleton
class VoskRecognizer @Inject constructor(
    @ApplicationContext private val context: Context,
    private val modelDownloader: VoskModelDownloader
) {

    private var model: Model? = null

    sealed class Result {
        data class Success(val text: String) : Result()
        object Empty : Result()
        data class Error(val message: String) : Result()
        object ModelNotInstalled : Result()
    }

    /**
     * Распознать речь из WAV-файла.
     * Блокирующая операция — вызывать в IO-диспатчере.
     *
     * @param wavFile WAV-файл (16 kHz, mono, PCM 16-bit)
     */
    suspend fun recognize(wavFile: File): Result = withContext(Dispatchers.IO) {
        val modelDir = modelDownloader.getInstalledModelDir()
            ?: return@withContext Result.ModelNotInstalled

        try {
            if (model == null) {
                model = Model(modelDir.absolutePath)
            }

            Recognizer(model, 16_000f).use { recognizer ->
                FileInputStream(wavFile).use { fis ->
                    // Пропускаем WAV-заголовок (44 байта)
                    fis.skip(44)

                    val buffer = ByteArray(4096)
                    while (true) {
                        val bytesRead = fis.read(buffer)
                        if (bytesRead == -1) break
                        recognizer.acceptWaveForm(buffer, bytesRead)
                    }
                }

                val finalResultJson = recognizer.finalResult
                val text = JSONObject(finalResultJson).optString("text", "").trim()

                if (text.isEmpty()) Result.Empty else Result.Success(text)
            }
        } catch (e: Exception) {
            Result.Error("Ошибка Vosk: ${e.message}")
        }
    }

    /**
     * Освободить ресурсы модели из памяти.
     * Вызывать когда приложение уходит в фон и распознавание не нужно.
     */
    fun release() {
        model?.close()
        model = null
    }
}
