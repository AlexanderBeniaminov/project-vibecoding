package com.napominator.alarm

import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.napominator.data.repository.TaskRepository
import com.napominator.notification.NotificationBuilder
import com.napominator.notification.QuietHoursManager
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Получает будильник от AlarmManager → показывает уведомление.
 * Учитывает тихие часы и настойчивые повторы.
 */
@AndroidEntryPoint
class AlarmReceiver : BroadcastReceiver() {

    @Inject lateinit var taskRepository: TaskRepository
    @Inject lateinit var notificationBuilder: NotificationBuilder
    @Inject lateinit var alarmScheduler: AlarmScheduler
    @Inject lateinit var quietHoursManager: QuietHoursManager
    @Inject lateinit var rRuleScheduler: RRuleScheduler

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != AlarmScheduler.ACTION_ALARM) return
        val taskId = intent.getLongExtra(AlarmScheduler.EXTRA_TASK_ID, -1L)
        if (taskId == -1L) return

        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val task = taskRepository.getById(taskId) ?: return@launch
                if (task.isCompleted) return@launch

                val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                val suppress = quietHoursManager.shouldSuppressNotification()

                if (suppress) {
                    // Тихие часы — откладываем до конца тихих часов
                    val resumeAt = quietHoursManager.quietHoursEndTime()
                    alarmScheduler.scheduleAt(taskId, resumeAt)
                    return@launch
                }

                // Показываем уведомление
                nm.notify(taskId.toInt(), notificationBuilder.buildReminder(task))
                taskRepository.incrementSnoozeCount(taskId)

                // Планируем следующее повторение если нужно
                val snoozeInterval = task.snoozeIntervalMinutes
                val snoozeMax = task.snoozeMaxCount
                val snoozeCurrent = task.snoozeCurrentCount + 1

                if (snoozeInterval != null) {
                    val withinLimit = snoozeMax == null || snoozeCurrent < snoozeMax
                    if (withinLimit) {
                        val nextTime = System.currentTimeMillis() + snoozeInterval * 60_000L
                        alarmScheduler.scheduleAt(taskId, nextTime)
                    }
                }

                // Для повторяющихся задач планируем следующее вхождение по RRULE
                if (task.isRepeating && task.reminderAt != null) {
                    val nextTime = rRuleScheduler.nextOccurrence(task.reminderAt, task.rrule!!)
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

}
