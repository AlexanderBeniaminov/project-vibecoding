package com.napominator.alarm

import java.util.Calendar
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Вычисляет следующую дату срабатывания по RRULE (RFC 5545).
 * Поддерживает базовые паттерны без внешних библиотек.
 */
@Singleton
class RRuleScheduler @Inject constructor() {

    /**
     * Возвращает следующий Unix timestamp (мс) после [currentTs] по правилу [rrule].
     * Возвращает null если rrule не распознан или не поддерживается.
     */
    fun nextOccurrence(currentTs: Long, rrule: String): Long? {
        val cal = Calendar.getInstance().apply { timeInMillis = currentTs }
        return when {
            rrule == "FREQ=DAILY" -> {
                cal.add(Calendar.DAY_OF_YEAR, 1)
                cal.timeInMillis
            }
            rrule == "FREQ=WEEKLY" -> {
                cal.add(Calendar.WEEK_OF_YEAR, 1)
                cal.timeInMillis
            }
            rrule == "FREQ=MONTHLY" -> {
                cal.add(Calendar.MONTH, 1)
                cal.timeInMillis
            }
            rrule == "FREQ=YEARLY" -> {
                cal.add(Calendar.YEAR, 1)
                cal.timeInMillis
            }
            rrule.startsWith("FREQ=DAILY;INTERVAL=") -> {
                val n = rrule.removePrefix("FREQ=DAILY;INTERVAL=").toIntOrNull() ?: 1
                cal.add(Calendar.DAY_OF_YEAR, n)
                cal.timeInMillis
            }
            rrule.startsWith("FREQ=WEEKLY;INTERVAL=") -> {
                val n = rrule.removePrefix("FREQ=WEEKLY;INTERVAL=").toIntOrNull() ?: 1
                cal.add(Calendar.WEEK_OF_YEAR, n)
                cal.timeInMillis
            }
            // По будням: MO,TU,WE,TH,FR
            rrule == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR" -> {
                cal.add(Calendar.DAY_OF_YEAR, 1)
                while (cal.get(Calendar.DAY_OF_WEEK) in listOf(Calendar.SATURDAY, Calendar.SUNDAY)) {
                    cal.add(Calendar.DAY_OF_YEAR, 1)
                }
                cal.timeInMillis
            }
            // По выходным: SA,SU
            rrule == "FREQ=WEEKLY;BYDAY=SA,SU" -> {
                cal.add(Calendar.DAY_OF_YEAR, 1)
                while (cal.get(Calendar.DAY_OF_WEEK) !in listOf(Calendar.SATURDAY, Calendar.SUNDAY)) {
                    cal.add(Calendar.DAY_OF_YEAR, 1)
                }
                cal.timeInMillis
            }
            // Конкретный день недели: FREQ=WEEKLY;BYDAY=MO (или TU, WE, ...)
            rrule.startsWith("FREQ=WEEKLY;BYDAY=") -> {
                val byDay = rrule.removePrefix("FREQ=WEEKLY;BYDAY=")
                val targetDow = parseSingleDay(byDay)
                if (targetDow != null) {
                    cal.add(Calendar.DAY_OF_YEAR, 1)
                    while (cal.get(Calendar.DAY_OF_WEEK) != targetDow) {
                        cal.add(Calendar.DAY_OF_YEAR, 1)
                    }
                    cal.timeInMillis
                } else {
                    // Несколько дней — берём следующее вхождение через неделю (упрощение)
                    cal.add(Calendar.WEEK_OF_YEAR, 1)
                    cal.timeInMillis
                }
            }
            else -> null
        }
    }

    private fun parseSingleDay(day: String): Int? = when (day.uppercase()) {
        "MO" -> Calendar.MONDAY
        "TU" -> Calendar.TUESDAY
        "WE" -> Calendar.WEDNESDAY
        "TH" -> Calendar.THURSDAY
        "FR" -> Calendar.FRIDAY
        "SA" -> Calendar.SATURDAY
        "SU" -> Calendar.SUNDAY
        else -> null
    }
}
