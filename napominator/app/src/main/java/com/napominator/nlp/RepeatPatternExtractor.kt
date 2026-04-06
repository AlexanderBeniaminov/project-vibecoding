package com.napominator.nlp

import java.util.Locale

/**
 * Конвертирует русскоязычные фразы повторения в строки RRULE (RFC 5545).
 *
 * Примеры:
 *  "каждый день"              → "FREQ=DAILY"
 *  "каждую неделю"            → "FREQ=WEEKLY"
 *  "каждый месяц"             → "FREQ=MONTHLY"
 *  "каждый год"               → "FREQ=YEARLY"
 *  "каждые 2 дня"             → "FREQ=DAILY;INTERVAL=2"
 *  "каждые 3 недели"          → "FREQ=WEEKLY;INTERVAL=3"
 *  "каждый понедельник"       → "FREQ=WEEKLY;BYDAY=MO"
 *  "каждую пятницу"           → "FREQ=WEEKLY;BYDAY=FR"
 *  "по будням"                → "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
 *  "по выходным"              → "FREQ=WEEKLY;BYDAY=SA,SU"
 *  "каждый пн и пт"           → "FREQ=WEEKLY;BYDAY=MO,FR"
 *  "каждый месяц 15-го"       → "FREQ=MONTHLY;BYMONTHDAY=15"
 *  "каждый последний день"    → "FREQ=MONTHLY;BYMONTHDAY=-1"
 *  "ежедневно"                → "FREQ=DAILY"
 *  "еженедельно"              → "FREQ=WEEKLY"
 *  "ежемесячно"               → "FREQ=MONTHLY"
 */
object RepeatPatternExtractor {

    private val WEEKDAY_CODES = mapOf(
        "понедельник" to "MO", "понедельника" to "MO",
        "вторник" to "TU", "вторника" to "TU",
        "среда" to "WE", "среду" to "WE", "среды" to "WE",
        "четверг" to "TH", "четверга" to "TH",
        "пятница" to "FR", "пятницу" to "FR", "пятницы" to "FR",
        "суббота" to "SA", "субботу" to "SA", "субботы" to "SA",
        "воскресенье" to "SU", "воскресенья" to "SU",
        // Сокращения
        "пн" to "MO", "вт" to "TU", "ср" to "WE",
        "чт" to "TH", "пт" to "FR", "сб" to "SA", "вс" to "SU"
    )

    /** @return RRULE-строка или null если повторение не найдено */
    fun extract(text: String): String? {
        val lower = text.lowercase(Locale("ru"))

        // "ежедневно" / "ежедневный"
        if (Regex("""ежедневн""").containsMatchIn(lower)) return "FREQ=DAILY"

        // "еженедельно"
        if (Regex("""еженедельн""").containsMatchIn(lower)) return "FREQ=WEEKLY"

        // "ежемесячно"
        if (Regex("""ежемесячн""").containsMatchIn(lower)) return "FREQ=MONTHLY"

        // "ежегодно" / "каждый год"
        if (Regex("""ежегодн""").containsMatchIn(lower) ||
            Regex("""каждый\s+год""").containsMatchIn(lower)) return "FREQ=YEARLY"

        // "по будням"
        if (Regex("""по\s+будням""").containsMatchIn(lower)) {
            return "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
        }

        // "по выходным"
        if (Regex("""по\s+выходным""").containsMatchIn(lower)) {
            return "FREQ=WEEKLY;BYDAY=SA,SU"
        }

        // "каждый последний день месяца"
        if (Regex("""последн(?:ий|его)\s+день""").containsMatchIn(lower)) {
            return "FREQ=MONTHLY;BYMONTHDAY=-1"
        }

        // "каждый месяц 15-го" / "каждое 15-е"
        val monthdayRegex = Regex("""(?:каждый\s+месяц\s+|каждое\s+)?(\d{1,2})[-–]?(?:го|е|й)?\s+числа?""")
        monthdayRegex.find(lower)?.let { m ->
            val day = m.groupValues[1].toInt()
            if (day in 1..31) return "FREQ=MONTHLY;BYMONTHDAY=$day"
        }

        // "каждые N дней/недель/месяцев"
        val intervalRegex = Regex("""каждые?\s+(\d+)\s+(дн[еёяий]+|недел[юиь]+|месяц[аов]*)""")
        intervalRegex.find(lower)?.let { m ->
            val n = m.groupValues[1].toInt()
            val unit = m.groupValues[2]
            return when {
                unit.startsWith("дн") || unit.startsWith("ден") ->
                    if (n == 1) "FREQ=DAILY" else "FREQ=DAILY;INTERVAL=$n"
                unit.startsWith("недел") ->
                    if (n == 1) "FREQ=WEEKLY" else "FREQ=WEEKLY;INTERVAL=$n"
                unit.startsWith("месяц") ->
                    if (n == 1) "FREQ=MONTHLY" else "FREQ=MONTHLY;INTERVAL=$n"
                else -> null
            }
        }

        // "каждый понедельник и пятницу" / "каждый пн, ср, пт"
        if (Regex("""каждый|каждую|каждое""").containsMatchIn(lower)) {
            val days = mutableListOf<String>()
            for ((dayName, code) in WEEKDAY_CODES) {
                if (dayName in lower) days.add(code)
            }
            val uniqueDays = days.distinct()
            if (uniqueDays.isNotEmpty()) {
                return if (uniqueDays.size == 1) "FREQ=WEEKLY;BYDAY=${uniqueDays[0]}"
                else "FREQ=WEEKLY;BYDAY=${uniqueDays.joinToString(",")}"
            }

            // "каждый день"
            if (Regex("""каждый\s+день|каждые\s+сутки""").containsMatchIn(lower)) return "FREQ=DAILY"

            // "каждую неделю"
            if (Regex("""каждую\s+неделю|каждой\s+недели""").containsMatchIn(lower)) return "FREQ=WEEKLY"

            // "каждый месяц"
            if (Regex("""каждый\s+месяц""").containsMatchIn(lower)) return "FREQ=MONTHLY"
        }

        return null
    }
}
