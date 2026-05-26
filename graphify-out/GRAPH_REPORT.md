# Graph Report - .  (2026-04-21)

## Corpus Check
- 134 files · ~120,206 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 822 nodes · 1098 edges · 77 communities detected
- Extraction: 80% EXTRACTED · 20% INFERRED · 0% AMBIGUOUS · INFERRED: 225 edges (avg confidence: 0.76)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]

## God Nodes (most connected - your core abstractions)
1. `TaskDaoTest` - 28 edges
2. `MaxBot` - 21 edges
3. `TaskRepository` - 21 edges
4. `BaseScraper` - 20 edges
5. `NlpParserTest` - 20 edges
6. `TaskDao` - 19 edges
7. `Error` - 19 edges
8. `run()` - 14 edges
9. `AppPreferences` - 13 edges
10. `get_conn()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `collect_daily_data_iiko_web()` --calls--> `Error`  [INFERRED]
  hotel-restaurant-processes/scripts/iiko_client.py → napominator/app/src/main/java/com/napominator/data/backup/BackupManager.kt
- `update_sheets()` --calls--> `Error`  [INFERRED]
  obyavlenia/sheets.py → napominator/app/src/main/java/com/napominator/data/backup/BackupManager.kt
- `run_all_scrapers()` --calls--> `Error`  [INFERRED]
  obyavlenia/main.py → napominator/app/src/main/java/com/napominator/data/backup/BackupManager.kt
- `run()` --calls--> `Error`  [INFERRED]
  obyavlenia/main.py → napominator/app/src/main/java/com/napominator/data/backup/BackupManager.kt
- `run_scheduled()` --calls--> `Error`  [INFERRED]
  obyavlenia/main.py → napominator/app/src/main/java/com/napominator/data/backup/BackupManager.kt

## Hyperedges (group relationships)
- **Губаха Automation Ecosystem** —  [INFERRED]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.0
Nodes (61): GET с retry и случайной задержкой. Возвращает Response или None., _get_area_config(), get_area_flags(), get_enabled_directions(), _get_enabled_include_keywords(), _get_exclude_keywords(), _load_config(), matches_exclude() (+53 more)

### Community 1 - "Community 1"
Cohesion: 0.0
Nodes (58): Error, _aggregate_weekly(), _alert_dev(), _build_owner_report(), _build_weekly_digest(), daily_collect(), daily_report(), _empty_weekly() (+50 more)

### Community 2 - "Community 2"
Cohesion: 0.0
Nodes (30): AlteraScraper, Парсер Альтера Инвест. https://alterainvest.ru/rus/products/275/ Карточки: .al-c, AvitoScraper, Парсер Авито — использует Playwright из-за JS-рендеринга и антибот защиты. При п, Запускает браузер в headless режиме, сохраняет сессию., BaseScraper, BebossScraper, Парсер БИБОСС через Playwright (сайт рендерит результаты через JS). Выбираем кат (+22 more)

### Community 3 - "Community 3"
Cohesion: 0.0
Nodes (39): enqueue_notification(), get_active_ids_by_source(), get_conn(), get_listing(), get_pending_notifications(), init_db(), insert_listing(), mark_notification_sent() (+31 more)

### Community 4 - "Community 4"
Cohesion: 0.0
Nodes (27): ABC, BaseScraper, Базовый класс парсера: ротация User-Agent, задержки, retry при 403/429, логирова, Наследуй этот класс для каждой площадки., site_delay(), check_config(), get_capacity(), Центральный конфиг: читает .env и предоставляет константы всему проекту. (+19 more)

### Community 5 - "Community 5"
Cohesion: 0.0
Nodes (21): diagnose_categories.py — диагностика категорий iiko для конкретных дат.  Запуск:, collect_daily_data(), collect_daily_data_iiko_web(), _date_filter(), get_token(), IikoWebSession, _olap_query(), iiko_client.py — клиент для iikoWeb OLAP.  Авторизация: POST /api/auth/login {lo (+13 more)

### Community 6 - "Community 6"
Cohesion: 0.0
Nodes (25): get_all_active(), fix_formats(), fix_row3_dates(), get_service(), get_sheet_name(), iso_week_date_range(), main(), Применяет к листу «Еженедельно»:   1. Числовые форматы для строк 4–96 (данные, к (+17 more)

### Community 7 - "Community 7"
Cohesion: 0.0
Nodes (1): TaskDaoTest

### Community 8 - "Community 8"
Cohesion: 0.0
Nodes (26): Александр Бениаминов, Альтера Инвест, Авито, Content Plan (апрель 2026), Лист Ежедневно, Лист Дашборд, Энтенс групп, GitHub Actions (+18 more)

### Community 9 - "Community 9"
Cohesion: 0.0
Nodes (1): TaskRepository

### Community 10 - "Community 10"
Cohesion: 0.0
Nodes (20): Агент 1 — Аналитик, Агент 2 — Стратег, Агент 3 — Диспетчер, AI-система ВК Губаха, Anthropic API (Claude), 33 Коттеджа, Google Apps Script, gspread Python library (+12 more)

### Community 11 - "Community 11"
Cohesion: 0.0
Nodes (1): TaskDao

### Community 12 - "Community 12"
Cohesion: 0.0
Nodes (1): NlpParserTest

### Community 13 - "Community 13"
Cohesion: 0.0
Nodes (8): DownloadingModel, Error, Idle, Processing, Recognized, Recording, RecordUiState, RecordViewModel

### Community 14 - "Community 14"
Cohesion: 0.0
Nodes (13): add_data_validation(), build_requests(), build_values(), get_service(), hide_rows(), main(), Читает KPI данные для нед.1-5 из 2025 и 2026., Возвращает список batchUpdate requests для форматирования. (+5 more)

### Community 15 - "Community 15"
Cohesion: 0.0
Nodes (2): AppPreferences, Keys

### Community 16 - "Community 16"
Cohesion: 0.0
Nodes (6): AudioRecorder, Error, Idle, Recording, State, Stopping

### Community 17 - "Community 17"
Cohesion: 0.0
Nodes (1): SettingsViewModel

### Community 18 - "Community 18"
Cohesion: 0.0
Nodes (6): Done, Downloading, Error, Extracting, Progress, VoskModelDownloader

### Community 19 - "Community 19"
Cohesion: 0.0
Nodes (7): Empty, Engine, Error, ModelNotInstalled, Result, SpeechRecognitionManager, Success

### Community 20 - "Community 20"
Cohesion: 0.0
Nodes (7): BackupState, BackupViewModel, Error, ExportSuccess, Idle, ImportSuccess, InProgress

### Community 21 - "Community 21"
Cohesion: 0.0
Nodes (0): 

### Community 22 - "Community 22"
Cohesion: 0.0
Nodes (2): ConfirmUiState, ConfirmViewModel

### Community 23 - "Community 23"
Cohesion: 0.0
Nodes (3): MainUiState, MainViewModel, TaskSection

### Community 24 - "Community 24"
Cohesion: 0.0
Nodes (6): BatteryOnboarding, Main, NewTask, Screen, Settings, TaskDetail

### Community 25 - "Community 25"
Cohesion: 0.0
Nodes (2): TaskDetailUiState, TaskDetailViewModel

### Community 26 - "Community 26"
Cohesion: 0.0
Nodes (6): Empty, Error, ModelNotInstalled, Result, Success, VoskRecognizer

### Community 27 - "Community 27"
Cohesion: 0.0
Nodes (2): DateTimeExtractor, ExtractedDateTime

### Community 28 - "Community 28"
Cohesion: 0.0
Nodes (9): CalDAV Protocol, Google Calendar, HMS ML Kit Speech, Huawei Nova 11, Jetpack Compose, Kotlin, Napominator App, Room Database (+1 more)

### Community 29 - "Community 29"
Cohesion: 0.0
Nodes (0): 

### Community 30 - "Community 30"
Cohesion: 0.0
Nodes (1): HapticFeedback

### Community 31 - "Community 31"
Cohesion: 0.0
Nodes (1): AlarmScheduler

### Community 32 - "Community 32"
Cohesion: 0.0
Nodes (3): BackupManager, ImportResult, Success

### Community 33 - "Community 33"
Cohesion: 0.0
Nodes (2): ReminderSheetActivity, SnoozeAction

### Community 34 - "Community 34"
Cohesion: 0.0
Nodes (0): 

### Community 35 - "Community 35"
Cohesion: 0.0
Nodes (0): 

### Community 36 - "Community 36"
Cohesion: 0.0
Nodes (1): NotificationBuilder

### Community 37 - "Community 37"
Cohesion: 0.0
Nodes (1): QuietHoursManager

### Community 38 - "Community 38"
Cohesion: 0.0
Nodes (1): DailySummaryScheduler

### Community 39 - "Community 39"
Cohesion: 0.0
Nodes (0): 

### Community 40 - "Community 40"
Cohesion: 0.0
Nodes (2): NlpParser, ParsedTask

### Community 41 - "Community 41"
Cohesion: 0.0
Nodes (1): Task

### Community 42 - "Community 42"
Cohesion: 0.0
Nodes (1): NapominatorApp

### Community 43 - "Community 43"
Cohesion: 0.0
Nodes (0): 

### Community 44 - "Community 44"
Cohesion: 0.0
Nodes (1): DatabaseModule

### Community 45 - "Community 45"
Cohesion: 0.0
Nodes (1): MicButtonWidget

### Community 46 - "Community 46"
Cohesion: 0.0
Nodes (1): RRuleScheduler

### Community 47 - "Community 47"
Cohesion: 0.0
Nodes (1): ReminderForegroundService

### Community 48 - "Community 48"
Cohesion: 0.0
Nodes (1): AppDatabase

### Community 49 - "Community 49"
Cohesion: 0.0
Nodes (4): ФЗ-315 (О СРО), СРО индустрии развлечений, СТО СРО-РИ-001, ТР ЕАЭС 038/2016

### Community 50 - "Community 50"
Cohesion: 0.0
Nodes (4): EntenS Group, EntenS Landing Page, GSAP 3 + ScrollTrigger, Lenis Smooth Scroll

### Community 51 - "Community 51"
Cohesion: 0.0
Nodes (1): MainActivity

### Community 52 - "Community 52"
Cohesion: 0.0
Nodes (1): RecordActivity

### Community 53 - "Community 53"
Cohesion: 0.0
Nodes (0): 

### Community 54 - "Community 54"
Cohesion: 0.0
Nodes (1): NetworkModule

### Community 55 - "Community 55"
Cohesion: 0.0
Nodes (1): TaskListWidget

### Community 56 - "Community 56"
Cohesion: 0.0
Nodes (1): DailySummaryBuilder

### Community 57 - "Community 57"
Cohesion: 0.0
Nodes (1): NotificationActionReceiver

### Community 58 - "Community 58"
Cohesion: 0.0
Nodes (1): RepeatPatternExtractor

### Community 59 - "Community 59"
Cohesion: 0.0
Nodes (1): DailySummaryReceiver

### Community 60 - "Community 60"
Cohesion: 0.0
Nodes (1): AlarmReceiver

### Community 61 - "Community 61"
Cohesion: 0.0
Nodes (1): BootReceiver

### Community 62 - "Community 62"
Cohesion: 0.0
Nodes (0): 

### Community 63 - "Community 63"
Cohesion: 0.0
Nodes (1): TaskEntity

### Community 64 - "Community 64"
Cohesion: 0.0
Nodes (0): 

### Community 65 - "Community 65"
Cohesion: 0.0
Nodes (0): 

### Community 66 - "Community 66"
Cohesion: 0.0
Nodes (1): Задержка между площадками.

### Community 67 - "Community 67"
Cohesion: 0.0
Nodes (1): Парсит площадку и возвращает список словарей с полями:         id, url, source,

### Community 68 - "Community 68"
Cohesion: 0.0
Nodes (0): 

### Community 69 - "Community 69"
Cohesion: 0.0
Nodes (0): 

### Community 70 - "Community 70"
Cohesion: 0.0
Nodes (0): 

### Community 71 - "Community 71"
Cohesion: 0.0
Nodes (1): max_bot.py

### Community 72 - "Community 72"
Cohesion: 0.0
Nodes (1): IAAPA (стандарты)

### Community 73 - "Community 73"
Cohesion: 0.0
Nodes (1): Skill: fullstack-developer

### Community 74 - "Community 74"
Cohesion: 0.0
Nodes (1): Skill: code-reviewer

### Community 75 - "Community 75"
Cohesion: 0.0
Nodes (1): Skill: discovery-interview

### Community 76 - "Community 76"
Cohesion: 0.0
Nodes (1): Битрикс24 CRM

## Knowledge Gaps
- **152 isolated node(s):** `iiko_client.py — клиент для iikoWeb OLAP.  Авторизация: POST /api/auth/login {lo`, `Фильтр по дате открытия заказа (формат YYYY-MM-DD).`, `Сессия iikoWeb: логин → JWT токен + auto-refresh.`, `Выполнить OLAP-запрос. Возвращает rawData (список dict) или [].     olap_type: "`, `Собрать данные через iikoWeb OLAP.     Возвращает dict со всеми показателями дня` (+147 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 62`** (2 nodes): `NapominatorTheme()`, `AppTheme.kt`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (2 nodes): `TaskEntity.kt`, `TaskEntity`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (1 nodes): `Задержка между площадками.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (1 nodes): `Парсит площадку и возвращает список словарей с полями:         id, url, source,`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `settings.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `max_bot.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `IAAPA (стандарты)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `Skill: fullstack-developer`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `Skill: code-reviewer`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (1 nodes): `Skill: discovery-interview`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (1 nodes): `Битрикс24 CRM`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.