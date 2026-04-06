# PROJECT.md — Napominator

Технический документ для разработки. Источник требований: `features_v2.md`.

---

## ЦЕЛЬ ПРОДУКТА

Android-приложение-напоминатель с голосовым вводом.
Целевое устройство: **Huawei Nova 11** (HarmonyOS/EMUI, без Google Play Services).
Все данные хранятся локально (Room). Сервер не нужен до v2.

---

## ПРЕДВАРИТЕЛЬНЫЕ ТРЕБОВАНИЯ ПЕРЕД РАЗРАБОТКОЙ

### Huawei Developer Account (обязательно до Этапа 2)

HMS ML Kit Speech и HMS Location Kit требуют регистрации приложения в Huawei AppGallery Connect.

Шаги:
1. Зарегистрировать аккаунт разработчика на `developer.huawei.com`
2. Создать приложение в AppGallery Connect → получить `agconnect-services.json`
3. Поместить `agconnect-services.json` в `app/` директорию
4. Включить нужные HMS API в консоли: ML Kit, Location Kit, Map Kit
5. Настроить подпись APK в `build.gradle` (SHA256 fingerprint)

**Без этих шагов HMS SDK будет падать с runtime exception при любом вызове.**

### Google OAuth2 (для CalDAV, Этап 16)

1. Зарегистрировать проект в Google Cloud Console
2. Включить CalDAV API (Google Calendar API)
3. Создать OAuth2 Client ID типа "Android" с SHA256 fingerprint
4. Сохранить client_id в `local.properties` (не в git!)

### Яндекс OAuth2 (для CalDAV, Этап 17)

1. Зарегистрировать приложение на `oauth.yandex.ru`
2. Получить `client_id` и `client_secret`
3. Сохранить в `local.properties`

---

## ТЕХНИЧЕСКИЙ СТЕК

### Платформа
- **Язык:** Kotlin
- **Min SDK:** 26 (Android 8.0)
- **Target SDK:** 34
- **Архитектура:** MVVM + Repository
- **DI:** Hilt
- **Navigation:** Navigation Component (Single Activity)

### Локальные данные
- **БД:** Room (SQLite)
- **Preferences:** DataStore

### Распознавание речи
- **Онлайн (основной):** HMS ML Kit Speech Recognition — русский язык
- **Офлайн (резерв):** Vosk — модель `vosk-model-small-ru` (~50 МБ)
- **Стратегия выбора:** HMS если есть сеть И HMS доступен; иначе Vosk
- **Vosk модель:** скачивается по требованию при первом офлайн-использовании, не включается в APK. Хранится в `filesDir`. Показывать progress UI при скачивании.

### Уведомления и будильники
- **`AlarmManager.setAlarmClock()`** — для всех точных будильников (не убивается Huawei)
- **`FOREGROUND_SERVICE_TYPE_SPECIAL_USE`** — обязательно для Android 14+ в манифесте
- **Foreground Service** — держит процесс живым
- **Два Notification Channel:** `CHANNEL_REMINDER` (обычные) и `CHANNEL_PERSISTENT` (настойчивые, importance HIGH)
- **HMS Push Kit** — зарезервировано для v2

### Геолокация
- **HMS Location Kit** — Geofencing API
- **HMS Map Kit** — выбор места на карте
- Геофенсы перерегистрируются после BOOT_COMPLETED

### Календарная интеграция
- **Протокол:** CalDAV (RFC 4791)
- **Формат событий:** iCalendar (RFC 5545)
- **Библиотека:** `ical4android` + `OkHttp`
- **Авторизация:** OAuth2 через Custom Tabs (не WebView — WebView хуже UX и запрещён Google)

### UI
- **Jetpack Compose** + Material Design 3
- **Виджеты:** `AppWidgetProvider` (микрофон) + Compose Glance (список)
- **Haptics:** `VibrationEffect` для подтверждения действий

---

## СТРУКТУРА ПРОЕКТА

