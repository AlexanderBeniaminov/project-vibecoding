package com.napominator.ui.task

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.napominator.alarm.AlarmScheduler
import com.napominator.data.repository.TaskRepository
import com.napominator.domain.model.Task
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class TaskDetailUiState(
    val task: Task? = null,
    val isLoading: Boolean = true,
    val isSaved: Boolean = false,
    val isDeleted: Boolean = false
)

@HiltViewModel
class TaskDetailViewModel @Inject constructor(
    private val taskRepository: TaskRepository,
    private val alarmScheduler: AlarmScheduler
) : ViewModel() {

    private val _uiState = MutableStateFlow(TaskDetailUiState())
    val uiState: StateFlow<TaskDetailUiState> = _uiState.asStateFlow()

    fun load(taskId: Long) {
        viewModelScope.launch {
            val task = taskRepository.getById(taskId)
            _uiState.value = TaskDetailUiState(task = task, isLoading = false)
        }
    }

    fun updateTitle(title: String) {
        _uiState.value = _uiState.value.copy(task = _uiState.value.task?.copy(title = title))
    }

    fun updateReminderAt(ts: Long?) {
        _uiState.value = _uiState.value.copy(task = _uiState.value.task?.copy(reminderAt = ts))
    }

    fun updateRrule(rrule: String?) {
        _uiState.value = _uiState.value.copy(task = _uiState.value.task?.copy(rrule = rrule))
    }

    fun save() {
        val task = _uiState.value.task ?: return
        viewModelScope.launch {
            taskRepository.update(task)
            // Перепланируем будильник
            alarmScheduler.cancel(task.id)
            if (task.reminderAt != null && task.reminderAt > System.currentTimeMillis()) {
                alarmScheduler.schedule(task)
            }
            _uiState.value = _uiState.value.copy(isSaved = true)
        }
    }

    fun delete() {
        val task = _uiState.value.task ?: return
        viewModelScope.launch {
            alarmScheduler.cancel(task.id)
            taskRepository.deleteById(task.id)
            _uiState.value = _uiState.value.copy(isDeleted = true)
        }
    }

    fun markCompleted() {
        val task = _uiState.value.task ?: return
        viewModelScope.launch {
            taskRepository.markCompleted(task.id)
            alarmScheduler.cancel(task.id)
            _uiState.value = _uiState.value.copy(isSaved = true)
        }
    }
}
