package com.napominator.notification

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import com.napominator.MainActivity
import com.napominator.NapominatorApp
import com.napominator.data.repository.TaskRepository
import dagger.hilt.android.qualifiers.ApplicationContext
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class DailySummaryBuilder @Inject constructor(
    @ApplicationContext private val context: Context,
    private val taskRepository: TaskRepository
) {

    companion object {
        const val NOTIFICATION_ID = Int.MAX_VALUE - 1
    }

    /**
     * Создаёт и показывает уведомление с утренней сводкой.
     */
    suspend fun showSummary() {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val now = System.currentTimeMillis()
        val todayEnd = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, 23)
            set(Calendar.MINUTE, 59)
            set(Calendar.SECOND, 59)
        }.timeInMillis

        val allActive = taskRepository.getActiveTasksOnce()
        val overdue = allActive.filter { it.reminderAt != null && it.reminderAt < now }
        val today = allActive.filter { it.reminderAt != null && it.reminderAt in now..todayEnd }
        val noDate = allActive.filter { it.reminderAt == null }

        val totalCount = overdue.size + today.size
        if (totalCount == 0 && noDate.isEmpty()) return

        val launchIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pi = PendingIntent.getActivity(
            context, 0, launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val sdf = SimpleDateFormat("HH:mm", Locale("ru"))
        val todayStr = SimpleDateFormat("d MMMM", Locale("ru")).format(Date())

        val shortText = buildString {
            if (overdue.isNotEmpty()) append("Просрочено: ${overdue.size}  ")
            if (today.isNotEmpty()) append("Сегодня: ${today.size}  ")
            if (noDate.isNotEmpty()) append("Без даты: ${noDate.size}")
        }.trim()

        val bigText = buildString {
            appendLine("📅 Сводка на $todayStr")
            if (overdue.isNotEmpty()) {
                appendLine()
                appendLine("🔴 Просроченные (${overdue.size}):")
                overdue.take(5).forEach { appendLine("• ${it.title}") }
                if (overdue.size > 5) appendLine("  … ещё ${overdue.size - 5}")
            }
            if (today.isNotEmpty()) {
                appendLine()
                appendLine("📌 Сегодня (${today.size}):")
                today.take(5).forEach { t ->
                    val time = if (t.reminderAt != null) " ${sdf.format(Date(t.reminderAt))}" else ""
                    appendLine("• ${t.title}$time")
                }
                if (today.size > 5) appendLine("  … ещё ${today.size - 5}")
            }
            if (noDate.isNotEmpty()) {
                appendLine()
                appendLine("📋 Без срока (${noDate.size}):")
                noDate.take(3).forEach { appendLine("• ${it.title}") }
                if (noDate.size > 3) appendLine("  … ещё ${noDate.size - 3}")
            }
        }.trim()

        val notification = Notification.Builder(context, NapominatorApp.CHANNEL_SUMMARY)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Напоминания на сегодня")
            .setContentText(shortText)
            .setStyle(Notification.BigTextStyle().bigText(bigText))
            .setContentIntent(pi)
            .setAutoCancel(true)
            .build()

        nm.notify(NOTIFICATION_ID, notification)
    }
}
