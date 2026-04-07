package com.napominator.ui.task

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskDetailScreen(
    taskId: Long,
    onBack: () -> Unit,
    viewModel: TaskDetailViewModel = hiltViewModel()
) {
    LaunchedEffect(taskId) { viewModel.load(taskId) }

    val state by viewModel.uiState.collectAsStateWithLifecycle()
    var showDeleteDialog by remember { mutableStateOf(false) }
    var showDatePicker by remember { mutableStateOf(false) }
    var showRrulePicker by remember { mutableStateOf(false) }

    LaunchedEffect(state.isSaved, state.isDeleted) {
        if (state.isSaved || state.isDeleted) onBack()
    }

    if (showDeleteDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = false },
            title = { Text("Удалить задачу?") },
            confirmButton = {
                TextButton(onClick = { showDeleteDialog = false; viewModel.delete() }) {
                    Text("Удалить", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = false }) { Text("Отмена") }
            }
        )
    }

    if (showDatePicker) {
        DatePickerDialog(
            currentTs = state.task?.reminderAt,
            onConfirm = { viewModel.updateReminderAt(it); showDatePicker = false },
            onDismiss = { showDatePicker = false }
        )
    }

    if (showRrulePicker) {
        RrulePickerDialog(
            current = state.task?.rrule,
            onConfirm = { viewModel.updateRrule(it); showRrulePicker = false },
            onDismiss = { showRrulePicker = false }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Редактировать задачу") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Назад")
                    }
                },
                actions = {
                    IconButton(onClick = { showDeleteDialog = true }) {
                        Icon(Icons.Default.Delete, "Удалить", tint = MaterialTheme.colorScheme.error)
                    }
                }
            )
        }
    ) { padding ->
        if (state.isLoading || state.task == null) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = androidx.compose.ui.Alignment.Center) {
                CircularProgressIndicator()
            }
            return@Scaffold
        }

        val task = state.task!!

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Заголовок
            OutlinedTextField(
                value = task.title,
                onValueChange = { viewModel.updateTitle(it) },
                label = { Text("Задача") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2
            )

            // Дата и время
            OutlinedCard(
                onClick = { showDatePicker = true },
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier.padding(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Icon(Icons.Default.Schedule, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Column {
                        Text("Дата и время", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(
                            text = if (task.reminderAt != null)
                                SimpleDateFormat("d MMMM yyyy, HH:mm", Locale("ru")).format(Date(task.reminderAt))
                            else "Не задано",
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
            }

            // Повторение
            OutlinedCard(
                onClick = { showRrulePicker = true },
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier.padding(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Icon(Icons.Default.Repeat, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Column {
                        Text("Повторение", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(
                            text = formatRrule(task.rrule),
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
            }

            Spacer(Modifier.height(8.dp))

            // Кнопки
            Button(
                onClick = { viewModel.save() },
                modifier = Modifier.fillMaxWidth(),
                enabled = task.title.isNotBlank()
            ) {
                Text("Сохранить")
            }

            if (!task.isCompleted) {
                OutlinedButton(
                    onClick = { viewModel.markCompleted() },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Icon(Icons.Default.Check, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("Отметить выполненной")
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DatePickerDialog(
    currentTs: Long?,
    onConfirm: (Long?) -> Unit,
    onDismiss: () -> Unit
) {
    val state = rememberDatePickerState(
        initialSelectedDateMillis = currentTs ?: System.currentTimeMillis()
    )
    var timeHour by remember { mutableIntStateOf(
        if (currentTs != null) Calendar.getInstance().apply { timeInMillis = currentTs }.get(Calendar.HOUR_OF_DAY) else 9
    ) }
    var timeMinute by remember { mutableIntStateOf(
        if (currentTs != null) Calendar.getInstance().apply { timeInMillis = currentTs }.get(Calendar.MINUTE) else 0
    ) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Дата и время") },
        text = {
            Column {
                DatePicker(state = state, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = "%02d".format(timeHour),
                        onValueChange = { timeHour = it.toIntOrNull()?.coerceIn(0, 23) ?: timeHour },
                        label = { Text("Час") },
                        modifier = Modifier.weight(1f),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = "%02d".format(timeMinute),
                        onValueChange = { timeMinute = it.toIntOrNull()?.coerceIn(0, 59) ?: timeMinute },
                        label = { Text("Мин") },
                        modifier = Modifier.weight(1f),
                        singleLine = true
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val dateMs = state.selectedDateMillis ?: System.currentTimeMillis()
                val cal = Calendar.getInstance().apply {
                    timeInMillis = dateMs
                    set(Calendar.HOUR_OF_DAY, timeHour)
                    set(Calendar.MINUTE, timeMinute)
                    set(Calendar.SECOND, 0)
                }
                onConfirm(cal.timeInMillis)
            }) { Text("Готово") }
        },
        dismissButton = {
            TextButton(onClick = { onConfirm(null) }) { Text("Без даты") }
        }
    )
}

@Composable
private fun RrulePickerDialog(
    current: String?,
    onConfirm: (String?) -> Unit,
    onDismiss: () -> Unit
) {
    val options = listOf(
        null to "Не повторять",
        "FREQ=DAILY" to "Каждый день",
        "FREQ=WEEKLY" to "Каждую неделю",
        "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR" to "По будням",
        "FREQ=WEEKLY;BYDAY=SA,SU" to "По выходным",
        "FREQ=MONTHLY" to "Каждый месяц",
        "FREQ=YEARLY" to "Каждый год"
    )
    var selected by remember { mutableStateOf(current) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Повторение") },
        text = {
            Column {
                options.forEach { (value, label) ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp),
                        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                    ) {
                        RadioButton(selected = selected == value, onClick = { selected = value })
                        Spacer(Modifier.width(8.dp))
                        Text(label)
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(selected) }) { Text("Готово") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Отмена") }
        }
    )
}

private fun formatRrule(rrule: String?): String = when (rrule) {
    null -> "Не повторять"
    "FREQ=DAILY" -> "Каждый день"
    "FREQ=WEEKLY" -> "Каждую неделю"
    "FREQ=MONTHLY" -> "Каждый месяц"
    "FREQ=YEARLY" -> "Каждый год"
    "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR" -> "По будням"
    "FREQ=WEEKLY;BYDAY=SA,SU" -> "По выходным"
    else -> rrule
}
