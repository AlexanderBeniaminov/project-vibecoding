# CLAUDE.md — Content Bot

Личный бот Александра для генерации и публикации постов в канал «ИИндустрия Развлечений». Живёт на VPS `/home/parser/bots/content-bot/`. Полностью отдельный от `telegram-assistant` — свой токен, свой процесс, свой systemd-сервис.

---

## Что умеет

- Голос/текст с темой → 3 варианта поста (разные форматы и аудитории)
- «Идея для поста: ...» → сохраняет тему без немедленной генерации
- Сам предлагает темы: веб-поиск тренда ниши + тон голоса + история публикаций
- Корректировка вариантов через чат
- Публикация сразу или по расписанию (пн/чт 10:00 МСК, раз в 2 недели — рубрика «Лайфхак»)
- Блэклист тем (временный/постоянный) с семантической проверкой перед генерацией
- Двусторонняя синхронизация с Google Sheets (push мгновенно, pull 2 раза в сутки)

Полная спецификация — [PLAN.md](PLAN.md).

---

## Стек

| Компонент | Технология |
|-----------|-----------|
| Фреймворк | aiogram 3 (async, long-polling) |
| LLM | DeepSeek V4 Pro через RouterAI (`deepseek/deepseek-v4-pro`) |
| Голос | Groq Whisper (`whisper-large-v3-turbo`, fallback `whisper-large-v3`) |
| Планировщик | APScheduler `AsyncIOScheduler`, timezone=`Europe/Moscow` |
| БД | SQLite (`data/content.db`) — источник правды |
| Sheets | gspread + service account — визуальный слой, не источник правды |
| Деплой | rsync → `deploy.sh` → `systemctl restart content-bot` |

---

## Файловая структура

```
content-bot/
├── bot.py               # Dispatcher, хэндлеры, FSM, главное меню
├── db.py                # SQLite схема + CRUD
├── generator.py         # Промпт → DeepSeek → 3 варианта поста
├── publisher.py         # Публикация в канал + APScheduler джобы расписания
├── blacklist.py         # Реестр нежелательных тем + семантическая проверка
├── search.py            # Веб-поиск трендов ниши (DuckDuckGo)
├── sheets.py            # Google Sheets: push + pull синхронизация
├── config.example.py    # Шаблон конфига
├── deploy.sh             # rsync + systemctl restart
├── knowledge/
│   ├── tone-of-voice.md # Тон голоса канала (источник: content-plan/, копировать вручную при обновлении)
│   ├── audience.md      # Боли и вопросы аудитории (источник: content-plan/)
│   └── business.md      # Сводка о бизнесе для промпта генератора
└── data/
    └── content.db        # SQLite (создаётся автоматически)
```

На сервере та же структура в `/home/parser/bots/content-bot/`, плюс `config.py` (секреты, не в git).

**Systemd:** `systemctl status content-bot`
**Логи:** `journalctl -u content-bot -n 50`

---

## Источник правды

SQLite — основное хранилище. Google Sheets — зеркало для просмотра и ручных правок. При синхронизации побеждает последнее изменение по timestamp. Подробности — PLAN.md → «Google Sheets — структура и синхронизация».

---

## Ключевые паттерны (переиспользованы из telegram-assistant)

### DSML-очистка ответов DeepSeek
`generator.py:_clean_json_response()` — тот же подход, что `assistant_bot.py:_clean_dsml()`: вырезать `<|DSML|tool_calls>` блоки и одиночные теги перед `json.loads()`.

### Timezone — только Москва
```python
from zoneinfo import ZoneInfo
_MSK = ZoneInfo("Europe/Moscow")
```

### Восстановление расписания при старте
`publisher.py:restore_scheduled_jobs()` — при старте бота читает `ideas WHERE status='scheduled'` и регистрирует APScheduler job на каждую. Паттерн идентичен `telegram-assistant/tools/reminders.py:_restore_pending()`.

### Веб-поиск
`search.py` — обёртка вокруг `ddgs.DDGS()`, тот же подход что `telegram-assistant/tools/web.py`.

---

## Критичные инварианты — не ломать

1. **Не трогать `telegram-assistant`.** Разные токены, разные процессы, разные systemd-юниты. Общий только сервис-аккаунт Google (`/home/parser/config/personal/service_account.json`) — он read/write, делить аккуратно.
2. **SQLite — источник правды, Sheets — зеркало.** Никогда не писать прямо в Sheets без последующей синхронизации в SQLite. Логика sync — только в `sheets.py`.
3. **Тест vs боевой канал — только через конфиг.** В UI всегда одна кнопка [✅ Опубликовать]. Не делать два разных потока в коде — переключение `CHANNEL_ID`/`TEST_CHANNEL_ID` в `config.py`.
4. **Поле `audience` в `generations`** — для аналитики, никогда не показывать пользователю в тексте сообщения.
5. **Cooldown 30 дней** после публикации — тема не должна предлагаться повторно в Режиме 0.

---

## Деплой

```bash
bash content-bot/deploy.sh
```

Паттерн идентичен `telegram-assistant/deploy.sh`: rsync исключая `config.py` и `data/`, затем `systemctl restart content-bot`.

После обновления `knowledge/*.md` — деплой обязателен (бот читает файлы при старте, без hot-reload).

---

## Правила

- Ответы бота: короткие, без канцелярита
- Комментарии в коде — на русском
- Язык генерируемых постов — стиль из `knowledge/tone-of-voice.md`, без отклонений