```
napominator/
├── app/
│   └── src/main/
│       ├── data/
│       │   ├── db/
│       │   │   ├── TaskDao.kt
│       │   │   ├── TaskEntity.kt
│       │   │   └── AppDatabase.kt
│       │   ├── repository/
│       │   │   ├── TaskRepository.kt
│       │   │   └── CalendarRepository.kt
│       │   └── prefs/
│       │       └── AppPreferences.kt
│       ├── domain/
│       │   ├── model/
│       │   │   └── Task.kt
│       │   └── nlp/
│       │       ├── NlpParser.kt
│       │       ├── DateTimeExtractor.kt
│       │       └── RepeatPatternExtractor.kt
│       ├── speech/
│       │   ├── SpeechRecognitionManager.kt
│       │   ├── HmsSpeechRecognizer.kt
│       │   ├── VoskSpeechRecognizer.kt
│       │   └── VoskModelDownloader.kt      ← скачивание модели с UI
│       ├── alarm/
│       │   ├── AlarmScheduler.kt
│       │   ├── AlarmReceiver.kt
│       │   ├── BootReceiver.kt             ← восстановление будильников И геофенсов
│       │   └── ReminderForegroundService.kt
│       ├── notification/
│       │   ├── NotificationBuilder.kt
│       │   ├── NotificationActionReceiver.kt
│       │   └── QuietHoursManager.kt        ← тихие часы
│       ├── geofence/
│       │   ├── GeofenceManager.kt
│       │   └── GeofenceReceiver.kt
│       ├── calendar/
│       │   ├── CalDavClient.kt
│       │   ├── TaskToVEventMapper.kt
│       │   ├── GoogleCalendarSync.kt
│       │   └── YandexCalendarSync.kt
│       ├── ui/
│       │   ├── main/          ← список задач
│       │   ├── record/        ← запись голоса
│       │   ├── confirm/       ← экран подтверждения
│       │   ├── task/          ← редактирование задачи
│       │   ├── settings/      ← настройки
│       │   ├── onboarding/    ← батарея Huawei + первый запуск
│       │   └── theme/
│       └── widget/
│           ├── MicButtonWidget.kt
│           └── TaskListWidget.kt
```

---

## МОДЕЛЬ ДАННЫХ

```kotlin
@Entity(tableName = "tasks")
data class TaskEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val title: String,
    val createdAt: Long,                   // Unix timestamp мс
    val reminderAt: Long?,                 // Unix timestamp мс, null = нет времени
    // RRULE строка по RFC 5545: "FREQ=WEEKLY;BYDAY=MO,FR" и т.д.
    // null = не повторяется
    val rrule: String?,
    val repeatUntil: Long?,                // Unix timestamp окончания, null = бесконечно
    val isCompleted: Boolean = false,
    val completedAt: Long? = null,
    // Геолокация
    val geofenceLat: Double? = null,
    val geofenceLon: Double? = null,
    val geofenceRadius: Int? = null,       // метры
    val geofenceTrigger: String? = null,   // "ENTER" | "EXIT"
    val geofenceMaxPerDay: Int? = null,    // лимит срабатываний в день
    val geofenceWindowStart: Int? = null,  // минуты с 00:00 (напр. 540 = 09:00)
    val geofenceWindowEnd: Int? = null,    // минуты с 00:00 (напр. 1320 = 22:00)
    // Настойчивость
    val snoozeIntervalMinutes: Int? = null, // null = без повторов
    val snoozeMaxCount: Int? = null,        // null = без ограничений
    val snoozePausesDuringQuietHours: Boolean = true,
    // Синхронизация
    val calendarEventId: String? = null,   // CalDAV event UID после синхронизации
    val calendarEtag: String? = null       // ETag для обнаружения конфликтов
)
```

**Почему `rrule: String?` вместо кастомного формата:**
Стандарт RFC 5545 RRULE используется CalDAV напрямую. Никакой конвертации не нужно. Парсеры RRULE существуют в виде готовых библиотек.

---

## КЛЮЧЕВЫЕ ТЕХНИЧЕСКИЕ РЕШЕНИЯ

### Разрешения — правильный выбор

Использовать **только одно** из двух:
- `USE_EXACT_ALARM` — автоматически даётся, не требует диалога, Android 13+
- `SCHEDULE_EXACT_ALARM` — требует системного диалога, Android 12+

**Решение:** использовать `USE_EXACT_ALARM` (Android 13+) с fallback на `SCHEDULE_EXACT_ALARM` для Android 12. Не объявлять оба одновременно.

```xml
<!-- AndroidManifest.xml -->
<uses-permission android:name="android.permission.USE_EXACT_ALARM" />
<!-- fallback для Android 12 -->
<uses-permission android:name="android.permission.SCHEDULE_EXACT_ALARM"
    android:maxSdkVersion="32" />
```

### Foreground Service для Android 14+

```xml
<service
    android:name=".alarm.ReminderForegroundService"
    android:foregroundServiceType="specialUse"
    android:exported="false">
    <property
        android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"
        android:value="reminder_scheduling"/>
</service>
```

### NLP: RRULE из текста

Прямая генерация RRULE строки из ключевых слов:

```kotlin
fun parseRepeat(text: String): String? {
    return when {
        text.contains(Regex("каждый день|ежедневно"))         -> "FREQ=DAILY"
        text.contains(Regex("каждую неделю|еженедельно"))    -> "FREQ=WEEKLY"
        text.contains(Regex("каждый месяц|ежемесячно"))      -> "FREQ=MONTHLY"
        text.contains(Regex("каждые (\\d+) (день|дня|дней)")) -> {
            val n = ...; "FREQ=DAILY;INTERVAL=$n"
        }
        // ... и т.д.
        else -> null
    }
}
```

### CalDAV: обработка конфликтов через ETag

