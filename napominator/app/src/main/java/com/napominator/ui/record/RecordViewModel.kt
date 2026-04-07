package com.napominator.ui.record

import android.Manifest
import android.app.Application
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.napominator.audio.AudioRecorder
import com.napominator.nlp.NlpParser
import com.napominator.speech.SpeechRecognitionManager
import com.napominator.speech.VoskModelDownloader
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

sealed class RecordUiState {
    object Idle : RecordUiState()
    data class Recording(val seconds: Int) : RecordUiState()
    object Processing : RecordUiState()
    data class Error(val message: String) : RecordUiState()
    data class Recognized(val parsed: NlpParser.ParsedTask) : RecordUiState()
    /** Скачивание модели Vosk */
    data class DownloadingModel(val percent: Int, val bytesLoaded: Long, val totalBytes: Long) : RecordUiState()
}

@HiltViewModel
class RecordViewModel @Inject constructor(
    application: Application,
    private val audioRecorder: AudioRecorder,
    private val speechManager: SpeechRecognitionManager,
    private val nlpParser: NlpParser,
    private val modelDownloader: VoskModelDownloader
) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow<RecordUiState>(RecordUiState.Idle)
    val uiState: StateFlow<RecordUiState> = _uiState.asStateFlow()

    val amplitude = audioRecorder.amplitude

    private var currentFile: File? = null
    private var secondsJob: Job? = null

    init {
        // Автоматически скачиваем модель если не установлена
        if (!modelDownloader.isModelInstalled()) {
            downloadModel()
        }
    }

    fun hasMicPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            getApplication(), Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
    }

    fun downloadModel() {
        viewModelScope.launch {
            modelDownloader.download().collect { progress ->
                when (progress) {
                    is VoskModelDownloader.Progress.Downloading -> {
                        _uiState.value = RecordUiState.DownloadingModel(
                            percent = progress.percent,
                            bytesLoaded = progress.bytesLoaded,
                            totalBytes = progress.totalBytes
                        )
                    }
                    is VoskModelDownloader.Progress.Extracting -> {
                        _uiState.value = RecordUiState.DownloadingModel(100, 0, 0)
                    }
                    is VoskModelDownloader.Progress.Done -> {
                        _uiState.value = RecordUiState.Idle
                    }
                    is VoskModelDownloader.Progress.Error -> {
                        _uiState.value = RecordUiState.Error(
                            "Не удалось скачать модель: ${progress.message}\nПроверьте подключение к интернету."
                        )
                    }
                }
            }
        }
    }

    fun startRecording() {
        if (_uiState.value is RecordUiState.Recording) return
        currentFile = audioRecorder.startRecording()
        if (currentFile == null) {
            _uiState.value = RecordUiState.Error("Не удалось начать запись")
            return
        }
        _uiState.value = RecordUiState.Recording(0)
        secondsJob = viewModelScope.launch {
            var secs = 0
            while (true) {
                delay(1000)
                secs++
                if (_uiState.value is RecordUiState.Recording) {
                    _uiState.value = RecordUiState.Recording(secs)
                } else break
            }
        }
    }

    fun stopRecording() {
        secondsJob?.cancel()
        secondsJob = null
        viewModelScope.launch {
            val file = audioRecorder.stopRecording()
            if (file == null) {
                _uiState.value = RecordUiState.Idle
                return@launch
            }
            _uiState.value = RecordUiState.Processing
            when (val result = speechManager.recognize(file)) {
                is SpeechRecognitionManager.Result.Success -> {
                    val parsed = nlpParser.parse(result.text)
                    _uiState.value = RecordUiState.Recognized(parsed)
                }
                is SpeechRecognitionManager.Result.Empty -> {
                    _uiState.value = RecordUiState.Error("Ничего не распознано. Попробуйте ещё раз.")
                }
                is SpeechRecognitionManager.Result.Error -> {
                    _uiState.value = RecordUiState.Error(result.message)
                }
                SpeechRecognitionManager.Result.ModelNotInstalled -> {
                    downloadModel()
                }
            }
        }
    }

    fun cancelRecording() {
        secondsJob?.cancel()
        secondsJob = null
        audioRecorder.cancelRecording()
        _uiState.value = RecordUiState.Idle
    }

    fun resetToIdle() {
        _uiState.value = RecordUiState.Idle
    }

    fun saveTextInput(text: String) {
        if (text.isBlank()) return
        val parsed = nlpParser.parse(text)
        _uiState.value = RecordUiState.Recognized(parsed)
    }

    override fun onCleared() {
        super.onCleared()
        audioRecorder.cancelRecording()
    }
}
