package com.napominator.audio

import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.File
import java.io.FileOutputStream
import java.io.RandomAccessFile
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Пишет микрофон в WAV-файл.
 * Поддерживает два режима:
 *  - Hold   : startRecording() при нажатии, stopRecording() при отпускании
 *  - Toggle : startRecording() при первом касании, stopRecording() при втором
 *
 * Амплитуда [amplitude] обновляется в реальном времени — используется для визуализации.
 */
@Singleton
class AudioRecorder @Inject constructor(
    @ApplicationContext private val context: Context
) {

    companion object {
        private const val SAMPLE_RATE = 16_000    // 16 kHz — оптимально для ASR
        private const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
    }

    sealed class State {
        object Idle : State()
        object Recording : State()
        object Stopping : State()
        data class Error(val message: String) : State()
    }

    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state.asStateFlow()

    /** Текущий уровень амплитуды (0.0–1.0) для визуализации */
    private val _amplitude = MutableStateFlow(0f)
    val amplitude: StateFlow<Float> = _amplitude.asStateFlow()

    private var audioRecord: AudioRecord? = null
    private var recordingJob: Job? = null
    private var outputFile: File? = null

    /**
     * Начать запись.
     * @return File — файл, куда пишется WAV (запись ещё идёт, файл не завершён)
     */
    fun startRecording(): File? {
        if (_state.value is State.Recording) return outputFile

        val bufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT)
        if (bufferSize == AudioRecord.ERROR_BAD_VALUE || bufferSize == AudioRecord.ERROR) {
            _state.value = State.Error("Не удалось инициализировать аудиозапись")
            return null
        }

        val file = File(context.cacheDir, "recording_${System.currentTimeMillis()}.wav")
        outputFile = file

        try {
            val recorder = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE,
                CHANNEL_CONFIG,
                AUDIO_FORMAT,
                bufferSize * 2
            )
            audioRecord = recorder
            recorder.startRecording()
            _state.value = State.Recording

            recordingJob = CoroutineScope(Dispatchers.IO).launch {
                writePcmToWav(recorder, file, bufferSize)
            }
        } catch (e: SecurityException) {
            _state.value = State.Error("Нет разрешения на запись микрофона")
            return null
        } catch (e: Exception) {
            _state.value = State.Error("Ошибка: ${e.message}")
            return null
        }

        return file
    }

    /**
     * Остановить запись.
     * @return File — готовый WAV-файл или null если не было записи
     */
    suspend fun stopRecording(): File? {
        if (_state.value !is State.Recording) return null
        _state.value = State.Stopping

        audioRecord?.apply {
            stop()
            release()
        }
        audioRecord = null
        recordingJob?.join()
        recordingJob = null
        _amplitude.value = 0f
        _state.value = State.Idle

        return outputFile
    }

    fun cancelRecording() {
        audioRecord?.apply {
            stop()
            release()
        }
        audioRecord = null
        recordingJob?.cancel()
        recordingJob = null
        outputFile?.delete()
        outputFile = null
        _amplitude.value = 0f
        _state.value = State.Idle
    }

    // ── Запись PCM + формирование WAV-заголовка ───────────────────────────────

    private suspend fun writePcmToWav(
        recorder: AudioRecord,
        file: File,
        bufferSize: Int
    ) {
        val buffer = ShortArray(bufferSize)
        FileOutputStream(file).use { fos ->
            // Оставляем место под WAV-заголовок (44 байта)
            fos.write(ByteArray(44))

            var totalSamples = 0L
            while (_state.value == State.Recording) {
                val read = recorder.read(buffer, 0, bufferSize)
                if (read > 0) {
                    // Амплитуда: среднеквадратичное значение нормированное до 0-1
                    val rms = Math.sqrt(
                        buffer.take(read).sumOf { it.toLong() * it }.toDouble() / read
                    ).toFloat()
                    _amplitude.value = (rms / 32768f).coerceIn(0f, 1f)

                    // Пишем PCM как little-endian bytes
                    val bytes = ByteArray(read * 2)
                    for (i in 0 until read) {
                        bytes[i * 2] = (buffer[i].toInt() and 0xFF).toByte()
                        bytes[i * 2 + 1] = (buffer[i].toInt() shr 8 and 0xFF).toByte()
                    }
                    fos.write(bytes)
                    totalSamples += read
                }
            }

            val dataSize = totalSamples * 2  // 16 bit = 2 байта на семпл
            writeWavHeader(file, dataSize)
        }
    }

    /** Записывает 44-байтовый WAV-заголовок в начало уже записанного файла */
    private fun writeWavHeader(file: File, dataSize: Long) {
        RandomAccessFile(file, "rw").use { raf ->
            raf.seek(0)
            val totalSize = dataSize + 36
            raf.write("RIFF".toByteArray())
            raf.write(intToLittleEndian(totalSize.toInt()))
            raf.write("WAVE".toByteArray())
            raf.write("fmt ".toByteArray())
            raf.write(intToLittleEndian(16))          // chunk size
            raf.write(shortToLittleEndian(1))          // PCM format
            raf.write(shortToLittleEndian(1))          // mono
            raf.write(intToLittleEndian(SAMPLE_RATE))
            raf.write(intToLittleEndian(SAMPLE_RATE * 2))  // byte rate
            raf.write(shortToLittleEndian(2))          // block align
            raf.write(shortToLittleEndian(16))         // bits per sample
            raf.write("data".toByteArray())
            raf.write(intToLittleEndian(dataSize.toInt()))
        }
    }

    private fun intToLittleEndian(v: Int) = byteArrayOf(
        (v and 0xFF).toByte(),
        (v shr 8 and 0xFF).toByte(),
        (v shr 16 and 0xFF).toByte(),
        (v shr 24 and 0xFF).toByte()
    )

    private fun shortToLittleEndian(v: Int) = byteArrayOf(
        (v and 0xFF).toByte(),
        (v shr 8 and 0xFF).toByte()
    )
}
