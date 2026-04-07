package com.napominator.ui.settings

import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.napominator.ui.backup.BackupState
import com.napominator.ui.backup.BackupViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel(),
    backupViewModel: BackupViewModel = hiltViewModel()
) {
    val context = LocalContext.current

    val quietEnabled by viewModel.quietHoursEnabled.collectAsStateWithLifecycle()
    val quietStart by viewModel.quietHoursStart.collectAsStateWithLifecycle()
    val quietEnd by viewModel.quietHoursEnd.collectAsStateWithLifecycle()
    val snoozeInterval by viewModel.snoozeInterval.collectAsStateWithLifecycle()
    val snoozeMax by viewModel.snoozeMax.collectAsStateWithLifecycle()
    val morningTime by viewModel.morningTime.collectAsStateWithLifecycle()
    val eveningTime by viewModel.eveningTime.collectAsStateWithLifecycle()
    val confirmTimer by viewModel.confirmTimer.collectAsStateWithLifecycle()
    val recordMode by viewModel.recordModeToggle.collectAsStateWithLifecycle()
    val asrEngine by viewModel.asrEngine.collectAsStateWithLifecycle()
    val summaryEnabled by viewModel.dailySummaryEnabled.collectAsStateWithLifecycle()
    val summaryTime by viewModel.dailySummaryTime.collectAsStateWithLifecycle()

    val backupState by backupViewModel.state.collectAsStateWithLifecycle()

    // File pickers
    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/json")
    ) { uri: Uri? -> uri?.let { backupViewModel.export(it) } }

    val importLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? -> uri?.let { backupViewModel.import(it) } }

    // Показываем результат бэкапа через Snackbar
    val snackbarHostState = remember { SnackbarHostState() }
    LaunchedEffect(backupState) {
        when (val s = backupState) {
            is BackupState.ExportSuccess -> {
                snackbarHostState.showSnackbar("Экспортировано задач: ${s.count}")
                backupViewModel.resetState()
            }
            is BackupState.ImportSuccess -> {
                snackbarHostState.showSnackbar("Импортировано: ${s.imported}, пропущено: ${s.skipped}")
                backupViewModel.resetState()
            }
            is BackupState.Error -> {
                snackbarHostState.showSnackbar("Ошибка: ${s.message}")
                backupViewModel.resetState()
            }
            else -> {}
        }
    }

    // Диалоги
    var showQuietStartPicker by remember { mutableStateOf(false) }
    var showQuietEndPicker by remember { mutableStateOf(false) }
    var showSummaryTimePicker by remember { mutableStateOf(false) }
    var showMorningPicker by remember { mutableStateOf(false) }
    var showEveningPicker by remember { mutableStateOf(false) }
    var showConfirmTimerDialog by remember { mutableStateOf(false) }
    var showSnoozeDialog by remember { mutableStateOf(false) }
    var showDeleteConfirm by remember { mutableStateOf(false) }

    if (showQuietStartPicker) {
        TimePickerDialog(
            title = "Начало тихих часов",
            currentMinutes = quietStart,
            onConfirm = { viewModel.setQuietHours(it, quietEnd); showQuietStartPicker = false },
            onDismiss = { showQuietStartPicker = false }
        )
    }
    if (showQuietEndPicker) {
        TimePickerDialog(
            title = "Конец тихих часов",
            currentMinutes = quietEnd,
            onConfirm = { viewModel.setQuietHours(quietStart, it); showQuietEndPicker = false },
            onDismiss = { showQuietEndPicker = false }
        )
    }
    if (showSummaryTimePicker) {
        TimePickerDialog(
            title = "Время сводки",
            currentMinutes = summaryTime,
            onConfirm = { viewModel.setDailySummary(summaryEnabled, it); showSummaryTimePicker = false },
            onDismiss = { showSummaryTimePicker = false }
        )
    }
    if (showMorningPicker) {
        TimePickerDialog(
            title = "Время «Утром»",
            currentMinutes = morningTime,
            onConfirm = { viewModel.setMorningTime(it); showMorningPicker = false },
            onDismiss = { showMorningPicker = false }
        )
    }
    if (showEveningPicker) {
        TimePickerDialog(
            title = "Время «Вечером»",
            currentMinutes = eveningTime,
            onConfirm = { viewModel.setEveningTime(it); showEveningPicker = false },
            onDismiss = { showEveningPicker = false }
        )
    }
    if (showConfirmTimerDialog) {
        NumberPickerDialog(
            title = "Таймер подтверждения",
            unit = "сек",
            current = confirmTimer,
            range = 3..30,
            onConfirm = { viewModel.setConfirmTimer(it); showConfirmTimerDialog = false },
            onDismiss = { showConfirmTimerDialog = false }
        )
    }
    if (showSnoozeDialog) {
        SnoozeSettingsDialog(
            currentInterval = snoozeInterval,
            currentMax = snoozeMax,
            onConfirm = { interval, max -> viewModel.setSnooze(interval, max); showSnoozeDialog = false },
            onDismiss = { showSnoozeDialog = false }
        )
    }
    if (showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = false },
            title = { Text("Удалить выполненные?") },
            text = { Text("Все выполненные задачи будут удалены без возможности восстановления.") },
            confirmButton = {
                TextButton(onClick = { viewModel.deleteCompleted(); showDeleteConfirm = false }) {
                    Text("Удалить", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteConfirm = false }) { Text("Отмена") }
            }
        )
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        topBar = {
            TopAppBar(
                title = { Text("Настройки") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Назад")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
        ) {

            // ── Напоминания ──────────────────────────────────────────────────
            SectionHeader("Напоминания")

            SettingsRow(
                label = "Тихие часы",
                description = if (quietEnabled) "${formatMinutes(quietStart)} – ${formatMinutes(quietEnd)}" else "Выкл",
                trailing = {
                    Switch(checked = quietEnabled, onCheckedChange = { viewModel.setQuietHoursEnabled(it) })
                }
            )
            if (quietEnabled) {
                SettingsRow(
                    label = "Начало",
                    description = formatMinutes(quietStart),
                    onClick = { showQuietStartPicker = true }
                )
                SettingsRow(
                    label = "Конец",
                    description = formatMinutes(quietEnd),
                    onClick = { showQuietEndPicker = true }
                )
            }
            SettingsRow(
                label = "Повторять напоминание",
                description = if (snoozeInterval == 0) "Выкл" else "каждые $snoozeInterval мин, макс $snoozeMax раз",
                onClick = { showSnoozeDialog = true }
            )

            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

            // ── Голос ────────────────────────────────────────────────────────
            SectionHeader("Голос и запись")

            SettingsRow(
                label = "Таймер подтверждения",
                description = "$confirmTimer сек",
                onClick = { showConfirmTimerDialog = true }
            )
            SettingsRow(
                label = "Режим записи",
                description = if (recordMode) "Нажать для старта/стопа" else "Удерживать",
                trailing = {
                    Switch(checked = recordMode, onCheckedChange = { viewModel.setRecordMode(it) })
                }
            )
            SettingsRow(
                label = "Движок распознавания",
                description = when (asrEngine) { "vosk" -> "Только офлайн (Vosk)"; else -> "Авто (онлайн/офлайн)" },
                trailing = {
                    Switch(
                        checked = asrEngine == "vosk",
                        onCheckedChange = { viewModel.setAsrEngine(if (it) "vosk" else "auto") }
                    )
                }
            )

            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

            // ── Сводка дня ───────────────────────────────────────────────────
            SectionHeader("Сводка дня")

            SettingsRow(
                label = "Утренняя сводка",
                description = if (summaryEnabled) "В ${formatMinutes(summaryTime)}" else "Выкл",
                trailing = {
                    Switch(
                        checked = summaryEnabled,
                        onCheckedChange = { viewModel.setDailySummary(it, summaryTime) }
                    )
                }
            )
            if (summaryEnabled) {
                SettingsRow(
                    label = "Время сводки",
                    description = formatMinutes(summaryTime),
                    onClick = { showSummaryTimePicker = true }
                )
            }

            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

            // ── Время переноса ───────────────────────────────────────────────
            SectionHeader("Быстрый перенос")

            SettingsRow(
                label = "«Утром» означает",
                description = formatMinutes(morningTime),
                onClick = { showMorningPicker = true }
            )
            SettingsRow(
                label = "«Вечером» означает",
                description = formatMinutes(eveningTime),
                onClick = { showEveningPicker = true }
            )

            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

            // ── Данные ───────────────────────────────────────────────────────
            SectionHeader("Данные")

            SettingsRow(
                label = "Экспортировать задачи",
                description = "Сохранить все задачи в JSON-файл",
                onClick = {
                    exportLauncher.launch("napominator_backup.json")
                }
            )
            SettingsRow(
                label = "Импортировать задачи",
                description = "Загрузить задачи из JSON-файла",
                onClick = {
                    importLauncher.launch(arrayOf("application/json", "text/plain", "*/*"))
                }
            )
            SettingsRow(
                label = "Очистить выполненные",
                description = "Удалить все выполненные задачи",
                onClick = { showDeleteConfirm = true }
            )

            if (backupState is BackupState.InProgress) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp))
            }

            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

            // ── Батарея Huawei ───────────────────────────────────────────────
            SectionHeader("Батарея (Huawei)")

            val pm = remember { context.getSystemService(PowerManager::class.java) }
            val isIgnoring = remember(pm) { pm?.isIgnoringBatteryOptimizations(context.packageName) == true }

            SettingsRow(
                label = "Оптимизация батареи",
                description = if (isIgnoring) "Отключена ✓ (рекомендуется)" else "Включена — могут пропускаться напоминания",
                onClick = if (!isIgnoring) {
                    {
                        val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                            data = Uri.parse("package:${context.packageName}")
                        }
                        context.startActivity(intent)
                    }
                } else null
            )

            Spacer(Modifier.height(16.dp))
        }
    }
}

