package com.napominator.ui.main

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.napominator.data.repository.TaskRepository
import com.napominator.domain.model.Task
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

data class MainUiState(
    val tasks: List<Task> = emptyList(),
    val isLoading: Boolean = true,
    val searchQuery: String = ""
)

@HiltViewModel
class MainViewModel @Inject constructor(
    private val taskRepository: TaskRepository
) : ViewModel() {

    private val _searchQuery = MutableStateFlow("")

    val uiState: StateFlow<MainUiState> = combine(
        taskRepository.getActiveTasks(),
        _searchQuery
    ) { tasks, query ->
        val filtered = if (query.isBlank()) tasks
        else tasks.filter { it.title.contains(query, ignoreCase = true) }
        MainUiState(tasks = filtered, isLoading = false, searchQuery = query)
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = MainUiState()
    )

    fun completeTask(id: Long) {
        viewModelScope.launch {
            taskRepository.markCompleted(id)
        }
    }

    fun deleteTask(id: Long) {
        viewModelScope.launch {
            taskRepository.deleteById(id)
        }
    }

    fun setSearchQuery(query: String) {
        _searchQuery.value = query
    }
}
