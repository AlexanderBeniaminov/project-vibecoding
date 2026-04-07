package com.napominator.ui.main

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.napominator.data.repository.TaskRepository
import com.napominator.domain.model.Task
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.util.Calendar
import javax.inject.Inject

data class MainUiState(
    val sections: List<TaskSection> = emptyList(),
    val isLoading: Boolean = true,
    val searchQuery: String = "",
    val deletedTask: Task? = null   // для Snackbar "Отменить"
)

data class TaskSection(
    val title: String,
    val tasks: List<Task>,
    val isCollapsible: Boolean = false,
    val isOverdue: Boolean = false
)

@HiltViewModel
class MainViewModel @Inject constructor(
    private val taskRepository: TaskRepository
) : ViewModel() {

    private val _searchQuery = MutableStateFlow("")
    private val _deletedTask = MutableStateFlow<Task?>(null)

    val uiState: StateFlow<MainUiState> = combine(
        taskRepository.getActiveTasks(),
        _searchQuery,
        _deletedTask
    ) { tasks, query, deleted ->
        val filtered = if (query.isBlank()) tasks
        else tasks.filter { it.title.contains(query, ignoreCase = true) }

        MainUiState(
            sections = buildSections(filtered),
            isLoading = false,
            searchQuery = query,
            deletedTask = deleted
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = MainUiState()
    )

    fun completeTask(id: Long) {
        viewModelScope.launch { taskRepository.markCompleted(id) }
    }

    fun deleteTask(task: Task) {
        viewModelScope.launch {
            taskRepository.deleteById(task.id)
            _deletedTask.value = task
        }
    }

    fun undoDelete() {
        val task = _deletedTask.value ?: return
        viewModelScope.launch {
            taskRepository.insert(task)
            _deletedTask.value = null
        }
    }

    fun clearDeletedTask() {
        _deletedTask.value = null
    }

    fun setSearchQuery(query: String) {
        _searchQuery.value = query
    }

    private fun buildSections(tasks: List<Task>): List<TaskSection> {
        val now = System.currentTimeMillis()
        val cal = Calendar.getInstance()

        fun startOfDay(offset: Int): Long {
            return Calendar.getInstance().apply {
                add(Calendar.DAY_OF_YEAR, offset)
                set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0)
                set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
            }.timeInMillis
        }

        val todayStart = startOfDay(0)
        val tomorrowStart = startOfDay(1)
        val weekEnd = startOfDay(7)

        val overdue = tasks.filter { it.reminderAt != null && it.reminderAt < todayStart }
        val today = tasks.filter { it.reminderAt != null && it.reminderAt in todayStart until tomorrowStart }
        val tomorrow = tasks.filter { it.reminderAt != null && it.reminderAt in tomorrowStart until startOfDay(2) }
        val thisWeek = tasks.filter { it.reminderAt != null && it.reminderAt in startOfDay(2) until weekEnd }
        val later = tasks.filter { it.reminderAt != null && it.reminderAt >= weekEnd }
        val noTime = tasks.filter { it.reminderAt == null }

        val sections = mutableListOf<TaskSection>()
        if (overdue.isNotEmpty()) sections.add(TaskSection("Просроченные", overdue, isCollapsible = true, isOverdue = true))
        if (today.isNotEmpty()) sections.add(TaskSection("Сегодня", today))
        if (tomorrow.isNotEmpty()) sections.add(TaskSection("Завтра", tomorrow))
        if (thisWeek.isNotEmpty()) sections.add(TaskSection("На этой неделе", thisWeek))
        if (later.isNotEmpty()) sections.add(TaskSection("Позже", later))
        if (noTime.isNotEmpty()) sections.add(TaskSection("Без даты", noTime))
        return sections
    }
}
