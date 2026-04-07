package com.napominator.ui.reminder

import android.app.NotificationManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import com.napominator.alarm.AlarmScheduler
import com.napominator.data.prefs.AppPreferences
import com.napominator.data.repository.TaskRepository
import com.napominator.ui.theme.NapominatorTheme
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.util.Calendar
import javax.inject.Inject

/**
 * Прозрачная Activity, показывает bottom sheet с вариантами переноса задачи.
 * Запускается при нажатии на тело уведомления.
 */
@AndroidEntryPoint
class ReminderSheetActivity : ComponentActivity() {

    @Inject lateinit var taskRepository: TaskRepository
    @Inject lateinit var alarmScheduler: AlarmScheduler
    @Inject lateinit var prefs: AppPreferences

    companion object {
        const val EXTRA_TASK_ID = "task_id"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val taskId = intent.getLongExtra(EXTRA_TASK_ID, -1L)
        if (taskId == -1L) { finish(); return }

        // Убираем уведомление сразу при открытии
        val nm = getSystemService(NotificationManager::class.java)
        nm.cancel(taskId.toInt())

        setContent {
            NapominatorTheme {
                var visible by remember { mutableStateOf(true) }

                if (visible) {
                    SnoozeBottomSheet(
                        taskId = taskId,
                        onDismiss = { visible = false; finish() },
                        onOptionSelected = { action ->
                            handleAction(taskId, action)
                            visible = false
                            finish()
                        }
                    )
                }
            }
        }
    }

    private fun handleAction(taskId: Long, action: SnoozeAction) {
        lifecycleScope.launch {
            val morningMinutes = prefs.morningTime.first()
            val eveningMinutes = prefs.eveningTime.first()

            when (action) {
                SnoozeAction.Done -> {
                    taskRepository.markCompleted(taskId)
                    alarmScheduler.cancel(taskId)
                }
                SnoozeAction.In1Hour -> {
                    val newTime = System.currentTimeMillis() + 60 * 60_000L
                    taskRepository.reschedule(taskId, newTime)
                    alarmScheduler.scheduleAt(taskId, newTime)
                }
                SnoozeAction.In3Hours -> {
                    val newTime = System.currentTimeMillis() + 3 * 60 * 60_000L
                    taskRepository.reschedule(taskId, newTime)
                    alarmScheduler.scheduleAt(taskId, newTime)
                }
                SnoozeAction.ThisEvening -> {
                    val cal = Calendar.getInstance().apply {
                        set(Calendar.HOUR_OF_DAY, eveningMinutes / 60)
                        set(Calendar.MINUTE, eveningMinutes % 60)
                        set(Calendar.SECOND, 0)
                        set(Calendar.MILLISECOND, 0)
                    }
                    // Если вечер уже прошёл — ставим на завтра
                    if (cal.timeInMillis <= System.currentTimeMillis()) {
                        cal.add(Calendar.DAY_OF_YEAR, 1)
                    }
                    taskRepository.reschedule(taskId, cal.timeInMillis)
                    alarmScheduler.scheduleAt(taskId, cal.timeInMillis)
                }
                SnoozeAction.TomorrowMorning -> {
                    val cal = Calendar.getInstance().apply {
                        add(Calendar.DAY_OF_YEAR, 1)
                        set(Calendar.HOUR_OF_DAY, morningMinutes / 60)
                        set(Calendar.MINUTE, morningMinutes % 60)
                        set(Calendar.SECOND, 0)
                        set(Calendar.MILLISECOND, 0)
                    }
                    taskRepository.reschedule(taskId, cal.timeInMillis)
                    alarmScheduler.scheduleAt(taskId, cal.timeInMillis)
                }
            }
        }
    }
}

enum class SnoozeAction {
    Done, In1Hour, In3Hours, ThisEvening, TomorrowMorning
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SnoozeBottomSheet(
    taskId: Long,
    onDismiss: () -> Unit,
    onOptionSelected: (SnoozeAction) -> Unit
) {
    val sheetState = rememberModalBottomSheetState(skipPartialExpansion = true)

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 32.dp)
        ) {
            Text(
                text = "Что сделать с напоминанием?",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(horizontal = 24.dp, vertical = 8.dp)
            )

            SnoozeOption(Icons.Default.Check, "Выполнено") { onOptionSelected(SnoozeAction.Done) }
            SnoozeOption(Icons.Default.Alarm, "Через 1 час") { onOptionSelected(SnoozeAction.In1Hour) }
            SnoozeOption(Icons.Default.Schedule, "Через 3 часа") { onOptionSelected(SnoozeAction.In3Hours) }
            SnoozeOption(Icons.Default.WbSunny, "Сегодня вечером") { onOptionSelected(SnoozeAction.ThisEvening) }
            SnoozeOption(Icons.Default.Bedtime, "Завтра утром") { onOptionSelected(SnoozeAction.TomorrowMorning) }
        }
    }
}

@Composable
private fun SnoozeOption(icon: ImageVector, label: String, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Text(label, style = MaterialTheme.typography.bodyLarge)
        }
    }
}
