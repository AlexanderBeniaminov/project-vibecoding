package com.napominator.ui.backup

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.napominator.data.backup.BackupManager
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed class BackupState {
    object Idle : BackupState()
    object InProgress : BackupState()
    data class ExportSuccess(val count: Int) : BackupState()
    data class ImportSuccess(val imported: Int, val skipped: Int) : BackupState()
    data class Error(val message: String) : BackupState()
}

@HiltViewModel
class BackupViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val backupManager: BackupManager
) : ViewModel() {

    private val _state = MutableStateFlow<BackupState>(BackupState.Idle)
    val state: StateFlow<BackupState> = _state.asStateFlow()

    fun export(uri: Uri) {
        _state.value = BackupState.InProgress
        viewModelScope.launch {
            try {
                val stream = context.contentResolver.openOutputStream(uri)
                    ?: throw Exception("Не удалось открыть файл для записи")
                val count = backupManager.exportToJson(stream)
                _state.value = BackupState.ExportSuccess(count)
            } catch (e: Exception) {
                _state.value = BackupState.Error(e.message ?: "Ошибка экспорта")
            }
        }
    }

    fun import(uri: Uri) {
        _state.value = BackupState.InProgress
        viewModelScope.launch {
            try {
                val stream = context.contentResolver.openInputStream(uri)
                    ?: throw Exception("Не удалось открыть файл")
                val result = backupManager.importFromJson(stream)
                _state.value = when (result) {
                    is BackupManager.ImportResult.Success ->
                        BackupState.ImportSuccess(result.imported, result.skipped)
                    is BackupManager.ImportResult.Error ->
                        BackupState.Error(result.message)
                }
            } catch (e: Exception) {
                _state.value = BackupState.Error(e.message ?: "Ошибка импорта")
            }
        }
    }

    fun resetState() { _state.value = BackupState.Idle }
}
