package com.napominator.nlp

import java.util.Calendar
import java.util.Locale

/**
 * Извлекает дату и время из русскоязычной фразы.
 *
 * Примеры фраз:
 *  - "завтра в 15:00"
 *  - "в пятницу утром"
 *  - "через 2 часа"
 *  - "10 декабря в 18:30"
 *  - "в следующий вторник"
 *  - "послезавтра"
 *  - "через 3 дня"
 *  - "в 9 утра"
 *  - "сегодня вечером"
 */
object DateTimeExtractor {

    data class ExtractedDateTime(
        /** Unix timestamp (мс) или null если не удалось распознать */
        val timestamp: Long?,
        /** true если из фразы удалось извлечь конкретное время */
        val hasTime: Boolean
    )

    private val MONTHS = mapOf(
        "января" to 1, "февраля" to 2, "марта" to 3,
        "апреля" to 4, "мая" to 5, "июня" to 6,
        "июля" to 7, "августа" to 8, "сентября" to 9,
        "октября" to 10, "ноября" to 11, "декабря" to 12
    )

    private val WEEKDAYS = mapOf(
        "понедельник" to Calendar.MONDAY,
        "понедельника" to Calendar.MONDAY,
        "вторник" to Calendar.TUESDAY,
        "вторника" to Calendar.TUESDAY,
        "среда" to Calendar.WEDNESDAY,
        "среду" to Calendar.WEDNESDAY,
        "среды" to Calendar.WEDNESDAY,
        "четверг" to Calendar.THURSDAY,
        "четверга" to Calendar.THURSDAY,
        "пятница" to Calendar.FRIDAY,
        "пятницу" to Calendar.FRIDAY,
        "пятницы" to Calendar.FRIDAY,
        "суббота" to Calendar.SATURDAY,
        "субботу" to Calendar.SATURDAY,
        "субботы" to Calendar.SATURDAY,
        "воскресенье" to Calendar.SUNDAY,
        "воскресенья" to Calendar.SUNDAY
    )

    /** Основная точка входа */
    fun extract(text: String, now: Calendar = Calendar.getInstance()): ExtractedDateTime {
        val lower = text.lowercase(Locale("ru"))

        val date = extractDate(lower, now)
        val time = extractTime(lower)

        if (date == null && time == null) {
            return ExtractedDateTime(timestamp = null, hasTime = false)
        }

        val cal = (date ?: cloneDay(now)).apply {
            if (time != null) {
                set(Calendar.HOUR_OF_DAY, time.first)
                set(Calendar.MINUTE, time.second)
                set(Calendar.SECOND, 0)
                set(Calendar.MILLISECOND, 0)
            } else {
                // Время не указано — ставим начало дня, флаг hasTime = false
                set(Calendar.HOUR_OF_DAY, 9)
                set(Calendar.MINUTE, 0)
                set(Calendar.SECOND, 0)
                set(Calendar.MILLISECOND, 0)
            }
        }

        // Если дата не указана, но время указано и уже прошло — переносим на завтра
        if (date == null && time != null && cal.timeInMillis < now.timeInMillis) {
            cal.add(Calendar.DAY_OF_YEAR, 1)
        }

        return ExtractedDateTime(
            timestamp = cal.timeInMillis,
            hasTime = time != null
        )
    }

    // ── Дата ──────────────────────────────────────────────────────────────────

