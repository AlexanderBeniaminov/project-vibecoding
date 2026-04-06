package com.napominator.ui.confirm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.napominator.alarm.AlarmScheduler
import com.napominator.data.repository.TaskRepository
import com.napominator.domain.model.Task
import com.napominator.nlp.NlpParser
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ConfirmUiState(
    val title: String = "",
    val reminderAt: Long? = null,
    val rrule: String? = null,
    val hasNoTime: Boolean = false,
    val timerSeconds: Int = TIMER_DURATION,
    val timerRunning: Boolean = true,
    val saved: Boolean = false
) {
    companion object {
        const val TIMER_DURATION = 8
    }
}

@HiltViewModel
class ConfirmViewModel @Inject constructor(
    private val taskRepository: TaskRepository,
    private val alarmScheduler: AlarmScheduler
) : ViewModel() {

    private val _uiState = MutableStateFlow(ConfirmUiState())
    val uiState: StateFlow<ConfirmUiState> = _uiState.asStateFlow()

    private var timerJob: Job? = null

    fun init(parsed: NlpParser.ParsedTask) {
        _uiState.value = ConfirmUiState(
            title = parsed.title,
            reminderAt = parsed.reminderAt,
            rrule = parsed.rrule,
            hasNoTime = parsed.hasNoTime,
            timerSeconds = ConfirmUiState.TIMER_DURATION,
            timerRunning = true
        )
        startTimer()
    }

    private fun startTimer() {
        timerJob?.cancel()
        timerJob = viewModelScope.launch {
            while (_uiState.value.timerSeconds > 0 && _uiState.value.timerRunning) {
                delay(1000)
                val current = _uiState.value.timerSeconds
                if (current <= 1) {
                    saveTask()
                    return@launch
                }
                _uiState.value = _uiState.value.copy(timerSeconds = current - 1)
            }
        }
    }

    /** Пользователь коснулся поля — останавливаем таймер */
    fun stopTimer() {
        timerJob?.cancel()
        _uiState.value = _uiState.value.copy(timerRunning = false, timerSeconds = 0)
    }

    fun updateTitle(title: String) {
        stopTimer()
        _uiState.value = _uiState.value.copy(title = title)
    }

    fun updateReminderAt(ts: Long?) {
        stopTimer()
        _uiState.value = _uiState.value.copy(
            reminderAt = ts,
            hasNoTime = ts == null
        )
    }

    fun updateRrule(rrule: String?) {
        stopTimer()
        _uiState.value = _uiState.value.copy(rrule = rrule)
    }

    fun saveTask() {
        val state = _uiState.value
        if (state.saved) return
        timerJob?.cancel()
        _uiState.value = state.copy(saved = true, timerRunning = false)

        viewModelScope.launch {
            val task = Task(
                id = 0,
                title = state.title.ifBlank { "Без названия" },
                createdAt = System.currentTimeMillis(),
                reminderAt = state.reminderAt,
                rrule = state.rrule
            )
            val savedId = taskRepository.insert(task)
            // Планируем будильник если есть время напоминания
            if (state.reminderAt != null) {
                alarmScheduler.schedule(task.copy(id = savedId))
            }
        }
    }
}
