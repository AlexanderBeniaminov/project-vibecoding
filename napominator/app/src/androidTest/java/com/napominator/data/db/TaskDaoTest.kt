package com.napominator.data.db

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class TaskDaoTest {

    private lateinit var db: AppDatabase
    private lateinit var dao: TaskDao

    @Before
    fun setUp() {
        db = Room.inMemoryDatabaseBuilder(
            ApplicationProvider.getApplicationContext(),
            AppDatabase::class.java
        ).allowMainThreadQueries().build()
        dao = db.taskDao()
    }

    @After
    fun tearDown() {
        db.close()
    }

    // ── Insert / CRUD ─────────────────────────────────────────────────────────

    @Test
    fun insert_returnsGeneratedId() = runTest {
        val id = dao.insert(makeTask(title = "Купить молоко"))
        assertTrue(id > 0)
    }

    @Test
    fun getById_returnsInsertedTask() = runTest {
        val id = dao.insert(makeTask(title = "Позвонить врачу"))
        val task = dao.getById(id)
        assertNotNull(task)
        assertEquals("Позвонить врачу", task!!.title)
    }

    @Test
    fun getById_returnsNull_whenNotFound() = runTest {
        val task = dao.getById(99999L)
        assertNull(task)
    }

    @Test
    fun update_changesTitle() = runTest {
        val id = dao.insert(makeTask(title = "Старый"))
        val task = dao.getById(id)!!
        dao.update(task.copy(title = "Новый"))
        assertEquals("Новый", dao.getById(id)!!.title)
    }

    @Test
    fun delete_removesTask() = runTest {
        val id = dao.insert(makeTask(title = "Удалить"))
        val task = dao.getById(id)!!
        dao.delete(task)
        assertNull(dao.getById(id))
    }

    @Test
    fun deleteById_removesTask() = runTest {
        val id = dao.insert(makeTask(title = "Удалить по id"))
        dao.deleteById(id)
        assertNull(dao.getById(id))
    }

    // ── getActiveTasks ────────────────────────────────────────────────────────

    @Test
    fun getActiveTasks_excludesCompleted() = runTest {
        dao.insert(makeTask(title = "Активная"))
        val completedId = dao.insert(makeTask(title = "Выполненная"))
        dao.markCompleted(completedId)

        val active = dao.getActiveTasks().first()
        assertEquals(1, active.size)
        assertEquals("Активная", active[0].title)
    }

    @Test
    fun getActiveTasks_sortsByReminderAt_nullsLast() = runTest {
        val now = System.currentTimeMillis()
        dao.insert(makeTask(title = "Без времени", reminderAt = null))
        dao.insert(makeTask(title = "Позже", reminderAt = now + 10_000))
        dao.insert(makeTask(title = "Раньше", reminderAt = now + 1_000))

        val active = dao.getActiveTasks().first()
        assertEquals(3, active.size)
        assertEquals("Раньше", active[0].title)
        assertEquals("Позже", active[1].title)
        assertEquals("Без времени", active[2].title)
    }

    @Test
    fun getActiveTasks_emptyWhenNone() = runTest {
        val active = dao.getActiveTasks().first()
        assertTrue(active.isEmpty())
    }

    // ── markCompleted ─────────────────────────────────────────────────────────

    @Test
    fun markCompleted_setsIsCompletedAndTimestamp() = runTest {
        val id = dao.insert(makeTask(title = "Задача"))
        dao.markCompleted(id)
        val task = dao.getById(id)!!
        assertTrue(task.isCompleted)
        assertNotNull(task.completedAt)
    }

    // ── getOverdueTasks ───────────────────────────────────────────────────────

    @Test
    fun getOverdueTasks_returnsOnlyPastReminders() = runTest {
        val now = System.currentTimeMillis()
        dao.insert(makeTask(title = "Просроченная", reminderAt = now - 60_000))
        dao.insert(makeTask(title = "Будущая", reminderAt = now + 60_000))
        dao.insert(makeTask(title = "Без времени", reminderAt = null))

        val overdue = dao.getOverdueTasks(now).first()
        assertEquals(1, overdue.size)
        assertEquals("Просроченная", overdue[0].title)
    }

    @Test
    fun getOverdueTasks_excludesCompleted() = runTest {
        val now = System.currentTimeMillis()
        val id = dao.insert(makeTask(title = "Выполнена но просрочена", reminderAt = now - 60_000))
        dao.markCompleted(id)

        val overdue = dao.getOverdueTasks(now).first()
        assertTrue(overdue.isEmpty())
    }

    // ── searchTasks ───────────────────────────────────────────────────────────

    @Test
    fun searchTasks_findsByPartialTitle() = runTest {
        dao.insert(makeTask(title = "Позвонить врачу"))
        dao.insert(makeTask(title = "Купить молоко"))
        dao.insert(makeTask(title = "Позвонить маме"))

        val results = dao.searchTasks("Позвонить").first()
        assertEquals(2, results.size)
    }

    @Test
    fun searchTasks_caseInsensitive() = runTest {
        dao.insert(makeTask(title = "Позвонить врачу"))
        val results = dao.searchTasks("позвонить").first()
        assertEquals(1, results.size)
    }

    @Test
    fun searchTasks_returnsEmpty_whenNoMatch() = runTest {
        dao.insert(makeTask(title = "Купить молоко"))
        val results = dao.searchTasks("zzznomatch").first()
        assertTrue(results.isEmpty())
    }

    // ── getTasksInRange ───────────────────────────────────────────────────────

    @Test
    fun getTasksInRange_returnsOnlyMatchingTasks() = runTest {
        val base = System.currentTimeMillis()
        dao.insert(makeTask(title = "До диапазона", reminderAt = base - 100_000))
        dao.insert(makeTask(title = "В диапазоне", reminderAt = base + 1_000))
        dao.insert(makeTask(title = "После диапазона", reminderAt = base + 200_000))

        val tasks = dao.getTasksInRange(base, base + 10_000)
        assertEquals(1, tasks.size)
        assertEquals("В диапазоне", tasks[0].title)
    }

    // ── getGeofenceTasks ──────────────────────────────────────────────────────

    @Test
    fun getGeofenceTasks_returnsOnlyTasksWithLatLon() = runTest {
        dao.insert(makeTask(title = "Обычная"))
        dao.insert(makeTask(
            title = "С геофенсом",
            geofenceLat = 55.75,
            geofenceLon = 37.62
        ))

        val geo = dao.getGeofenceTasks()
        assertEquals(1, geo.size)
        assertEquals("С геофенсом", geo[0].title)
    }

    // ── getFutureAlarmTasks ───────────────────────────────────────────────────

    @Test
    fun getFutureAlarmTasks_returnsOnlyFutureTasks() = runTest {
        val now = System.currentTimeMillis()
        dao.insert(makeTask(title = "Прошедшая", reminderAt = now - 1_000))
        dao.insert(makeTask(title = "Будущая", reminderAt = now + 60_000))
        dao.insert(makeTask(title = "Без времени", reminderAt = null))

        val future = dao.getFutureAlarmTasks(now)
        assertEquals(1, future.size)
        assertEquals("Будущая", future[0].title)
    }

    // ── reschedule ────────────────────────────────────────────────────────────

    @Test
    fun reschedule_updatesReminderAndResetsSnoozeCount() = runTest {
        val id = dao.insert(makeTask(title = "Задача", snoozeCurrentCount = 3))
        val newTime = System.currentTimeMillis() + 3_600_000
        dao.reschedule(id, newTime)
        val task = dao.getById(id)!!
        assertEquals(newTime, task.reminderAt)
        assertEquals(0, task.snoozeCurrentCount)
    }

    // ── snooze count ──────────────────────────────────────────────────────────

    @Test
    fun incrementSnoozeCount_incrementsByOne() = runTest {
        val id = dao.insert(makeTask(title = "Задача"))
        dao.incrementSnoozeCount(id)
        dao.incrementSnoozeCount(id)
        val task = dao.getById(id)!!
        assertEquals(2, task.snoozeCurrentCount)
    }

    @Test
    fun resetSnoozeCount_setsToZero() = runTest {
        val id = dao.insert(makeTask(title = "Задача", snoozeCurrentCount = 5))
        dao.resetSnoozeCount(id)
        assertEquals(0, dao.getById(id)!!.snoozeCurrentCount)
    }

    // ── geofence count ────────────────────────────────────────────────────────

    @Test
    fun updateGeofenceCount_updatesCountAndDate() = runTest {
        val id = dao.insert(makeTask(title = "Гео-задача"))
        dao.updateGeofenceCount(id, count = 3, date = "2026-04-06")
        val task = dao.getById(id)!!
        assertEquals(3, task.geofenceTodayCount)
        assertEquals("2026-04-06", task.geofenceCountResetDate)
    }

    // ── deleteCompleted ───────────────────────────────────────────────────────

    @Test
    fun deleteCompleted_removesOnlyCompletedTasks() = runTest {
        dao.insert(makeTask(title = "Активная"))
        val id = dao.insert(makeTask(title = "Выполненная"))
        dao.markCompleted(id)

        dao.deleteCompleted()

        val all = dao.getAllTasks().first()
        assertEquals(1, all.size)
        assertEquals("Активная", all[0].title)
    }

    // ── RRULE / calendarEtag ──────────────────────────────────────────────────

    @Test
    fun insert_storesRruleAndCalendarFields() = runTest {
        val id = dao.insert(makeTask(
            title = "Еженедельная",
            rrule = "FREQ=WEEKLY;BYDAY=MO",
            calendarEventId = "abc-123",
            calendarEtag = "etag-v1"
        ))
        val task = dao.getById(id)!!
        assertEquals("FREQ=WEEKLY;BYDAY=MO", task.rrule)
        assertEquals("abc-123", task.calendarEventId)
        assertEquals("etag-v1", task.calendarEtag)
    }

    // ── Вспомогательная функция ───────────────────────────────────────────────

    private fun makeTask(
        title: String,
        reminderAt: Long? = null,
        rrule: String? = null,
        geofenceLat: Double? = null,
        geofenceLon: Double? = null,
        snoozeCurrentCount: Int = 0,
        calendarEventId: String? = null,
        calendarEtag: String? = null,
    ) = TaskEntity(
        title = title,
        reminderAt = reminderAt,
        rrule = rrule,
        geofenceLat = geofenceLat,
        geofenceLon = geofenceLon,
        snoozeCurrentCount = snoozeCurrentCount,
        calendarEventId = calendarEventId,
        calendarEtag = calendarEtag,
    )
}