@Composable
private fun SectionHeader(title: String) {
    Text(
        text = title,
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.primary,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
    )
}

@Composable
private fun SettingsRow(
    label: String,
    description: String,
    onClick: (() -> Unit)? = null,
    trailing: @Composable (() -> Unit)? = null
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodyLarge)
            Text(
                description,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        if (trailing != null) {
            Spacer(Modifier.width(8.dp))
            trailing()
        }
    }
}

@Composable
private fun TimePickerDialog(
    title: String,
    currentMinutes: Int,
    onConfirm: (Int) -> Unit,
    onDismiss: () -> Unit
) {
    var hour by remember { mutableIntStateOf(currentMinutes / 60) }
    var minute by remember { mutableIntStateOf(currentMinutes % 60) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = "%02d".format(hour),
                    onValueChange = { hour = it.toIntOrNull()?.coerceIn(0, 23) ?: hour },
                    label = { Text("Час") },
                    modifier = Modifier.weight(1f),
                    singleLine = true
                )
                OutlinedTextField(
                    value = "%02d".format(minute),
                    onValueChange = { minute = it.toIntOrNull()?.coerceIn(0, 59) ?: minute },
                    label = { Text("Мин") },
                    modifier = Modifier.weight(1f),
                    singleLine = true
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(hour * 60 + minute) }) { Text("Готово") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Отмена") }
        }
    )
}

