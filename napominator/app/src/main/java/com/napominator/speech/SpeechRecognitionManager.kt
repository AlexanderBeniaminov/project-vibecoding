package com.napominator.speech

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Единый менеджер распознавания речи.
 *
 * Стратегия выбора движка:
 * 1. Если есть интернет → HMS ML Kit Speech (онлайн, выше качество)
 * 2. Если нет интернета → Vosk (офлайн)
 * 3. Если HMS недоступен (нет agconnect-services.json) → Vosk
 *
 * HMS-интеграция включается автоматически когда будет добавлен HmsRecognizer.
 */
@Singleton
class SpeechRecognitionManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val voskRecognizer: VoskRecognizer,
    // hmsRecognizer подключается позже (требует agconnect-services.json)
) {

    sealed class Result {
        data class Success(val text: String, val engine: Engine) : Result()
        object Empty : Result()
        data class Error(val message: String) : Result()
        object ModelNotInstalled : Result()
    }

    enum class Engine { HMS, VOSK }

    /**
     * Распознать речь из WAV-файла.
     * Автоматически выбирает движок.
     */
    suspend fun recognize(wavFile: File): Result {
        // TODO (задача 2.2): подключить HMS когда будет agconnect-services.json
        // if (isOnline() && hmsRecognizer.isAvailable()) {
        //     return when (val r = hmsRecognizer.recognize(wavFile)) {
        //         is HmsRecognizer.Result.Success -> Result.Success(r.text, Engine.HMS)
        //         else -> fallbackToVosk(wavFile)
        //     }
        // }
        return recognizeWithVosk(wavFile)
    }

    private suspend fun recognizeWithVosk(wavFile: File): Result {
        return when (val r = voskRecognizer.recognize(wavFile)) {
            is VoskRecognizer.Result.Success -> Result.Success(r.text, Engine.VOSK)
            is VoskRecognizer.Result.Empty -> Result.Empty
            is VoskRecognizer.Result.Error -> Result.Error(r.message)
            VoskRecognizer.Result.ModelNotInstalled -> Result.ModelNotInstalled
        }
    }

    fun isOnline(): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    fun release() {
        voskRecognizer.release()
    }
}
