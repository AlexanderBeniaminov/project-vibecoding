package com.napominator.nlp

import org.junit.Assert.*
import org.junit.Test
import java.util.Calendar

/**
 * Unit-тесты NLP-парсера.
 * Запускаются на JVM, не требуют Android-устройства.
 *
 * Фиксированная "сейчас": понедельник, 7 апреля 2026, 10:00
 */
class NlpParserTest {

    private val parser = NlpParser()

    /** Понедельник 2026-04-07 10:00:00 */
    private fun now(): Calendar = Calendar.getInstance().apply {
        set(2026, Calendar.APRIL, 7, 10, 0, 0)
        set(Calendar.MILLISECOND, 0)
    }

    private fun cal(year: Int, month: Int, day: Int, hour: Int, min: Int): Calendar =
        Calendar.getInstance().apply {
            set(year, month - 1, day, hour, min, 0)
            set(Calendar.MILLISECOND, 0)
        }

    private fun assertTimestamp(
        phrase: String,
        expectedYear: Int, expectedMonth: Int, expectedDay: Int,
        expectedHour: Int, expectedMinute: Int
    ) {
        val result = parser.parse(phrase, now())
        assertNotNull("Timestamp must not be null for: \"$phrase\"", result.reminderAt)
        val actual = Calendar.getInstance().apply { timeInMillis = result.reminderAt!! }
        assertEquals("Year for \"$phrase\"", expectedYear, actual.get(Calendar.YEAR))
        assertEquals("Month for \"$phrase\"", expectedMonth, actual.get(Calendar.MONTH) + 1)
        assertEquals("Day for \"$phrase\"", expectedDay, actual.get(Calendar.DAY_OF_MONTH))
        assertEquals("Hour for \"$phrase\"", expectedHour, actual.get(Calendar.HOUR_OF_DAY))
        assertEquals("Minute for \"$phrase\"", expectedMinute, actual.get(Calendar.MINUTE))
    }

    // ── Даты ─────────────────────────────────────────────────────────────────

    @Test
    fun `завтра - следующий день`() {
        assertTimestamp("Позвонить врачу завтра", 2026, 4, 8, 9, 0)
    }

    @Test
    fun `послезавтра - через 2 дня`() {
        assertTimestamp("Купить молоко послезавтра", 2026, 4, 9, 9, 0)
    }

    @Test
    fun `сегодня вечером`() {
        assertTimestamp("Сделать отчёт сегодня вечером", 2026, 4, 7, 18, 0)
    }

    @Test
    fun `в пятницу`() {
        // Сегодня понедельник → ближайшая пятница = 11 апреля
        assertTimestamp("Встреча в пятницу", 2026, 4, 11, 9, 0)
    }

    @Test
    fun `в следующий вторник`() {
        // Сегодня понедельник → следующий вторник = 14 апреля (следующая неделя)
        assertTimestamp("Врач в следующий вторник", 2026, 4, 14, 9, 0)
    }

    @Test
    fun `через 2 часа`() {
        val result = parser.parse("Позвонить через 2 часа", now())
        assertNotNull(result.reminderAt)
        val actual = Calendar.getInstance().apply { timeInMillis = result.reminderAt!! }
        assertEquals(12, actual.get(Calendar.HOUR_OF_DAY))
    }

    @Test
    fun `через 30 минут`() {
        val result = parser.parse("Напомнить через 30 минут", now())
        assertNotNull(result.reminderAt)
        val actual = Calendar.getInstance().apply { timeInMillis = result.reminderAt!! }
        assertEquals(10, actual.get(Calendar.HOUR_OF_DAY))
        assertEquals(30, actual.get(Calendar.MINUTE))
    }

    @Test
    fun `через 3 дня`() {
        assertTimestamp("Подготовить презентацию через 3 дня", 2026, 4, 10, 10, 0)
    }

    @Test
    fun `10 декабря`() {
        assertTimestamp("Новый год 10 декабря", 2026, 12, 10, 9, 0)
    }

    @Test
    fun `числовая дата DD_MM`() {
        assertTimestamp("Встреча 15.06", 2026, 6, 15, 9, 0)
    }

    // ── Время ─────────────────────────────────────────────────────────────────

    @Test
    fun `завтра в 15_00`() {
        assertTimestamp("Позвонить врачу завтра в 15:00", 2026, 4, 8, 15, 0)
    }

    @Test
    fun `в 9_30`() {
        // Время сегодня ещё не наступило? 10:00 > 9:30 → переносим на завтра
        val result = parser.parse("Встать в 9:30", now())
        assertNotNull(result.reminderAt)
        val actual = Calendar.getInstance().apply { timeInMillis = result.reminderAt!! }
        // 9:30 < 10:00 текущего времени → переносится на завтра
        assertEquals(8, actual.get(Calendar.DAY_OF_MONTH))
        assertEquals(9, actual.get(Calendar.HOUR_OF_DAY))
        assertEquals(30, actual.get(Calendar.MINUTE))
    }

    @Test
    fun `в 18_45`() {
        // 18:45 > 10:00 → сегодня
        assertTimestamp("Ужин в 18:45", 2026, 4, 7, 18, 45)
    }

    @Test
    fun `завтра утром`() {
        assertTimestamp("Сделать зарядку завтра утром", 2026, 4, 8, 9, 0)
    }