    private fun extractDate(text: String, now: Calendar): Calendar? {
        // "через N минут/часов/дней"
        val throughRegex = Regex("""через\s+(\d+)\s+(минут[уы]?|час(?:а|ов)?|дн[еёяий]+|недел[юи])""")
        throughRegex.find(text)?.let { m ->
            val n = m.groupValues[1].toInt()
            val unit = m.groupValues[2]
            val cal = cloneNow(now)
            when {
                unit.startsWith("минут") -> cal.add(Calendar.MINUTE, n)
                unit.startsWith("час") -> cal.add(Calendar.HOUR_OF_DAY, n)
                unit.startsWith("дн") || unit.startsWith("ден") -> cal.add(Calendar.DAY_OF_YEAR, n)
                unit.startsWith("недел") -> cal.add(Calendar.WEEK_OF_YEAR, n)
            }
            return cal
        }

        // "послезавтра"
        if ("послезавтра" in text) {
            return cloneDay(now).also { it.add(Calendar.DAY_OF_YEAR, 2) }
        }

        // "завтра"
        if ("завтра" in text) {
            return cloneDay(now).also { it.add(Calendar.DAY_OF_YEAR, 1) }
        }

        // "сегодня"
        if ("сегодня" in text) {
            return cloneDay(now)
        }

        // "в следующий/следующую <день недели>"
        val nextWeekdayRegex = Regex("""следующ(?:ий|ую|ем)\s+(\w+)""")
        nextWeekdayRegex.find(text)?.let { m ->
            val dayName = m.groupValues[1]
            WEEKDAYS[dayName]?.let { dayOfWeek ->
                return nextWeekday(now, dayOfWeek, skipCurrentWeek = true)
            }
        }

        // "в <день недели>" / "в пятницу"
        for ((dayName, dayOfWeek) in WEEKDAYS) {
            val pattern = Regex("""(?:^|[\s,])(?:в\s+)?$dayName(?:\s|${'$'}|[,!.])""")
            if (pattern.containsMatchIn(text)) {
                return nextWeekday(now, dayOfWeek, skipCurrentWeek = false)
            }
        }

        // "10 декабря" / "10-го декабря"
        val dateRegex = Regex("""(\d{1,2})(?:-го)?\s+(${MONTHS.keys.joinToString("|")})""")
        dateRegex.find(text)?.let { m ->
            val day = m.groupValues[1].toInt()
            val month = MONTHS[m.groupValues[2]] ?: return@let
            val cal = cloneDay(now).apply {
                set(Calendar.MONTH, month - 1)
                set(Calendar.DAY_OF_MONTH, day)
            }
            // Если дата уже прошла — следующий год
            if (cal.timeInMillis < now.timeInMillis) cal.add(Calendar.YEAR, 1)
            return cal
        }

        // "DD.MM" или "DD/MM"
        val numericDateRegex = Regex("""(\d{1,2})[./](\d{1,2})""")
        numericDateRegex.find(text)?.let { m ->
            val day = m.groupValues[1].toInt()
            val month = m.groupValues[2].toInt()
            if (day in 1..31 && month in 1..12) {
                val cal = cloneDay(now).apply {
                    set(Calendar.MONTH, month - 1)
                    set(Calendar.DAY_OF_MONTH, day)
                }
                if (cal.timeInMillis < now.timeInMillis) cal.add(Calendar.YEAR, 1)
                return cal
            }
        }

        return null
    }

    // ── Время ─────────────────────────────────────────────────────────────────

    /** Возвращает (hours, minutes) или null */
    private fun extractTime(text: String): Pair<Int, Int>? {
        // "в 15:30" / "в 9:05"
        val colonRegex = Regex("""(?:в\s+)?(\d{1,2}):(\d{2})""")
        colonRegex.find(text)?.let { m ->
            val h = m.groupValues[1].toInt()
            val min = m.groupValues[2].toInt()
            if (h in 0..23 && min in 0..59) return h to min
        }

        // "в 15 часов" / "в 9 часов"
        val hoursRegex = Regex("""в\s+(\d{1,2})\s+час""")
        hoursRegex.find(text)?.let { m ->
            val h = m.groupValues[1].toInt()
            if (h in 0..23) return h to 0
        }

        // "в 9 утра" / "в 3 ночи" / "в 7 вечера"
        val amPmRegex = Regex("""в\s+(\d{1,2})\s+(утра|утром|дня|вечера|вечером|ночи|ночью)""")
        amPmRegex.find(text)?.let { m ->
            var h = m.groupValues[1].toInt()
            val period = m.groupValues[2]
            h = when {
                period in setOf("вечера", "вечером") && h < 12 -> h + 12
                period in setOf("ночи", "ночью") && h < 6 -> h  // 1-5 ночи — это ночь
                period in setOf("ночи", "ночью") && h >= 6 -> h + 12  // редкий случай
                period == "дня" && h < 12 -> h + 12
                else -> h
            }
            if (h in 0..23) return h to 0
        }

        // Именованное время суток (без цифр)
        return when {
            "ночью" in text || "ночи" in text -> 0 to 0
            "утром" in text || "утра" in text -> 9 to 0
            "в обед" in text || "обеда" in text -> 13 to 0
            "днём" in text || "днем" in text -> 13 to 0
            "вечером" in text || "вечера" in text -> 18 to 0
            else -> null
        }
    }

    // ── Вспомогательные функции ───────────────────────────────────────────────

    /** Ближайший будущий день недели */
    private fun nextWeekday(now: Calendar, dayOfWeek: Int, skipCurrentWeek: Boolean): Calendar {
        val cal = cloneDay(now)
        val todayDow = cal.get(Calendar.DAY_OF_WEEK)
        var daysToAdd = (dayOfWeek - todayDow + 7) % 7
        if (daysToAdd == 0 && skipCurrentWeek) daysToAdd = 7
        if (daysToAdd == 0) daysToAdd = 7  // "в пятницу" когда сегодня пятница → следующая пятница
        cal.add(Calendar.DAY_OF_YEAR, daysToAdd)
        return cal
    }

    /** Копия Calendar с обнулёнными часами/минутами/секундами */
    private fun cloneDay(cal: Calendar): Calendar = (cal.clone() as Calendar).apply {
        set(Calendar.HOUR_OF_DAY, 0)
        set(Calendar.MINUTE, 0)
        set(Calendar.SECOND, 0)
        set(Calendar.MILLISECOND, 0)
    }

    /** Полная копия Calendar (для "через N ...") */
    private fun cloneNow(cal: Calendar): Calendar = cal.clone() as Calendar
}