@Composable
private fun NumberPickerDialog(
    title: String,
    unit: String,
    current: Int,
    range: IntRange,
    onConfirm: (Int) -> Unit,
    onDismiss: () -> Unit
) {
    var value by remember { mutableIntStateOf(current) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            OutlinedTextField(
                value = value.toString(),
                onValueChange = { value = it.toIntOrNull()?.coerceIn(range.first, range.last) ?: value },
                label = { Text(unit) },
                singleLine = true
            )
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(value) }) { Text("Готово") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Отмена") }
        }
    )
}

@Composable
private fun SnoozeSettingsDialog(
    currentInterval: Int,
    currentMax: Int,
    onConfirm: (Int, Int) -> Unit,
    onDismiss: () -> Unit
) {
    var interval by remember { mutableIntStateOf(currentInterval) }
    var max by remember { mutableIntStateOf(currentMax) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Повторять напоминание") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = interval.toString(),
                    onValueChange = { interval = it.toIntOrNull()?.coerceIn(0, 120) ?: interval },
                    label = { Text("Интервал (мин, 0 = выкл)") },
                    singleLine = true
                )
                OutlinedTextField(
                    value = max.toString(),
                    onValueChange = { max = it.toIntOrNull()?.coerceIn(0, 50) ?: max },
                    label = { Text("Макс. повторов (0 = без ограничений)") },
                    singleLine = true
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(interval, max) }) { Text("Готово") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Отмена") }
        }
    )
}

private fun formatMinutes(minutes: Int): String =
    "%02d:%02d".format(minutes / 60, minutes % 60)
