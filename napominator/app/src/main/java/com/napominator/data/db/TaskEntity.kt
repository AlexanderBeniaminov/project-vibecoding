package com.napominator.data.db

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Задача в базе данных.
 * Все поля nullable там, где значение опционально.
 */
@Entity(tableName = "tasks")
data class TaskEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,

    /** Текст задачи */
    val title: String,

    /** Когда задача была создана (Unix timestamp в миллисекундах) */
    val createdAt: Long = System.currentTimeMillis(),

    /** Когда сработает напоминание (Unix timestamp мс). null = задача без времени */
    val reminderAt: Long? = null,

    /**
     * Паттерн повторения в формате RRULE (RFC 5545).
     * Примеры:
     * - "FREQ=DAILY"                        каждый день
     * - "FREQ=WEEKLY;BYDAY=MO,FR"           каждый пн и пт
     * - "FREQ=MONTHLY;BYMONTHDAY=15"        каждый месяц 15-го
     * - "FREQ=MONTHLY;BYMONTHDAY=-1"        каждый последний день месяца
     * - "FREQ=DAILY;INTERVAL=2"             каждые 2 дня
     * null = не повторяется
     */
    val rrule: String? = null,

    /** До какого момента повторять (Unix timestamp мс). null = бесконечно */
    val repeatUntil: Long? = null,

    /** Задача выполнена */
    val isCompleted: Boolean = false,

    /** Когда была выполнена */
    val completedAt: Long? = null,

    // ── Геолокация ──────────────────────────────────────────────────────────

    val geofenceLat: Double? = null,
    val geofenceLon: Double? = null,
    val geofenceRadius: Int? = null,       // метры: 100, 300, 500, 1000

    /** "ENTER" или "EXIT" */
    val geofenceTrigger: String? = null,

    /** Максимум срабатываний в день. null = без ограничений */
    val geofenceMaxPerDay: Int? = null,

    /** Начало временного окна срабатывания (минуты с 00:00, напр. 540 = 09:00) */
    val geofenceWindowStart: Int? = null,

    /** Конец временного окна срабатывания (напр. 1320 = 22:00) */
    val geofenceWindowEnd: Int? = null,

    /** Сколько раз сегодня уже сработал геофенс */
    val geofenceTodayCount: Int = 0,

    /** Дата последнего сброса счётчика геофенса (yyyy-MM-dd) */
    val geofenceCountResetDate: String? = null,

    // ── Настойчивость уведомлений ────────────────────────────────────────────

    /** Интервал повтора уведомления в минутах. null = без повтора */
    val snoozeIntervalMinutes: Int? = null,

    /** Максимальное число повторов. null = без ограничений */
    val snoozeMaxCount: Int? = null,

    /** Сколько раз уже было показано уведомление по этому напоминанию */
    val snoozeCurrentCount: Int = 0,

    /** Останавливать повторы во время тихих часов */
    val snoozePausesDuringQuietHours: Boolean = true,

    // ── Синхронизация с календарём ───────────────────────────────────────────

    /** UID события в CalDAV после синхронизации */
    val calendarEventId: String? = null,

    /** ETag события для обнаружения конфликтов при синхронизации */
    val calendarEtag: String? = null
)
