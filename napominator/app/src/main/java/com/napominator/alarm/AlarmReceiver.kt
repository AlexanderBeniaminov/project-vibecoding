package com.napominator.alarm

import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.napominator.data.repository.TaskRepository
import com.napominator.notification.NotificationBuilder
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Получает будильник от AlarmManager → показывает уведомление.
 */
@AndroidEntryPoint
class AlarmReceiver : BroadcastReceiver() {

    @Inject lateinit var taskRepository: TaskRepository
    @Inject lateinit var notificationBuilder: NotificationBuilder
    @Inject lateinit var alarmScheduler: AlarmScheduler

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != AlarmScheduler.ACTION_ALARM) return

        val taskId = intent.getLongExtra(AlarmScheduler.EXTRA_TASK_ID, -1L)
        if (taskId == -1L) return

        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val task = taskRepository.getById(taskId) ?: return@launch
                if (task.isCompleted) return@launch

                val notification = notificationBuilder.buildReminder(task)
                val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                nm.notify(taskId.toInt(), notification)

                // Если задача повторяющаяся — планируем следующее срабатывание
                if (task.isRepeating) {
                    val nextTime = calcNextOccurrence(task.reminderAt ?: return@launch, task.rrule!!)
                    if (nextTime != null) {
                        taskRepository.reschedule(taskId, nextTime)
                        alarmScheduler.schedule(task.copy(reminderAt = nextTime))
                    }
                }
            } finally {
                pendingResult.finish()
            }
        }
    }

    /**
     * Вычисляет следующую дату срабатывания по RRULE.
     * Упрощённая реализация для основных паттернов.
     */
    private fun calcNextOccurrence(currentTs: Long, rrule: String): Long? {
        val cal = java.util.Calendar.getInstance().apply { timeInMillis = currentTs }
        return when {
            rrule == "FREQ=DAILY" -> {
                cal.add(java.util.Calendar.DAY_OF_YEAR, 1)
                cal.timeInMillis
            }
            rrule == "FREQ=WEEKLY" -> {
                cal.add(java.util.Calendar.WEEK_OF_YEAR, 1)
                cal.timeInMillis
            }
            rrule == "FREQ=MONTHLY" -> {
                cal.add(java.util.Calendar.MONTH, 1)
                cal.timeInMillis
            }
            rrule == "FREQ=YEARLY" -> {
                cal.add(java.util.Calendar.YEAR, 1)
                cal.timeInMillis
            }
            rrule.startsWith("FREQ=DAILY;INTERVAL=") -> {
                val interval = rrule.removePrefix("FREQ=DAILY;INTERVAL=").toIntOrNull() ?: 1
                cal.add(java.util.Calendar.DAY_OF_YEAR, interval)
                cal.timeInMillis
            }
            rrule.startsWith("FREQ=WEEKLY;INTERVAL=") -> {
                val interval = rrule.removePrefix("FREQ=WEEKLY;INTERVAL=").toIntOrNull() ?: 1
                cal.add(java.util.Calendar.WEEK_OF_YEAR, interval)
                cal.timeInMillis
            }
            rrule.startsWith("FREQ=WEEKLY;BYDAY=") -> {
                cal.add(java.util.Calendar.WEEK_OF_YEAR, 1)
                cal.timeInMillis
            }
            rrule == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR" -> {
                // По будням — следующий рабочий день
                cal.add(java.util.Calendar.DAY_OF_YEAR, 1)
                while (cal.get(java.util.Calendar.DAY_OF_WEEK) in listOf(
                    java.util.Calendar.SATURDAY, java.util.Calendar.SUNDAY)) {
                    cal.add(java.util.Calendar.DAY_OF_YEAR, 1)
                }
                cal.timeInMillis
            }
            else -> null
        }
    }
}
