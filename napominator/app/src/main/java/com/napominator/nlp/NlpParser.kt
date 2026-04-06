package com.napominator.nlp

import java.util.Calendar
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Главный NLP-парсер: из распознанного текста извлекает задачу.
 *
 * Возвращает [ParsedTask] с:
 *  - [ParsedTask.title]      — очищенный текст задачи (без дат/времени/повторений)
 *  - [ParsedTask.reminderAt] — Unix timestamp (мс) или null
 *  - [ParsedTask.rrule]      — RRULE строка RFC 5545 или null
 *  - [ParsedTask.hasNoTime]  — true если дата/время не найдены
 */
@Singleton
class NlpParser @Inject constructor() {

    data class ParsedTask(
        val title: String,
        val reminderAt: Long?,
        val rrule: String?,
        val hasNoTime: Boolean
    )

    fun parse(text: String, now: Calendar = Calendar.getInstance()): ParsedTask {
        val rrule = RepeatPatternExtractor.extract(text)
        val dateTime = DateTimeExtractor.extract(text, now)

        val cleanTitle = cleanTitle(text)

        return ParsedTask(
            title = cleanTitle.ifBlank { text.trim() },
            reminderAt = dateTime.timestamp,
            rrule = rrule,
            hasNoTime = dateTime.timestamp == null
        )
    }

    /**
     * Убирает из текста даты, время, слова повторения — оставляет суть задачи.
     */
    private fun cleanTitle(text: String): String {
        var result = text

        // Удаляем числовые даты "10 декабря", "15-го числа", "DD.MM"
        result = result.replace(
            Regex("""(\d{1,2})(?:-го)?\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)""",
                RegexOption.IGNORE_CASE), "")
        result = result.replace(Regex("""\d{1,2}[./]\d{1,2}"""), "")
        result = result.replace(Regex("""\d{1,2}[-–]?(?:го|е|й)\s+числа?"""), "")

        // Удаляем время "в 15:30", "в 9 утра", "в обед"
        result = result.replace(Regex("""(?:в\s+)?\d{1,2}:\d{2}"""), "")
        result = result.replace(
            Regex("""в\s+\d{1,2}\s+(?:утра|утром|дня|вечера|вечером|ночи|ночью|часов|час[а]?)"""), "")
        result = result.replace(Regex("""(?:^|\s)в\s+(?:обед|полдень)"""), "")

        // Удаляем относительное время "через 2 часа", "через 30 минут"
        result = result.replace(
            Regex("""через\s+\d+\s+(?:минут[уы]?|час(?:а|ов)?|дн[еёяий]+|недел[юи])"""), "")

        // Удаляем дни недели / относительные слова
        result = result.replace(
            Regex("""(?:^|\s)(?:в\s+)?(?:сегодня|завтра|послезавтра|вчера)"""), "")
        result = result.replace(
            Regex("""(?:следующ(?:ий|ую|ем)\s+)?(?:понедельник[а-я]*|вторник[а-я]*|среду?[а-я]*|четверг[а-я]*|пятниц[а-я]*|суббот[а-я]*|воскресень[а-я]*)""",
                RegexOption.IGNORE_CASE), "")
        result = result.replace(Regex("""(?:^|\s)следующ(?:ий|ую|ем)\s+"""), " ")

        // Удаляем слова повторения
        result = result.replace(
            Regex("""ежедневн\w*|еженедельн\w*|ежемесячн\w*|ежегодн\w*"""), "")
        result = result.replace(
            Regex("""по\s+(?:будням|выходным)"""), "")
        result = result.replace(
            Regex("""каждый?\s+(?:день|неделю|месяц|год|\w+|и\s+\w+)+"""), "")
        result = result.replace(
            Regex("""последн(?:ий|его)\s+день"""), "")

        // Удаляем предлоги/слова, оставшиеся висеть
        result = result.replace(Regex("""(?:^|\s)(?:в|на|до|утром|вечером|ночью|днём|днем)(?:\s|$)"""), " ")

        // Убираем лишние пробелы и знаки
        return result.replace(Regex("""\s{2,}"""), " ").trim().trimEnd(',', '.', ' ')
    }
}
