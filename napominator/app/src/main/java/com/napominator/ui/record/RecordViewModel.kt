package com.napominator.ui.record

import android.Manifest
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.napominator.audio.AudioRecorder
import com.napominator.nlp.NlpParser
import com.napominator.speech.SpeechRecognitionManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject
import android.app.Application
import androidx.lifecycle.AndroidViewModel

sealed class RecordUiState {
    object Idle : RecordUiState()
    data class Recording(val seconds: Int) : RecordUiState()
    object Processing : RecordUiState()
    data class Error(val message: String) : RecordUiState()
    data class Recognized(val parsed: NlpParser.ParsedTask) : RecordUiState()
}

@HiltViewModel
class RecordViewModel @Inject constructor(
    application: Application,
    private val audioRecorder: AudioRecorder,
    private val speechManager: SpeechRecognitionManager,
    private val nlpParser: NlpParser
) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow<RecordUiState>(RecordUiState.Idle)
    val uiState: StateFlow<RecordUiState> = _uiState.asStateFlow()

    val amplitude = audioRecorder.amplitude

    private var currentFile: File? = null
    private var secondsJob: kotlinx.coroutines.Job? = null

    fun hasMicPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            getApplication(), Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
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
                kotlinx.coroutines.delay(1000)
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
                    _uiState.value = RecordUiState.Error(
                        "Офлайн-модель не установлена. Подключитесь к интернету для первой записи."
                    )
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