```kotlin
// При обновлении события в CalDAV
// Если сервер вернул 412 Precondition Failed — ETag устарел
// Стратегия: Last Write Wins (последняя запись побеждает)
// Загрузить свежее событие с сервера, обновить локально, повторить PUT
```

### Тихие часы

```kotlin
class QuietHoursManager(private val prefs: AppPreferences) {
    fun isQuietNow(): Boolean {
        val now = LocalTime.now()
        val start = prefs.quietHoursStart  // например 23:00
        val end = prefs.quietHoursEnd      // например 08:00
        return if (start < end) now in start..end
               else now >= start || now <= end  // переход через полночь
    }
}
// В AlarmReceiver: если isQuietNow() && !task.isCritical → не показывать повтор
// Запланировать следующий повтор на конец тихих часов
```

### Геофенсы: восстановление после перезагрузки

```kotlin
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            // 1. Перепланировать все активные AlarmManager задачи
            taskRepository.getActiveTasksWithReminder().forEach {
                alarmScheduler.schedule(it)
            }
            // 2. Перерегистрировать все геофенсы
            taskRepository.getActiveGeofenceTasks().forEach {
                geofenceManager.register(it)
            }
        }
    }
}
```

---

## РАЗРЕШЕНИЯ В ANDROIDMANIFEST

```xml
<!-- Уведомления -->
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
<uses-permission android:name="android.permission.USE_EXACT_ALARM" />
<uses-permission android:name="android.permission.SCHEDULE_EXACT_ALARM"
    android:maxSdkVersion="32" />
<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_SPECIAL_USE" />

<!-- Микрофон -->
<uses-permission android:name="android.permission.RECORD_AUDIO" />

<!-- Геолокация -->
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_BACKGROUND_LOCATION" />

<!-- Сеть -->
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />

<!-- Вибрация -->
<uses-permission android:name="android.permission.VIBRATE" />
```

**`ACCESS_BACKGROUND_LOCATION`**: в Android 10+ запрашивается отдельным диалогом после основного. Объяснить: "нужно для геолокационных напоминаний когда приложение закрыто".

---

## ЗАВИСИМОСТИ (build.gradle)

```kotlin
// Room
implementation("androidx.room:room-runtime:2.6.1")
implementation("androidx.room:room-ktx:2.6.1")
ksp("androidx.room:room-compiler:2.6.1")

// Hilt
implementation("com.google.dagger:hilt-android:2.51")
ksp("com.google.dagger:hilt-android-compiler:2.51")

// Compose
implementation(platform("androidx.compose:compose-bom:2024.09.00"))
implementation("androidx.compose.ui:ui")
implementation("androidx.compose.material3:material3")
implementation("androidx.compose.animation:animation")
implementation("androidx.glance:glance-appwidget:1.1.0")

// Navigation
implementation("androidx.navigation:navigation-compose:2.8.0")

// DataStore
implementation("androidx.datastore:datastore-preferences:1.1.1")

// Vosk офлайн ASR
implementation("net.java.dev.jna:jna:5.13.0@aar")
implementation("com.alphacephei:vosk-android:0.3.47")

// CalDAV / iCalendar
implementation("at.bitfire.ical4android:ical4android:1.2.0")
implementation("com.squareup.okhttp3:okhttp:4.12.0")

// HMS (только для Huawei — требует agconnect-services.json)
implementation("com.huawei.hms:ml-computer-voice-asr:3.11.0.301")
implementation("com.huawei.hms:location:6.12.0.300")
implementation("com.huawei.hms:maps:6.12.1.301")
implementation("com.huawei.agconnect:agconnect-core:1.9.1.301")

// Coroutines
implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.0")

// Тестирование
testImplementation("androidx.room:room-testing:2.6.1")
testImplementation("junit:junit:4.13.2")
androidTestImplementation("androidx.test.espresso:espresso-core:3.6.1")
```

---

## ИЗВЕСТНЫЕ РИСКИ

| Риск | Решение |
|---|---|
| Huawei убивает процесс | `setAlarmClock()` + onboarding батареи |
| HMS ML Kit требует agconnect-services.json | Настроить до начала разработки (этап 0.0) |
| Vosk 50 МБ = нагрузка при первом запуске | Скачивать по требованию + прогресс UI |
| RRULE парсинг для русского языка | Regex + unit-тесты покрытием 95%+ |
| CalDAV конфликты | ETag + Last Write Wins |
| ACCESS_BACKGROUND_LOCATION отклонено | Геофенсы отключаются gracefully с пояснением |
| Geofence исчезает после перезагрузки | BootReceiver перерегистрирует все |
| Compose Glance ограничения для виджетов | "Ещё N задач" вместо скролла |
| Android 14 FGS требует тип | `FOREGROUND_SERVICE_TYPE_SPECIAL_USE` |

---

*Обновлять при каждом изменении стека, структуры или принятии нового архитектурного решения.*
