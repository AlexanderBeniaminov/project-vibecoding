package com.napominator.notification

import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.napominator.alarm.AlarmScheduler
import com.napominator.data.repository.TaskRepository
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.util.*
import javax.inject.Inject

/**
 * Обрабатывает нажатия на кнопки в уведомлении.
 * Работает без открытия приложения.
 */
@AndroidEntryPoint
class NotificationActionReceiver : BroadcastReceiver() {

    @Inject lateinit var taskRepository: TaskRepository
    @Inject lateinit var alarmScheduler: AlarmScheduler

    override fun onReceive(context: Context, intent: Intent) {
        val taskId = intent.getLongExtra(EXTRA_TASK_ID, -1L)
        if (taskId == -1L) return

        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                when (intent.action) {
                    ACTION_DONE -> {
                        taskRepository.markCompleted(taskId)
                        alarmScheduler.cancel(taskId)
                        nm.cancel(taskId.toInt())
                    }

                    ACTION_SNOOZE_1H -> {
                        val newTime = System.currentTimeMillis() + 60 * 60 * 1000L
                        taskRepository.reschedule(taskId, newTime)
                        val task = taskRepository.getById(taskId)
                        if (task != null) alarmScheduler.schedule(task)
                        nm.cancel(taskId.toInt())
                    }

                    ACTION_SNOOZE_TOMORROW -> {
                        val cal = Calendar.getInstance().apply {
                            add(Calendar.DAY_OF_YEAR, 1)
                            set(Calendar.HOUR_OF_DAY, 9)
                            set(Calendar.MINUTE, 0)
                            set(Calendar.SECOND, 0)
                            set(Calendar.MILLISECOND, 0)
                        }
                        taskRepository.reschedule(taskId, cal.timeInMillis)
                        val task = taskRepository.getById(taskId)
                        if (task != null) alarmScheduler.schedule(task)
                        nm.cancel(taskId.toInt())
                    }
                }
            } finally {
                pendingResult.finish()
            }
        }
    }

    companion object {
        const val EXTRA_TASK_ID = "task_id"
        const val ACTION_DONE = "com.napominator.ACTION_DONE"
        const val ACTION_SNOOZE_1H = "com.napominator.ACTION_SNOOZE_1H"
        const val ACTION_SNOOZE_TOMORROW = "com.napominator.ACTION_SNOOZE_TOMORROW"
    }
}
