package com.napominator.notification

import android.app.Notification
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import com.napominator.NapominatorApp
import com.napominator.domain.model.Task
import dagger.hilt.android.qualifiers.ApplicationContext
import java.text.SimpleDateFormat
import java.util.*
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Строит уведомления-напоминания.
 * Максимум 3 action-кнопки (ограничение Android).
 */
@Singleton
class NotificationBuilder @Inject constructor(
    @ApplicationContext private val context: Context
) {

    /**
     * Строит уведомление для задачи.
     * Кнопки: [Выполнено] [Через 1 час] [Завтра утром]
     * Для геозадач: [Выполнено] [Через 1 час] [У места]
     */
    fun buildReminder(task: Task): Notification {
        val doneIntent = actionIntent(NotificationActionReceiver.ACTION_DONE, task.id)
        val snooze1hIntent = actionIntent(NotificationActionReceiver.ACTION_SNOOZE_1H, task.id)
        val snoozeTomorrowIntent = actionIntent(NotificationActionReceiver.ACTION_SNOOZE_TOMORROW, task.id)

        val subtitle = buildSubtitle(task)

        return NotificationCompat.Builder(context, NapominatorApp.CHANNEL_REMINDER)
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle(task.title)
            .setContentText(subtitle)
            .setStyle(
                NotificationCompat.BigTextStyle()
                    .bigText(task.title)
                    .setSummaryText(subtitle)
            )
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setAutoCancel(false)
            .setOngoing(false)
            .setContentIntent(buildOpenIntent(task.id))
            // Кнопка 1: Выполнено
            .addAction(
                android.R.drawable.checkbox_on_background,
                "Выполнено",
                doneIntent
            )
            // Кнопка 2: Через 1 час
            .addAction(
                android.R.drawable.ic_lock_idle_clock,
                "Через 1 час",
                snooze1hIntent
            )
            // Кнопка 3: Завтра утром
            .addAction(
                android.R.drawable.ic_menu_today,
                "Завтра утром",
                snoozeTomorrowIntent
            )
            .build()
    }

    private fun buildSubtitle(task: Task): String {
        val parts = mutableListOf<String>()
        task.reminderAt?.let {
            parts.add(SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(it)))
        }
        if (task.rrule != null) parts.add("повтор")
        if (task.hasGeofence) parts.add("у места")
        return parts.joinToString(" · ").ifEmpty { "Напоминание" }
    }

    private fun actionIntent(action: String, taskId: Long): PendingIntent {
        val intent = Intent(context, NotificationActionReceiver::class.java).apply {
            this.action = action
            putExtra(NotificationActionReceiver.EXTRA_TASK_ID, taskId)
        }
        return PendingIntent.getBroadcast(
            context,
            (taskId * 100 + action.hashCode()).toInt(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    private fun buildOpenIntent(taskId: Long): PendingIntent {
        val intent = context.packageManager.getLaunchIntentForPackage(context.packageName)!!
        return PendingIntent.getActivity(
            context,
            taskId.toInt(),
            intent,
            PendingIntent.FLAG_IMMUTABLE
        )
    }
}
