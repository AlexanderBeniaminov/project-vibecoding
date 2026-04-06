package com.napominator.data.prefs

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "napominator_prefs")

@Singleton
class AppPreferences @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val store = context.dataStore

    // ── Ключи ──────────────────────────────────────────────────────────────

    private object Keys {
        val QUIET_HOURS_ENABLED = booleanPreferencesKey("quiet_hours_enabled")
        val QUIET_HOURS_START = intPreferencesKey("quiet_hours_start")   // минуты с 00:00
        val QUIET_HOURS_END = intPreferencesKey("quiet_hours_end")       // минуты с 00:00
        val EVENING_TIME = intPreferencesKey("evening_time")             // минуты с 00:00
        val MORNING_TIME = intPreferencesKey("morning_time")             // минуты с 00:00
        val CONFIRM_TIMER_SECONDS = intPreferencesKey("confirm_timer_sec")
        val RECORD_MODE_TOGGLE = booleanPreferencesKey("record_mode_toggle") // true = toggle, false = hold
        val DEFAULT_SNOOZE_INTERVAL = intPreferencesKey("default_snooze_interval") // минуты, 0 = выкл
        val DEFAULT_SNOOZE_MAX = intPreferencesKey("default_snooze_max")           // 0 = без ограничений
        val DAILY_SUMMARY_ENABLED = booleanPreferencesKey("daily_summary_enabled")
        val DAILY_SUMMARY_TIME = intPreferencesKey("daily_summary_time")  // минуты с 00:00
        val BATTERY_ONBOARDING_DONE = booleanPreferencesKey("battery_onboarding_done")
        val BATTERY_ONBOARDING_SKIPPED = booleanPreferencesKey("battery_onboarding_skipped")
        val FIRST_TASK_CREATED = booleanPreferencesKey("first_task_created")
        val ASR_ENGINE = stringPreferencesKey("asr_engine") // "auto" | "vosk"
        val GEOFENCE_MAX_PER_DAY = intPreferencesKey("geofence_max_per_day")
        val GEOFENCE_WINDOW_START = intPreferencesKey("geofence_window_start") // минуты
        val GEOFENCE_WINDOW_END = intPreferencesKey("geofence_window_end")
    }

    // ── Тихие часы ────────────────────────────────────────────────────────

    val quietHoursEnabled: Flow<Boolean> = store.data.map {
        it[Keys.QUIET_HOURS_ENABLED] ?: false
    }

    /** Начало тихих часов (минуты с 00:00). По умолчанию 23:00 = 1380 */
    val quietHoursStart: Flow<Int> = store.data.map {
        it[Keys.QUIET_HOURS_START] ?: 1380
    }

    /** Конец тихих часов (минуты с 00:00). По умолчанию 08:00 = 480 */
    val quietHoursEnd: Flow<Int> = store.data.map {
        it[Keys.QUIET_HOURS_END] ?: 480
    }

    // ── Время быстрого переноса ────────────────────────────────────────────

    /** "Вечером" = (минуты с 00:00). По умолчанию 18:00 = 1080 */
    val eveningTime: Flow<Int> = store.data.map {
        it[Keys.EVENING_TIME] ?: 1080
    }

    /** "Утром" = (минуты с 00:00). По умолчанию 09:00 = 540 */
    val morningTime: Flow<Int> = store.data.map {
        it[Keys.MORNING_TIME] ?: 540
    }

    // ── Запись и подтверждение ────────────────────────────────────────────

    /** Таймер на экране подтверждения в секундах. По умолчанию 8 */
    val confirmTimerSeconds: Flow<Int> = store.data.map {
        it[Keys.CONFIRM_TIMER_SECONDS] ?: 8
    }

    /** true = режим переключателя, false = режим удержания */
    val recordModeToggle: Flow<Boolean> = store.data.map {
        it[Keys.RECORD_MODE_TOGGLE] ?: false
    }

    // ── Настойчивые уведомления ───────────────────────────────────────────

    /** Интервал повтора по умолчанию в минутах. 0 = выкл */
    val defaultSnoozeInterval: Flow<Int> = store.data.map {
        it[Keys.DEFAULT_SNOOZE_INTERVAL] ?: 0
    }

    /** Макс. число повторов по умолчанию. 0 = без ограничений */
    val defaultSnoozeMax: Flow<Int> = store.data.map {
        it[Keys.DEFAULT_SNOOZE_MAX] ?: 5
    }

    // ── Утренняя сводка ───────────────────────────────────────────────────

    val dailySummaryEnabled: Flow<Boolean> = store.data.map {
        it[Keys.DAILY_SUMMARY_ENABLED] ?: true
    }

    /** Время сводки (минуты с 00:00). По умолчанию 08:00 = 480 */
    val dailySummaryTime: Flow<Int> = store.data.map {
        it[Keys.DAILY_SUMMARY_TIME] ?: 480
    }

    // ── Onboarding ────────────────────────────────────────────────────────

    val batteryOnboardingDone: Flow<Boolean> = store.data.map {
        it[Keys.BATTERY_ONBOARDING_DONE] ?: false
    }

    val batteryOnboardingSkipped: Flow<Boolean> = store.data.map {
        it[Keys.BATTERY_ONBOARDING_SKIPPED] ?: false
    }

    val firstTaskCreated: Flow<Boolean> = store.data.map {
        it[Keys.FIRST_TASK_CREATED] ?: false
    }

    // ── Движок распознавания речи ─────────────────────────────────────────

    /** "auto" (HMS если онлайн, иначе Vosk) или "vosk" */
    val asrEngine: Flow<String> = store.data.map {
        it[Keys.ASR_ENGINE] ?: "auto"
    }

    // ── Геолокация ─────────────────────────────────────────────────────────

    val geofenceMaxPerDay: Flow<Int> = store.data.map {
        it[Keys.GEOFENCE_MAX_PER_DAY] ?: 2
    }

    val geofenceWindowStart: Flow<Int> = store.data.map {
        it[Keys.GEOFENCE_WINDOW_START] ?: 540  // 09:00
    }

    val geofenceWindowEnd: Flow<Int> = store.data.map {
        it[Keys.GEOFENCE_WINDOW_END] ?: 1320   // 22:00
    }

    // ── Сеттеры ────────────────────────────────────────────────────────────

    suspend fun setQuietHoursEnabled(enabled: Boolean) = store.edit {
        it[Keys.QUIET_HOURS_ENABLED] = enabled
    }

    suspend fun setQuietHours(startMinutes: Int, endMinutes: Int) = store.edit {
        it[Keys.QUIET_HOURS_START] = startMinutes
        it[Keys.QUIET_HOURS_END] = endMinutes
    }

    suspend fun setEveningTime(minutes: Int) = store.edit {
        it[Keys.EVENING_TIME] = minutes
    }

    suspend fun setMorningTime(minutes: Int) = store.edit {
        it[Keys.MORNING_TIME] = minutes
    }

    suspend fun setConfirmTimerSeconds(seconds: Int) = store.edit {
        it[Keys.CONFIRM_TIMER_SECONDS] = seconds
    }

    suspend fun setRecordModeToggle(toggle: Boolean) = store.edit {
        it[Keys.RECORD_MODE_TOGGLE] = toggle
    }

    suspend fun setDefaultSnooze(intervalMinutes: Int, maxCount: Int) = store.edit {
        it[Keys.DEFAULT_SNOOZE_INTERVAL] = intervalMinutes
        it[Keys.DEFAULT_SNOOZE_MAX] = maxCount
    }

    suspend fun setDailySummary(enabled: Boolean, timeMinutes: Int) = store.edit {
        it[Keys.DAILY_SUMMARY_ENABLED] = enabled
        it[Keys.DAILY_SUMMARY_TIME] = timeMinutes
    }

    suspend fun setBatteryOnboardingDone() = store.edit {
        it[Keys.BATTERY_ONBOARDING_DONE] = true
        it[Keys.BATTERY_ONBOARDING_SKIPPED] = false
    }

    suspend fun setBatteryOnboardingSkipped() = store.edit {
        it[Keys.BATTERY_ONBOARDING_SKIPPED] = true
    }

    suspend fun setFirstTaskCreated() = store.edit {
        it[Keys.FIRST_TASK_CREATED] = true
    }

    suspend fun setAsrEngine(engine: String) = store.edit {
        it[Keys.ASR_ENGINE] = engine
    }
}