    @Test
    fun `в 9 вечера`() {
        assertTimestamp("Лечь спать в 9 вечера", 2026, 4, 7, 21, 0)
    }

    @Test
    fun `в обед`() {
        assertTimestamp("Позвонить в обед", 2026, 4, 7, 13, 0)
    }

    @Test
    fun `в пятницу в 14_00`() {
        assertTimestamp("Совещание в пятницу в 14:00", 2026, 4, 11, 14, 0)
    }

    // ── Повторения (RRULE) ────────────────────────────────────────────────────

    @Test
    fun `каждый день`() {
        val result = parser.parse("Пить воду каждый день")
        assertEquals("FREQ=DAILY", result.rrule)
    }

    @Test
    fun `ежедневно`() {
        val result = parser.parse("Принимать таблетки ежедневно")
        assertEquals("FREQ=DAILY", result.rrule)
    }

    @Test
    fun `каждую неделю`() {
        val result = parser.parse("Звонить маме каждую неделю")
        assertEquals("FREQ=WEEKLY", result.rrule)
    }

    @Test
    fun `каждый месяц`() {
        val result = parser.parse("Платить аренду каждый месяц")
        assertEquals("FREQ=MONTHLY", result.rrule)
    }

    @Test
    fun `каждые 2 дня`() {
        val result = parser.parse("Поливать цветы каждые 2 дня")
        assertEquals("FREQ=DAILY;INTERVAL=2", result.rrule)
    }

    @Test
    fun `каждые 3 недели`() {
        val result = parser.parse("Стрижка каждые 3 недели")
        assertEquals("FREQ=WEEKLY;INTERVAL=3", result.rrule)
    }

    @Test
    fun `каждый понедельник`() {
        val result = parser.parse("Планёрка каждый понедельник")
        assertEquals("FREQ=WEEKLY;BYDAY=MO", result.rrule)
    }

    @Test
    fun `каждую пятницу`() {
        val result = parser.parse("Отчёт каждую пятницу")
        assertEquals("FREQ=WEEKLY;BYDAY=FR", result.rrule)
    }

    @Test
    fun `по будням`() {
        val result = parser.parse("Зарядка по будням")
        assertEquals("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", result.rrule)
    }

    @Test
    fun `по выходным`() {
        val result = parser.parse("Пробежка по выходным")
        assertEquals("FREQ=WEEKLY;BYDAY=SA,SU", result.rrule)
    }

    @Test
    fun `каждый месяц 15-го`() {
        val result = parser.parse("Оплата кредита каждый месяц 15-го числа")
        assertEquals("FREQ=MONTHLY;BYMONTHDAY=15", result.rrule)
    }

    @Test
    fun `каждый последний день месяца`() {
        val result = parser.parse("Закрыть задачи последний день месяца")
        assertEquals("FREQ=MONTHLY;BYMONTHDAY=-1", result.rrule)
    }

    @Test
    fun `каждый год`() {
        val result = parser.parse("День рождения каждый год")
        assertEquals("FREQ=YEARLY", result.rrule)
    }

    // ── Задача без времени ────────────────────────────────────────────────────

    @Test
    fun `без времени - hasNoTime true`() {
        val result = parser.parse("Купить молоко")
        assertTrue(result.hasNoTime)
        assertNull(result.reminderAt)
        assertNull(result.rrule)
    }

    @Test
    fun `без времени - title сохраняется`() {
        val result = parser.parse("Позвонить маме")
        assertEquals("Позвонить маме", result.title)
    }

    // ── Заголовок (title) ─────────────────────────────────────────────────────

    @Test
    fun `title - убирает дату из фразы`() {
        val result = parser.parse("Позвонить врачу завтра в 15:00", now())
        val title = result.title.lowercase()
        assertFalse("Title should not contain 'завтра': ${result.title}", "завтра" in title)
        assertFalse("Title should not contain '15:00': ${result.title}", "15:00" in title)
        assertTrue("Title should contain 'позвонить': ${result.title}", "позвонить" in title)
    }

    @Test
    fun `title - убирает rrule из фразы`() {
        val result = parser.parse("Зарядка каждый день утром")
        val title = result.title.lowercase()
        assertFalse("каждый" in title)
        assertTrue("зарядка" in title)
    }

    // ── Комбинации ────────────────────────────────────────────────────────────

    @Test
    fun `повторение + время - оба поля заполнены`() {
        val result = parser.parse("Принимать таблетки каждый день в 8:00", now())
        assertEquals("FREQ=DAILY", result.rrule)
        assertNotNull(result.reminderAt)
        val actual = Calendar.getInstance().apply { timeInMillis = result.reminderAt!! }
        assertEquals(8, actual.get(Calendar.HOUR_OF_DAY))
    }

    @Test
    fun `в следующую среду`() {
        // Сегодня понедельник → следующая среда = 15 апреля (следующая неделя)
        assertTimestamp("Встреча в следующую среду", 2026, 4, 15, 9, 0)
    }

    @Test
    fun `в субботу в 10 утра`() {
        // Ближайшая суббота от понедельника = 11 апреля
        assertTimestamp("Рынок в субботу в 10 утра", 2026, 4, 11, 10, 0)
    }
}
