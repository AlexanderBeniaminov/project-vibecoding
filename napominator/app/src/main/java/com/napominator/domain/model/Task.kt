package com.napominator.domain.model

import com.napominator.data.db.TaskEntity

/**
 * Доменная модель задачи — чистая, без аннотаций Room.
 * Используется в UI и бизнес-логике.
 */
data class Task(
    val id: Long = 0,
    val title: String,
    val createdAt: Long = System.currentTimeMillis(),
    val reminderAt: Long? = null,
    val rrule: String? = null,
    val repeatUntil: Long? = null,
    val isCompleted: Boolean = false,
    val completedAt: Long? = null,
    // Геолокация
    val geofenceLat: Double? = null,
    val geofenceLon: Double? = null,
    val geofenceRadius: Int? = null,
    val geofenceTrigger: String? = null,
    val geofenceMaxPerDay: Int? = null,
    val geofenceWindowStart: Int? = null,
    val geofenceWindowEnd: Int? = null,
    // Настойчивость
    val snoozeIntervalMinutes: Int? = null,
    val snoozeMaxCount: Int? = null,
    val snoozeCurrentCount: Int = 0,
    val snoozePausesDuringQuietHours: Boolean = true,
    // Синхронизация
    val calendarEventId: String? = null,
    val calendarEtag: String? = null
) {
    /** Есть геолокационный триггер */
    val hasGeofence: Boolean get() = geofenceLat != null

    /** Есть время напоминания */
    val hasReminder: Boolean get() = reminderAt != null

    /** Повторяется */
    val isRepeating: Boolean get() = rrule != null

    /** Просрочена */
    fun isOverdue(now: Long = System.currentTimeMillis()): Boolean =
        !isCompleted && reminderAt != null && reminderAt < now
}

// ── Маппер ──────────────────────────────────────────────────────────────────

fun TaskEntity.toDomain() = Task(
    id = id,
    title = title,
    createdAt = createdAt,
    reminderAt = reminderAt,
    rrule = rrule,
    repeatUntil = repeatUntil,
    isCompleted = isCompleted,
    completedAt = completedAt,
    geofenceLat = geofenceLat,
    geofenceLon = geofenceLon,
    geofenceRadius = geofenceRadius,
    geofenceTrigger = geofenceTrigger,
    geofenceMaxPerDay = geofenceMaxPerDay,
    geofenceWindowStart = geofenceWindowStart,
    geofenceWindowEnd = geofenceWindowEnd,
    snoozeIntervalMinutes = snoozeIntervalMinutes,
    snoozeMaxCount = snoozeMaxCount,
    snoozeCurrentCount = snoozeCurrentCount,
    snoozePausesDuringQuietHours = snoozePausesDuringQuietHours,
    calendarEventId = calendarEventId,
    calendarEtag = calendarEtag
)

fun Task.toEntity() = TaskEntity(
    id = id,
    title = title,
    createdAt = createdAt,
    reminderAt = reminderAt,
    rrule = rrule,
    repeatUntil = repeatUntil,
    isCompleted = isCompleted,
    completedAt = completedAt,
    geofenceLat = geofenceLat,
    geofenceLon = geofenceLon,
    geofenceRadius = geofenceRadius,
    geofenceTrigger = geofenceTrigger,
    geofenceMaxPerDay = geofenceMaxPerDay,
    geofenceWindowStart = geofenceWindowStart,
    geofenceWindowEnd = geofenceWindowEnd,
    snoozeIntervalMinutes = snoozeIntervalMinutes,
    snoozeMaxCount = snoozeMaxCount,
    snoozeCurrentCount = snoozeCurrentCount,
    snoozePausesDuringQuietHours = snoozePausesDuringQuietHours,
    calendarEventId = calendarEventId,
    calendarEtag = calendarEtag
)
