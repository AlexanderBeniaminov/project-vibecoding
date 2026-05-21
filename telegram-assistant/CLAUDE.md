# CLAUDE.md — Telegram AI Ассистент

Персональный бот Александра Бениаминова. Живёт на VPS `/home/parser/bots/assistant/`.

---

## Что умеет

- Голосовые сообщения (Groq Whisper → текст)
- Напоминания с повтором до подтверждения (кнопки ✅ Принято / ⏰ Отложить)
- Заметки (SQLite)
- Google Calendar (чтение + создание событий)
- Веб-поиск
- Память фактов (SQLite FTS5, категории: fact / preference / project / decision)
- Самообновление базы знаний через инструмент `update_knowledge`

---

## Стек

| Компонент | Технология |
|-----------|-----------|
| Фреймворк | aiogram 3 (async, long-polling) |
| LLM | DeepSeek V4 Pro через RouterAI (`deepseek/deepseek-v4-pro`) |
| Голос | Groq Whisper (`whisper-large-v3-turbo`) — free tier |
| Планировщик | APScheduler `AsyncIOScheduler`, timezone=`Europe/Moscow` |
| БД | SQLite (`data/assistant.db`) — заметки, напоминания, память |
| Деплой | rsync → `deploy.sh` → `systemctl restart telegram-assistant` |

---

## Файловая структура

```
telegram-assistant/
├── assistant_bot.py        # Главный файл: handlers, run_llm(), инициализация
├── config.example.py       # Шаблон — скопировать в config.py на сервере
├── deploy.sh               # rsync + ssh restart
├── knowledge/
│   ├── projects.md         # База знаний о проектах Александра
│   └── user.md             # Профиль Александра (контакты, предпочтения)
└── tools/
    ├── db.py               # SQLite init (notes, reminders)
    ├── notes.py            # Заметки
    ├── reminders.py        # Напоминания с repeat-until-ack
    ├── calendar_tool.py    # Google Calendar
    ├── search.py           # Веб-поиск
    └── memory.py           # Память фактов + update_knowledge()
```

---

## На сервере

```
/home/parser/bots/assistant/
├── assistant_bot.py        # рабочий файл
├── config.py               # секреты (не в git!)
├── data/
│   └── assistant.db        # SQLite
└── knowledge/
    ├── projects.md
    └── user.md
```

**Systemd:** `systemctl status telegram-assistant`
**Логи:** `journalctl -u telegram-assistant -n 50`

---

## config.py (на сервере, не в git)

```python
TELEGRAM_TOKEN = "7778266500:..."
ALLOWED_USER_IDS: set[int] = {994743403}
ROUTERAI_BASE_URL = "https://routerai.ru/api/v1"
ROUTERAI_API_KEY = "sk-f61V-..."
MODEL = "deepseek/deepseek-v4-pro"
GOOGLE_CALENDAR_ID = "a79037801122@gmail.com"
SERVICE_ACCOUNT_JSON = "/home/parser/config/personal/service_account.json"
GROQ_API_KEY = "gsk_..."
DB_PATH = "/home/parser/bots/assistant/data/assistant.db"
KNOWLEDGE_DIR = "/home/parser/bots/assistant/knowledge"
```

---

## Ключевые паттерны

### Защита от бесконечного цикла инструментов
```python
# В run_llm(): после 3 вызовов инструментов — принудительный текстовый ответ
force_text = total_tool_calls >= 3
tool_choice = "none" if force_text else "auto"
```

### Timezone — только Moscow
```python
from zoneinfo import ZoneInfo
_MSK = ZoneInfo("Europe/Moscow")  # сервер в CEST, бот думает MSK
datetime.now(_MSK)                 # всегда использовать явно
```

### Чистка DSML-артефактов DeepSeek
```python
def _clean_response(text: str) -> str:
    text = re.sub(r'<\|?\s*DSML\s*\|?.*?>', '', text, flags=re.DOTALL)
    text = re.sub(r'<function_calls>.*?</function_calls>', '', text, flags=re.DOTALL)
    return text.strip() or "(пустой ответ)"
```

### Напоминания — repeat until ack
- `REPEAT_MINUTES = 5` — повтор каждые 5 минут пока не подтверждено
- `_pending_acks: dict[int, set[int]]` — отслеживает активные напоминания
- Кнопки: ✅ Принято → `ack_reminder_by_id()` / ⏰ Отложить → +30 мин / +1 час / Завтра 09:00

---

## Деплой

```bash
bash telegram-assistant/deploy.sh
```

Скрипт: rsync исключая `config.py`, `data/`, `__pycache__/` → рестарт сервиса.

После обновления `knowledge/*.md` — деплой обязателен (или `_reload_knowledge()` внутри бота через `update_knowledge`).

---

## Google Calendar

- Сервисный аккаунт: `personal-assistant@alex-personal-496919.iam.gserviceaccount.com`
- GCP проект: `alex-personal-496919`
- Права: "Изменение мероприятий" (writer) на календаре a79037801122@gmail.com
- Файл SA: `/home/parser/config/personal/service_account.json`

---

## Правила

- Ответы бота: максимум 2–3 предложения
- Язык: русский
- После вызова инструмента — одно короткое подтверждение
- Если бот узнал что-то важное — вызвать `remember_fact`
- Knowledge-файлы обновлять автономно через `update_knowledge`, потом деплоить
