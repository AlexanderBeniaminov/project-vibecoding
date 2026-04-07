package com.napominator.ui.confirm

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.napominator.nlp.NlpParser
import com.napominator.ui.util.rememberHapticFeedback
import java.text.SimpleDateFormat
import java.util.*

/**
 * Экран подтверждения задачи.
 * Показывает распознанный текст + дату/время/повторение.
 * Через 8 секунд автоматически сохраняет.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConfirmScreen(
    parsed: NlpParser.ParsedTask,
    onBack: () -> Unit,       // → вернуться к записи
    onSaved: () -> Unit,      // → задача сохранена, закрыть
    viewModel: ConfirmViewModel = hiltViewModel()
) {
    LaunchedEffect(parsed) {
        viewModel.init(parsed)
    }

    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val haptic = rememberHapticFeedback()

    LaunchedEffect(state.saved) {
        if (state.saved) {
            haptic.success()
            onSaved()
        }
    }

    val timerProgress by animateFloatAsState(
        targetValue = if (state.timerSeconds > 0)
            state.timerSeconds.toFloat() / ConfirmUiState.TIMER_DURATION
        else 0f,
        label = "timer"
    )

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Проверьте задачу") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад к записи")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Spacer(Modifier.height(8.dp))

            // Таймер автосохранения
            if (state.timerRunning) {
                TimerBar(seconds = state.timerSeconds, progress = timerProgress)
            }

            // Поле заголовка — касание останавливает таймер
            OutlinedTextField(
                value = state.title,
                onValueChange = { viewModel.updateTitle(it) },
                label = { Text("Задача") },
                modifier = Modifier
                    .fillMaxWidth()
                    .onFocusChanged { if (it.isFocused) viewModel.stopTimer() },
                minLines = 2
            )

            // Сообщение "без времени"
            if (state.hasNoTime) {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.tertiaryContainer
                    )
                ) {
                    Text(
                        text = "Без времени задача сохранится как заметка без напоминания",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onTertiaryContainer,
                        modifier = Modifier.padding(12.dp)
                    )
                }
            }

            // Дата и время
            val reminderAt = state.reminderAt
            if (reminderAt != null) {
                InfoRow(
                    label = "Когда",
                    value = formatTimestamp(reminderAt)
                )
            }

            // Повторение
            val rrule = state.rrule
            if (rrule != null) {
                InfoRow(
                    label = "Повтор",
                    value = formatRrule(rrule)
                )
            }

            Spacer(Modifier.weight(1f))

            // Кнопки
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                OutlinedButton(
                    onClick = onBack,
                    modifier = Modifier.weight(1f)
                ) {
                    Icon(Icons.Default.Mic, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("Перезаписать")
                }
                Button(
                    onClick = { haptic.click(); viewModel.saveTask() },
                    modifier = Modifier.weight(1f),
                    enabled = state.title.isNotBlank()
                ) {
                    Text("Сохранить")
                }
            }
            Spacer(Modifier.height(16.dp))
        }
    }
}

@Composable
private fun TimerBar(seconds: Int, progress: Float) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "Сохранится автоматически через $seconds с",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                text = "$seconds",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary
            )
        }
        Spacer(Modifier.height(4.dp))
        LinearProgressIndicator(
            progress = { progress },
            modifier = Modifier.fillMaxWidth()
        )
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface
        )
    }
}

private fun formatTimestamp(ts: Long): String {
    val sdf = SimpleDateFormat("d MMMM, HH:mm", Locale("ru"))
    return sdf.format(Date(ts))
}

private fun formatRrule(rrule: String): String = when {
    rrule == "FREQ=DAILY" -> "Каждый день"
    rrule == "FREQ=WEEKLY" -> "Каждую неделю"
    rrule == "FREQ=MONTHLY" -> "Каждый месяц"
    rrule == "FREQ=YEARLY" -> "Каждый год"
    rrule == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR" -> "По будням"
    rrule == "FREQ=WEEKLY;BYDAY=SA,SU" -> "По выходным"
    rrule.startsWith("FREQ=WEEKLY;BYDAY=") -> {
        val days = rrule.removePrefix("FREQ=WEEKLY;BYDAY=").split(",").joinToString(", ") {
            when (it) {
                "MO" -> "пн"; "TU" -> "вт"; "WE" -> "ср"
                "TH" -> "чт"; "FR" -> "пт"; "SA" -> "сб"; "SU" -> "вс"
                else -> it
            }
        }
        "Каждую неделю: $days"
    }
    rrule.startsWith("FREQ=DAILY;INTERVAL=") -> {
        val n = rrule.removePrefix("FREQ=DAILY;INTERVAL=")
        "Каждые $n дня"
    }
    rrule.startsWith("FREQ=MONTHLY;BYMONTHDAY=") -> {
        val day = rrule.removePrefix("FREQ=MONTHLY;BYMONTHDAY=")
        if (day == "-1") "Каждый последний день месяца" else "Каждый месяц $day-го"
    }
    else -> rrule
}

