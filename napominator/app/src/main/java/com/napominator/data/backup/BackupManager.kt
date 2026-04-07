package com.napominator.data.backup

import android.content.Context
import com.napominator.data.repository.TaskRepository
import com.napominator.domain.model.Task
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.first
import org.json.JSONArray
import org.json.JSONObject
import java.io.InputStream
import java.io.OutputStream
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Экспорт и импорт задач в JSON.
 * Формат: { "version": 1, "tasks": [ {...}, ... ] }
 */
@Singleton
class BackupManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val taskRepository: TaskRepository
) {

    companion object {
        private const val BACKUP_VERSION = 1
    }

    /**
     * Экспортирует все задачи в JSON и пишет в [outputStream].
     * @return количество экспортированных задач
     */
    suspend fun exportToJson(outputStream: OutputStream): Int {
        val tasks = taskRepository.getAllTasksOnce()

        val jsonTasks = JSONArray()
        tasks.forEach { task ->
            jsonTasks.put(task.toJson())
        }

        val root = JSONObject().apply {
            put("version", BACKUP_VERSION)
            put("exportedAt", System.currentTimeMillis())
            put("tasks", jsonTasks)
        }

        outputStream.writer(Charsets.UTF_8).use { it.write(root.toString(2)) }
        return tasks.size
    }

    /**
     * Импортирует задачи из JSON [inputStream].
     * Дубликаты по id пропускаются.
     * @return количество импортированных задач
     */
    suspend fun importFromJson(inputStream: InputStream): ImportResult {
        val json = inputStream.reader(Charsets.UTF_8).readText()

        val root = try {
            JSONObject(json)
        } catch (e: Exception) {
            return ImportResult.Error("Неверный формат файла")
        }

        val version = root.optInt("version", 0)
        if (version < 1) return ImportResult.Error("Неподдерживаемая версия формата")

        val jsonTasks = root.optJSONArray("tasks")
            ?: return ImportResult.Error("Задачи не найдены в файле")

        // Получаем существующие id для проверки дубликатов
        val existingIds = taskRepository.getAllTasks().first().map { it.id }.toSet()

        var imported = 0
        var skipped = 0

        for (i in 0 until jsonTasks.length()) {
            try {
                val taskJson = jsonTasks.getJSONObject(i)
                val task = taskJson.toTask()

                if (task.id in existingIds) {
                    skipped++
                } else {
                    // Вставляем с исходным id через insert (сохраняем id)
                    taskRepository.insert(task)
                    imported++
                }
            } catch (e: Exception) {
                skipped++
            }
        }

        return ImportResult.Success(imported, skipped)
    }

    private fun Task.toJson(): JSONObject = JSONObject().apply {
        put("id", id)
        put("title", title)
        put("createdAt", createdAt)
        reminderAt?.let { put("reminderAt", it) }
        rrule?.let { put("rrule", it) }
        repeatUntil?.let { put("repeatUntil", it) }
        put("isCompleted", isCompleted)
        completedAt?.let { put("completedAt", it) }
        snoozeIntervalMinutes?.let { put("snoozeIntervalMinutes", it) }
        snoozeMaxCount?.let { put("snoozeMaxCount", it) }
        put("snoozeCurrentCount", snoozeCurrentCount)
        geofenceLat?.let { put("geofenceLat", it) }
        geofenceLon?.let { put("geofenceLon", it) }
        geofenceRadius?.let { put("geofenceRadius", it) }
        geofenceTrigger?.let { put("geofenceTrigger", it) }
    }

    private fun JSONObject.toTask(): Task = Task(
        id = getLong("id"),
        title = getString("title"),
        createdAt = optLong("createdAt", System.currentTimeMillis()),
        reminderAt = if (has("reminderAt")) getLong("reminderAt") else null,
        rrule = if (has("rrule")) getString("rrule") else null,
        repeatUntil = if (has("repeatUntil")) getLong("repeatUntil") else null,
        isCompleted = optBoolean("isCompleted", false),
        completedAt = if (has("completedAt")) getLong("completedAt") else null,
        snoozeIntervalMinutes = if (has("snoozeIntervalMinutes")) getInt("snoozeIntervalMinutes") else null,
        snoozeMaxCount = if (has("snoozeMaxCount")) getInt("snoozeMaxCount") else null,
        snoozeCurrentCount = optInt("snoozeCurrentCount", 0),
        geofenceLat = if (has("geofenceLat")) getDouble("geofenceLat") else null,
        geofenceLon = if (has("geofenceLon")) getDouble("geofenceLon") else null,
        geofenceRadius = if (has("geofenceRadius")) getInt("geofenceRadius") else null,
        geofenceTrigger = if (has("geofenceTrigger")) getString("geofenceTrigger") else null
    )

    sealed class ImportResult {
        data class Success(val imported: Int, val skipped: Int) : ImportResult()
        data class Error(val message: String) : ImportResult()
    }
}
