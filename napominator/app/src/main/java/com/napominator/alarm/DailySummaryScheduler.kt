package com.napominator.alarm

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import com.napominator.data.prefs.AppPreferences
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.first
import java.util.Calendar
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Планирует ежедневную утреннюю сводку через AlarmManager.setAlarmClock().
 */
@Singleton
class DailySummaryScheduler @Inject constructor(
    @ApplicationContext private val context: Context,
    private val prefs: AppPreferences
) {

    private val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager

    companion object {
        const val ACTION_DAILY_SUMMARY = "com.napominator.ACTION_DAILY_SUMMARY"
        private const val REQUEST_CODE = Int.MAX_VALUE
    }

    /**
     * Планирует следующую сводку. Если время сегодня ещё не прошло — сегодня,
     * иначе — завтра.
     */
    suspend fun scheduleNext() {
        if (!prefs.dailySummaryEnabled.first()) {
            cancel()
            return
        }
        val timeMinutes = prefs.dailySummaryTime.first()
        val hour = timeMinutes / 60
        val minute = timeMinutes % 60

        val cal = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, hour)
            set(Calendar.MINUTE, minute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        if (cal.timeInMillis <= System.currentTimeMillis()) {
            cal.add(Calendar.DAY_OF_YEAR, 1)
        }

        val pi = buildPendingIntent()
        val launchPi = buildLaunchIntent()
        alarmManager.setAlarmClock(
            AlarmManager.AlarmClockInfo(cal.timeInMillis, launchPi),
            pi
        )
    }

    fun cancel() {
        alarmManager.cancel(buildPendingIntent())
    }

    private fun buildPendingIntent(): PendingIntent {
        val intent = Intent(context, DailySummaryReceiver::class.java).apply {
            action = ACTION_DAILY_SUMMARY
        }
        return PendingIntent.getBroadcast(
            context, REQUEST_CODE, intent,
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
}
