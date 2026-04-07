package com.napominator.notification

import android.app.NotificationManager
import android.content.Context
import com.napominator.data.prefs.AppPreferences
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.first
import java.util.Calendar
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Проверяет, находится ли текущий момент в тихих часах.
 * Тихие часы настраиваются в AppPreferences (quietHoursStart, quietHoursEnd).
 * Корректно обрабатывает диапазоны через полночь (например 23:00–07:00).
 */
@Singleton
class QuietHoursManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val prefs: AppPreferences
) {

    /**
     * Возвращает true если сейчас тихие часы.
     */
    suspend fun isQuietNow(): Boolean {
        if (!prefs.quietHoursEnabled.first()) return false

        val startMin = prefs.quietHoursStart.first()  // минуты с начала суток, напр. 1380 = 23:00
        val endMin = prefs.quietHoursEnd.first()       // напр. 420 = 07:00

        val now = Calendar.getInstance()
        val nowMin = now.get(Calendar.HOUR_OF_DAY) * 60 + now.get(Calendar.MINUTE)

        return if (startMin <= endMin) {
            // Обычный диапазон: 08:00–22:00
            nowMin in startMin..endMin
        } else {
            // Через полночь: 23:00–07:00
            nowMin >= startMin || nowMin <= endMin
        }
    }

    /**
     * Время (Unix timestamp мс) когда заканчиваются тихие часы.
     * Используется для планирования повтора уведомления.
     */
    suspend fun quietHoursEndTime(): Long {
        val endMin = prefs.quietHoursEnd.first()
        val cal = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, endMin / 60)
            set(Calendar.MINUTE, endMin % 60)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        // Если конец тихих часов уже прошёл сегодня — берём завтра
        if (cal.timeInMillis <= System.currentTimeMillis()) {
            cal.add(Calendar.DAY_OF_YEAR, 1)
        }
        return cal.timeInMillis
    }

    /**
     * Проверяет системный Do Not Disturb.
     */
    fun isSystemDndActive(): Boolean {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        return nm.currentInterruptionFilter != NotificationManager.INTERRUPTION_FILTER_ALL
    }

    /**
     * Суммарная проверка: тихие часы ИЛИ системный DND.
     */
    suspend fun shouldSuppressNotification(): Boolean =
        isQuietNow() || isSystemDndActive()
}
