package com.napominator.alarm

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import com.napominator.domain.model.Task
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Планирует и отменяет будильники через AlarmManager.setAlarmClock().
 * Это единственный тип будильников, который Huawei не убивает в фоне.
 */
@Singleton
class AlarmScheduler @Inject constructor(
    @ApplicationContext private val context: Context
) {

    private val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager

    fun schedule(task: Task) {
        val reminderAt = task.reminderAt ?: return
        if (reminderAt <= System.currentTimeMillis()) return

        val pendingIntent = buildPendingIntent(task.id) ?: return

        val clockInfo = AlarmManager.AlarmClockInfo(
            reminderAt,
            buildLaunchIntent()  // intent для отображения в системных часах
        )
        alarmManager.setAlarmClock(clockInfo, pendingIntent)
    }

    fun scheduleAt(taskId: Long, triggerAt: Long) {
        if (triggerAt <= System.currentTimeMillis()) return
        val pendingIntent = buildPendingIntent(taskId) ?: return
        val clockInfo = AlarmManager.AlarmClockInfo(triggerAt, buildLaunchIntent())
        alarmManager.setAlarmClock(clockInfo, pendingIntent)
    }

    fun cancel(taskId: Long) {
        buildPendingIntent(taskId)?.let { alarmManager.cancel(it) }
    }

    fun canScheduleExactAlarms(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            alarmManager.canScheduleExactAlarms()
        } else {
            true
        }
    }

    private fun buildPendingIntent(taskId: Long): PendingIntent? {
        val intent = Intent(context, AlarmReceiver::class.java).apply {
            action = ACTION_ALARM
            putExtra(EXTRA_TASK_ID, taskId)
        }
        return PendingIntent.getBroadcast(
            context,
            taskId.toInt(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    private fun buildLaunchIntent(): PendingIntent {
        val intent = context.packageManager.getLaunchIntentForPackage(context.packageName)!!
        return PendingIntent.getActivity(
            context, 0, intent,
            PendingIntent.FLAG_IMMUTABLE
        )
    }

    companion object {
        const val ACTION_ALARM = "com.napominator.ACTION_ALARM"
        const val EXTRA_TASK_ID = "task_id"
    }
}
