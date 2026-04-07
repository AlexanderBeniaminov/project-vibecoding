package com.napominator.data.repository

import com.napominator.data.db.TaskDao
import com.napominator.domain.model.Task
import com.napominator.domain.model.toDomain
import com.napominator.domain.model.toEntity
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class TaskRepository @Inject constructor(
    private val dao: TaskDao
) {
    /** Поток активных (невыполненных) задач */
    fun getActiveTasks(): Flow<List<Task>> =
        dao.getActiveTasks().map { list -> list.map { it.toDomain() } }

    /** Одноразовый снимок активных задач (для сводки) */
    suspend fun getActiveTasksOnce(): List<Task> = getActiveTasks().first()

    /** Поток всех задач */
    fun getAllTasks(): Flow<List<Task>> =
        dao.getAllTasks().map { list -> list.map { it.toDomain() } }

    /** Поток просроченных задач */
    fun getOverdueTasks(): Flow<List<Task>> =
        dao.getOverdueTasks().map { list -> list.map { it.toDomain() } }

    /** Поиск по названию */
    fun searchTasks(query: String): Flow<List<Task>> =
        dao.searchTasks(query).map { list -> list.map { it.toDomain() } }

    /** Получить задачу по id */
    suspend fun getById(id: Long): Task? = dao.getById(id)?.toDomain()

    /** Задачи с напоминанием в диапазоне (для утренней сводки) */
    suspend fun getTasksInRange(from: Long, to: Long): List<Task> =
        dao.getTasksInRange(from, to).map { it.toDomain() }

    /** Задачи с геофенсом (для восстановления после перезагрузки) */
    suspend fun getGeofenceTasks(): List<Task> =
        dao.getGeofenceTasks().map { it.toDomain() }

    /** Задачи с будущими будильниками (для восстановления после перезагрузки) */
    suspend fun getFutureAlarmTasks(): List<Task> =
        dao.getFutureAlarmTasks().map { it.toDomain() }

    /** Сохранить новую задачу, вернуть присвоенный id */
    suspend fun save(task: Task): Long = dao.insert(task.toEntity())

    /** Алиас для save — используется в ConfirmViewModel */
    suspend fun insert(task: Task): Long = save(task)

    /** Обновить существующую задачу */
    suspend fun update(task: Task) = dao.update(task.toEntity())

    /** Удалить задачу */
    suspend fun delete(task: Task) = dao.delete(task.toEntity())

    /** Удалить задачу по id */
    suspend fun deleteById(id: Long) = dao.deleteById(id)

    /** Отметить выполненной */
    suspend fun markCompleted(id: Long) = dao.markCompleted(id)

    /** Перенести напоминание */
    suspend fun reschedule(id: Long, newTime: Long) = dao.reschedule(id, newTime)

    /** Увеличить счётчик показанных уведомлений */
    suspend fun incrementSnoozeCount(id: Long) = dao.incrementSnoozeCount(id)

    /** Сбросить счётчик уведомлений */
    suspend fun resetSnoozeCount(id: Long) = dao.resetSnoozeCount(id)

    /** Удалить все выполненные */
    suspend fun deleteCompleted() = dao.deleteCompleted()
}
