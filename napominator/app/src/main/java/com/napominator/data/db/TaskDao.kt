package com.napominator.data.db

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Dao
interface TaskDao {

    // ── Запросы ──────────────────────────────────────────────────────────────

    /** Все невыполненные задачи, отсортированные по времени напоминания */
    @Query("""
        SELECT * FROM tasks
        WHERE isCompleted = 0
        ORDER BY
            CASE WHEN reminderAt IS NULL THEN 1 ELSE 0 END,
            reminderAt ASC
    """)
    fun getActiveTasks(): Flow<List<TaskEntity>>

    /** Все задачи (включая выполненные) */
    @Query("SELECT * FROM tasks ORDER BY createdAt DESC")
    fun getAllTasks(): Flow<List<TaskEntity>>

    /** Задача по id */
    @Query("SELECT * FROM tasks WHERE id = :id")
    suspend fun getById(id: Long): TaskEntity?

    /** Задачи с напоминанием в диапазоне времени (для утренней сводки) */
    @Query("""
        SELECT * FROM tasks
        WHERE isCompleted = 0
          AND reminderAt BETWEEN :from AND :to
        ORDER BY reminderAt ASC
    """)
    suspend fun getTasksInRange(from: Long, to: Long): List<TaskEntity>

    /** Просроченные задачи (напоминание в прошлом, не выполнены) */
    @Query("""
        SELECT * FROM tasks
        WHERE isCompleted = 0
          AND reminderAt < :now
          AND reminderAt IS NOT NULL
        ORDER BY reminderAt DESC
    """)
    fun getOverdueTasks(now: Long = System.currentTimeMillis()): Flow<List<TaskEntity>>

    /** Задачи с активным геофенсом */
    @Query("""
        SELECT * FROM tasks
        WHERE isCompleted = 0
          AND geofenceLat IS NOT NULL
    """)
    suspend fun getGeofenceTasks(): List<TaskEntity>

    /** Задачи с активным будильником (для восстановления после перезагрузки) */
    @Query("""
        SELECT * FROM tasks
        WHERE isCompleted = 0
          AND reminderAt > :now
    """)
    suspend fun getFutureAlarmTasks(now: Long = System.currentTimeMillis()): List<TaskEntity>

    /** Поиск по названию */
    @Query("""
        SELECT * FROM tasks
        WHERE isCompleted = 0
          AND title LIKE '%' || :query || '%'
        ORDER BY reminderAt ASC
    """)
    fun searchTasks(query: String): Flow<List<TaskEntity>>

    // ── Изменения ─────────────────────────────────────────────────────────────

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(task: TaskEntity): Long

    @Update
    suspend fun update(task: TaskEntity)

    @Delete
    suspend fun delete(task: TaskEntity)

    @Query("DELETE FROM tasks WHERE id = :id")
    suspend fun deleteById(id: Long)

    /** Отметить выполненной */
    @Query("""
        UPDATE tasks
        SET isCompleted = 1, completedAt = :completedAt
        WHERE id = :id
    """)
    suspend fun markCompleted(id: Long, completedAt: Long = System.currentTimeMillis())

    /** Перенести напоминание на новое время */
    @Query("UPDATE tasks SET reminderAt = :newTime, snoozeCurrentCount = 0 WHERE id = :id")
    suspend fun reschedule(id: Long, newTime: Long)

    /** Сбросить счётчик настойчивых уведомлений */
    @Query("UPDATE tasks SET snoozeCurrentCount = 0 WHERE id = :id")
    suspend fun resetSnoozeCount(id: Long)

    /** Увеличить счётчик настойчивых уведомлений */
    @Query("UPDATE tasks SET snoozeCurrentCount = snoozeCurrentCount + 1 WHERE id = :id")
    suspend fun incrementSnoozeCount(id: Long)

    /** Обновить счётчик срабатываний геофенса */
    @Query("""
        UPDATE tasks
        SET geofenceTodayCount = :count, geofenceCountResetDate = :date
        WHERE id = :id
    """)
    suspend fun updateGeofenceCount(id: Long, count: Int, date: String)

    /** Удалить все выполненные задачи */
    @Query("DELETE FROM tasks WHERE isCompleted = 1")
    suspend fun deleteCompleted()
}
