"""
assistant_bot.py — Персональный AI-ассистент Александра
"""
import asyncio
import json
import logging
import sys
import tempfile
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import re

_MSK = ZoneInfo("Europe/Moscow")

sys.path.insert(0, "/home/parser/bots/assistant")


# Один или больше пайпов с опциональными пробелами — ASCII | (U+007C) и полноширинный ｜ (U+FF5C)
# Важно: (?:...) non-capturing, иначе group-индексы в parse-функции сдвигаются
_D = r'(?:[|｜]\s*)+'

_DSML_CLOSED_RE = re.compile(rf'<\s*{_D}DSML\s*{_D}tool_calls\s*>.*?</\s*{_D}DSML\s*{_D}tool_calls\s*>', re.DOTALL)
_DSML_OPEN_RE   = re.compile(rf'<\s*{_D}DSML\s*{_D}tool_calls\s*>.*', re.DOTALL)
_DSML_TAG_RE    = re.compile(rf'<\s*/?\s*{_D}DSML\s*{_D}[^>]*>', re.DOTALL)
_DSML_CHECK_RE  = re.compile(r'DSML', re.IGNORECASE)


def _strip_dsml(text: str) -> str:
    text = _DSML_CLOSED_RE.sub('', text)   # убрать закрытые блоки
    text = _DSML_OPEN_RE.sub('', text)      # убрать незакрытые блоки
    text = _DSML_TAG_RE.sub('', text)       # убрать одиночные теги-остатки
    return text.strip()


def _has_dsml(text: str) -> bool:
    return bool(_DSML_CHECK_RE.search(text))


def _clean_response(text: str) -> str:
    text = _strip_dsml(text)
    text = re.sub(r'<function_calls>.*?</function_calls>', '', text, flags=re.DOTALL)
    text = re.sub(r'<invoke\b.*?</invoke>', '', text, flags=re.DOTALL)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() or "(пустой ответ)"


def _parse_dsml_tool_calls(text: str) -> list[tuple[str, dict]]:
    """Парсит DSML-формат тул-коллов из текста ответа модели."""
    if not _DSML_CHECK_RE.search(text):
        return []
    invoke_re = re.compile(
        rf'<\s*{_D}DSML\s*{_D}invoke\s+name="([^"]+)"[^>]*>(.*?)</\s*{_D}DSML\s*{_D}invoke\s*>',
        re.DOTALL,
    )
    param_re = re.compile(
        rf'<\s*{_D}DSML\s*{_D}parameter\s+name="([^"]+)"[^>]*>(.*?)</\s*{_D}DSML\s*{_D}parameter\s*>',
        re.DOTALL,
    )
    calls = []
    for inv_m in invoke_re.finditer(text):
        name = inv_m.group(1)
        args = {m.group(1): m.group(2).strip() for m in param_re.finditer(inv_m.group(2))}
        calls.append((name, args))
    return calls

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import openai

import config
from tools.db import init_db
from tools import notes, reminders as rem_tool, calendar, web, memory as mem_tool, team_tasks, email_tool

# ── Инициализация ─────────────────────────────────────────────
bot = Bot(token=config.TELEGRAM_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

ai_client = openai.AsyncOpenAI(
    base_url=config.ROUTERAI_BASE_URL,
    api_key=config.ROUTERAI_API_KEY,
    timeout=90.0,  # 90 сек максимум; без таймаута бот зависает навсегда
)

histories: dict[int, list[dict]] = {}

# ── База знаний ───────────────────────────────────────────────
def _load_knowledge() -> str:
    knowledge_dir = Path(getattr(config, "KNOWLEDGE_DIR", "/home/parser/bots/assistant/knowledge"))
    parts = []
    for fname in ["projects.md", "user.md", "bot_facts.md"]:
        fpath = knowledge_dir / fname
        if fpath.exists():
            parts.append(fpath.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts) if parts else ""

KNOWLEDGE = _load_knowledge()

# ── Инструменты LLM ───────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Поиск информации в интернете. Используй для актуальных новостей, фактов, цен.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Загрузить и прочитать содержимое веб-страницы по URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Полный URL страницы"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_note",
            "description": "Сохранить заметку.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "tags": {"type": "string", "description": "Теги через запятую (необязательно)"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": "Показать последние заметки.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": "Найти заметки по ключевому слову.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_note",
            "description": "Удалить заметку по ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "integer"}
                },
                "required": ["note_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_reminder",
            "description": "Установить напоминание. Время в ISO8601: 2026-05-20T18:00:00",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "remind_at": {"type": "string", "description": "ISO8601, например 2026-05-21T09:00:00"},
                },
                "required": ["text", "remind_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "Показать активные напоминания.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_reminder",
            "description": "Отменить напоминание по ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "integer"}
                },
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule",
            "description": (
                "Показать расписание на конкретный день: события из Google Calendar + напоминания. "
                "Используй при ЛЮБОМ вопросе о планах, делах или расписании на день — "
                "сегодня, завтра, в конкретную дату или день недели. "
                "Сам переведи дату из слов в ISO-формат YYYY-MM-DD."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Дата в формате ISO: 2026-05-26"}
                },
                "required": ["date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Получить события из Google Calendar на несколько дней вперёд (без напоминаний). Используй только если нужен диапазон дней, а не конкретная дата.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "На сколько дней вперёд (по умолчанию 7)"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Создать событие в Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string", "description": "ISO8601, например 2026-05-21T10:00:00"},
                    "end": {"type": "string", "description": "ISO8601 (необязательно, по умолчанию +1 час)"},
                    "description": {"type": "string"},
                },
                "required": ["title", "start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": "Запомнить важный факт о пользователе, проекте или договорённости. Используй когда пользователь сообщает что-то важное о себе, своих предпочтениях или проектах.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Факт для запоминания"},
                    "category": {
                        "type": "string",
                        "enum": ["fact", "preference", "project", "decision"],
                        "description": "fact=общий факт, preference=предпочтение, project=о проекте, decision=принятое решение",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_facts",
            "description": "Найти запомненные факты по теме. Используй когда нужен контекст из прошлых разговоров.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Тема или ключевые слова для поиска"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_memories",
            "description": "Показать всё что бот помнит, по категории.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["fact", "preference", "project", "decision", ""],
                        "description": "Категория или пустая строка для всех",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_fact",
            "description": "Удалить факт из памяти по ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {"type": "integer"}
                },
                "required": ["memory_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_knowledge",
            "description": (
                "Обновить базу знаний о проектах или пользователе. "
                "Вызывай когда пользователь сообщает важное изменение в проекте, "
                "новый проект, смену роли, решение по архитектуре — то что должно "
                "сохраниться навсегда и быть доступно в будущих сессиях."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "enum": ["projects", "user", "bot_facts"],
                        "description": "'projects' — изменения в проектах, 'user' — информация об Александре, 'bot_facts' — запомненные факты из диалогов",
                    },
                    "content": {
                        "type": "string",
                        "description": "Текст для добавления в markdown-файл (можно использовать заголовки ##)",
                    },
                },
                "required": ["target", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restart_bot",
            "description": "Перезапускает бота на сервере через systemctl. Использовать когда нужно применить изменения в конфигурации или коде.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": (
                "Найти файл на Mac Александра по имени или ключевым словам. "
                "Используй когда просят найти файл, документ, PDF, отчёт и т.п. "
                "Возвращает список найденных файлов с путями."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Имя файла или ключевые слова"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_file_email",
            "description": (
                "Отправить файл с Mac на email. Вызывай после того как пользователь подтвердил "
                "какой файл и кому отправить. Принимает полный путь к файлу из search_files. "
                "Известные контакты: Катя, Виктор, Алексей (рабочая), Алексей (личная)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Полный путь к файлу (из результата search_files)"},
                    "to_name": {"type": "string", "description": "Имя получателя из адресной книги или email напрямую"},
                    "subject": {"type": "string", "description": "Тема письма (необязательно, по умолчанию — имя файла)"},
                },
                "required": ["file_path", "to_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_send_status",
            "description": "Проверить статус последней отправки файла по email.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_team_task",
            "description": (
                "Добавить задачу для члена команды ВК Губаха в таблицу 'Задачи недели'. "
                "Команда: Виктор, Евгения, Надежда, Управляющий, Тех.директор. "
                "Используй когда говорят 'поставь задачу', 'скажи Евгении', 'добавь в задачи'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "executor": {
                        "type": "string",
                        "description": "Исполнитель: Виктор, Евгения, Надежда, Управляющий или Тех.директор",
                    },
                    "task": {
                        "type": "string",
                        "description": "Описание задачи",
                    },
                    "deadline": {
                        "type": "string",
                        "description": "Срок в любом формате, например 'пятница', '30.05', '2026-05-30'",
                    },
                    "result": {
                        "type": "string",
                        "description": "Ожидаемый результат (необязательно)",
                    },
                    "how_to_check": {
                        "type": "string",
                        "description": "Как проверить выполнение (необязательно)",
                    },
                    "block": {
                        "type": "string",
                        "description": "Блок A или B (по умолчанию A)",
                    },
                },
                "required": ["executor", "task"],
            },
        },
    },
]

# ── Выполнение инструментов ───────────────────────────────────
def execute_tool(name: str, args: dict, user_id: int) -> str:
    try:
        if name == "web_search":
            return web.search(args["query"])
        elif name == "fetch_url":
            return web.fetch_url(args["url"])
        elif name == "add_note":
            return notes.add_note(args["text"], args.get("tags", ""))
        elif name == "list_notes":
            return notes.list_notes(args.get("limit", 10))
        elif name == "search_notes":
            return notes.search_notes(args["query"])
        elif name == "delete_note":
            return notes.delete_note(args["note_id"])
        elif name == "add_reminder":
            return rem_tool.add_reminder(args["text"], args["remind_at"], user_id)
        elif name == "list_reminders":
            return rem_tool.list_reminders(user_id)
        elif name == "cancel_reminder":
            return rem_tool.cancel_reminder(args["reminder_id"])
        elif name == "get_schedule":
            date_iso = args["date"]
            events = calendar.get_schedule_for_date(config.GOOGLE_CALENDAR_ID, config.SERVICE_ACCOUNT_JSON, date_iso)
            reminders = rem_tool.get_reminders_for_date(user_id, date_iso)
            lines = []
            if events:
                lines.append("📅 Календарь:")
                for ev in events:
                    start = ev["start"].get("dateTime", ev["start"].get("date", ""))
                    prefix = datetime.fromisoformat(start).strftime("%H:%M") if "T" in start else "весь день"
                    lines.append(f"• {prefix} — {ev.get('summary', '(без названия)')}")
            else:
                lines.append("📅 Календарь: событий нет")
            if reminders:
                lines.append("⏰ Напоминания:")
                for r in reminders:
                    lines.append(f"• {r['remind_at'][11:16]} — {r['text']}")
            return "\n".join(lines) if lines else "На этот день ничего не запланировано."
        elif name == "get_calendar_events":
            return calendar.get_events(config.GOOGLE_CALENDAR_ID, config.SERVICE_ACCOUNT_JSON, args.get("days", 7))
        elif name == "create_calendar_event":
            return calendar.create_event(
                config.GOOGLE_CALENDAR_ID,
                config.SERVICE_ACCOUNT_JSON,
                args["title"],
                args["start"],
                args.get("end"),
                args.get("description", ""),
            )
        elif name == "remember_fact":
            return mem_tool.remember_fact(args["text"], args.get("category", "fact"))
        elif name == "recall_facts":
            return mem_tool.recall_facts(args["query"])
        elif name == "list_memories":
            return mem_tool.list_memories(args.get("category", ""))
        elif name == "forget_fact":
            return mem_tool.forget_fact(args["memory_id"])
        elif name == "update_knowledge":
            return mem_tool.update_knowledge(args["target"], args["content"])
        elif name == "restart_bot":
            import subprocess
            subprocess.Popen(
                ["systemctl", "restart", "telegram-assistant"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return "Перезапуск инициирован. Бот перезапустится через 2-3 секунды."
        elif name == "search_files":
            return email_tool.search_files(args["query"])
        elif name == "send_file_email":
            return email_tool.send_file_email(args["file_path"], args["to_name"], args.get("subject", ""))
        elif name == "check_send_status":
            return email_tool.check_send_status()
        elif name == "add_team_task":
            return team_tasks.add_team_task(
                args["executor"],
                args["task"],
                args.get("deadline", ""),
                args.get("result", ""),
                args.get("how_to_check", ""),
            )
        else:
            return f"Неизвестный инструмент: {name}"
    except Exception as e:
        return f"Ошибка инструмента {name}: {e}"

# ── Персистентный typing-индикатор ───────────────────────────
async def _keep_typing(chat_id: int, stop: asyncio.Event):
    while not stop.is_set():
        try:
            await bot.send_chat_action(chat_id, "typing")
        except Exception:
            pass
        try:
            await asyncio.wait_for(asyncio.shield(stop.wait()), timeout=4)
        except asyncio.TimeoutError:
            pass

# Инструменты, требующие мгновенного подтверждения пользователю
# remember_fact убран — он требует подтверждения через inline-кнопки
_ACTION_TOOLS = {
    "create_calendar_event", "add_reminder", "add_note",
    "delete_note", "cancel_reminder",
    "forget_fact", "update_knowledge",
    "send_file_email",
}

# Состояние: user_id → fact_id (ожидаем исправление текста факта)
_awaiting_correction: dict[int, int] = {}


def _fact_approval_keyboard(fact_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Верно", callback_data=f"fact_ok_{fact_id}"),
        InlineKeyboardButton(text="✏️ Исправить", callback_data=f"fact_fix_{fact_id}"),
        InlineKeyboardButton(text="❌ Не то", callback_data=f"fact_no_{fact_id}"),
    ]])


async def _send_fact_approval(chat_id: int, fact_id: int, text: str):
    """Отправляет сообщение с запросом подтверждения факта."""
    await bot.send_message(
        chat_id,
        f"📝 *Запомнить этот факт?*\n\n{text}",
        parse_mode="Markdown",
        reply_markup=_fact_approval_keyboard(fact_id),
    )

async def _execute_and_notify(name: str, args: dict, user_id: int, chat_id: int) -> str:
    """Выполняет инструмент. Для remember_fact — отправляет запрос на подтверждение."""
    if name == "remember_fact":
        fact_id, orig_cat, text = mem_tool.remember_fact_pending(
            args["text"], args.get("category", "fact")
        )
        await _send_fact_approval(chat_id, fact_id, text)
        return f"Факт #{fact_id} отправлен пользователю на подтверждение [{orig_cat}]."
    result = execute_tool(name, args, user_id)
    if name in _ACTION_TOOLS:
        await bot.send_message(chat_id, f"✅ {result}")
    return str(result)


# ── LLM-цикл ─────────────────────────────────────────────────
async def run_llm(history: list[dict], user_id: int, chat_id: int) -> str:
    recent_memory = mem_tool.get_recent_summary(5)
    memory_section = f"\n\n## Из памяти (последние факты):\n{recent_memory}" if recent_memory else ""

    knowledge_section = f"\n\n## База знаний:\n{KNOWLEDGE}" if KNOWLEDGE else ""

    system_msg = {
        "role": "system",
        "content": (
            f"Ты мобильный ассистент Александра Бениаминова — работаешь 24/7 с телефона. "
            f"Сейчас {datetime.now(_MSK).strftime('%d.%m.%Y %H:%M')} МСК.\n"
            "Твоя зона: напоминалки, заметки, Google Calendar, командные задачи, веб-поиск, "
            "поиск файлов на Mac и отправка файлов по email. "
            "Для поиска файлов — вызови search_files, покажи результаты, дождись подтверждения пользователя, "
            "затем вызови send_file_email с полным путём файла и именем получателя. "
            "Адресная книга: Катя (info@entens.ru), Виктор (karpenko@entens.ru), "
            "Алексей рабочая (ap@entens.ru), Алексей личная (aprosandeev@mail.ru). "
            "Правила: отвечай максимум 2-3 предложения, только по последнему вопросу, без списков. "
            "После вызова инструмента — одно короткое подтверждение. "
            "Если узнал что-то важное о пользователе или проектах — вызови remember_fact. "
            "Для напоминаний конвертируй время в ISO8601. "
            "После получения результата инструмента — сразу финальный ответ. "
            "Когда пользователь спрашивает о планах/делах/расписании на любой день (сегодня, завтра, "
            "конкретная дата, день недели) — всегда вызывай get_schedule с датой в формате YYYY-MM-DD. "
            "Результат get_schedule выводи как есть, без сокращений. "
            "АВТО-СОХРАНЕНИЕ: при любом голосовом или коротком сообщении сразу определяй тип и вызывай инструмент БЕЗ уточнений: "
            "ПРИОРИТЕТ 1 — командная задача → add_team_task ТОЛЬКО при явных триггерах: "
            "'поставь задачу [имя]', 'скажи [имя] сделать/подготовить/проверить', "
            "'[имя] по работе/по объекту/по проекту/по Губахе', "
            "или роли Управляющий/Тех.директор (они всегда рабочие). "
            "Примеры → Sheets: 'поставь задачу Виктору — отчёт к пятнице', 'скажи Евгении подготовить меню', "
            "'напомни Виктору по объекту про инвентаризацию', 'скажи Управляющему проверить номера'. "
            "Всё остальное с именем — НЕ командная задача: "
            "'напомни Виктору позвонить', 'напиши Евгении', 'встреча с Надеждой' → add_reminder для Александра. "
            "ПРИОРИТЕТ 2 — если есть время/дата → add_reminder; "
            "если задача/дело → add_note с tags='задача'; "
            "если идея/мысль → add_note с tags='идея'; "
            "если факт о проекте/решение → remember_fact. "
            "Не спрашивай 'сохранить?', 'куда записать?' — просто сохраняй и кратко подтверди. "
            "ПОДТВЕРЖДЕНИЯ: для инструментов create_calendar_event, add_reminder, add_note "
            "пользователь уже видит мгновенное ✅-подтверждение. Не повторяй его содержимое. "
            "Для remember_fact — пользователь видит запрос на подтверждение с кнопками ✅/✏️/❌. "
            "Не добавляй ничего лишнего — просто скажи что отправил на подтверждение."
            f"{knowledge_section}"
            f"{memory_section}"
        ),
    }
    messages = [system_msg] + history
    total_tool_calls = 0

    for _ in range(10):
        force_text = total_tool_calls >= 3
        # Не передаём tools когда нужен текстовый ответ — DeepSeek игнорирует tool_choice="none"
        create_kwargs: dict = {"model": config.MODEL, "messages": messages, "max_tokens": 2000}
        if not force_text:
            create_kwargs["tools"] = TOOLS
            create_kwargs["tool_choice"] = "auto"
        resp = await ai_client.chat.completions.create(**create_kwargs)
        msg = resp.choices[0].message

        if not msg.tool_calls:
            content = msg.content or ""
            # DeepSeek иногда возвращает тул-коллы в текстовом DSML-формате вместо API tool_calls
            dsml_calls = _parse_dsml_tool_calls(content)
            if dsml_calls and total_tool_calls < 6:
                messages.append({"role": "assistant", "content": _strip_dsml(content) or ""})
                results_parts = []
                for name, args in dsml_calls:
                    result = await _execute_and_notify(name, args, user_id, chat_id)
                    results_parts.append(f"[{name}]: {result}")
                    total_tool_calls += 1
                messages.append({
                    "role": "user",
                    "content": "Результаты инструментов:\n\n" + "\n\n".join(results_parts) + "\n\nОтветь пользователю текстом.",
                })
                # Финальный вызов без tools — DeepSeek обязан ответить текстом, не DSML
                final_resp = await ai_client.chat.completions.create(
                    model=config.MODEL,
                    messages=messages,
                    max_tokens=2000,
                )
                return _strip_dsml(final_resp.choices[0].message.content or "") or "(пустой ответ)"
            # Всегда стрипаем DSML — страховка на случай если парсер не сработал или лимит исчерпан
            return _strip_dsml(content) or "(пустой ответ)"

        messages.append(msg.model_dump(exclude_unset=True))
        total_tool_calls += len(msg.tool_calls)

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = await _execute_and_notify(tc.function.name, args, user_id, chat_id)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

        # После выполнения API tool_calls — делаем финальный вызов без tools
        # DeepSeek склонен петлять с повторными поисками; без tools он обязан ответить текстом
        final_resp = await ai_client.chat.completions.create(
            model=config.MODEL,
            messages=messages,
            max_tokens=2000,
        )
        final_content = final_resp.choices[0].message.content or ""
        # Если финальный ответ снова DSML — парсим и выполняем, затем возвращаем результаты напрямую
        dsml_final = _parse_dsml_tool_calls(final_content)
        if dsml_final:
            results_parts = []
            for name, args in dsml_final:
                r = await _execute_and_notify(name, args, user_id, chat_id)
                results_parts.append(f"[{name}]: {r}")
            # Последняя попытка — text-only с результатами
            messages.append({"role": "user", "content": "Результаты:\n" + "\n".join(results_parts) + "\n\nОтветь пользователю текстом."})
            last_resp = await ai_client.chat.completions.create(model=config.MODEL, messages=messages, max_tokens=2000)
            return _strip_dsml(last_resp.choices[0].message.content or "") or "(пустой ответ)"
        return _strip_dsml(final_content) or "(пустой ответ)"

    return "Не удалось обработать запрос. Попробуй переформулировать."

# ── Транскрипция голоса ───────────────────────────────────────

# Известные галлюцинации Whisper — пустой результат или промпт вместо текста
_WHISPER_HALLUCINATIONS = {
    "transcribe the audio",
    "transcribe the video",
    "thank you for watching",
    "thanks for watching",
    "subtitle by",
    "subtitles by",
    "downloaded from",
    "you",
    "",
}

def _is_whisper_hallucination(text: str) -> bool:
    """Проверяет, является ли результат галлюцинацией Whisper."""
    cleaned = text.strip().lower().rstrip(".")
    if not cleaned:
        return True
    if cleaned in _WHISPER_HALLUCINATIONS:
        return True
    # Слишком короткий текст для 9+ секунд аудио (< 3 символов)
    if len(cleaned) < 3:
        return True
    return False

async def transcribe_voice(message: Message) -> str:
    from groq import Groq
    voice = message.voice
    file = await bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        await bot.download_file(file.file_path, tmp_path)

        # Проверяем что файл реально скачался
        file_size = os.path.getsize(tmp_path)
        if file_size < 100:
            return "[Не удалось распознать голос: пустой аудиофайл]"

        groq_client = Groq(api_key=config.GROQ_API_KEY)

        # Prompt подсказывает модели что это русская речь — снижает галлюцинации
        ru_prompt = "Это голосовое сообщение на русском языке."

        # Первая попытка — turbo
        with open(tmp_path, "rb") as f:
            tr = groq_client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=("voice.ogg", f, "audio/ogg"),
                language="ru",
                prompt=ru_prompt,
            )
        result = tr.text.strip()

        # Если галлюцинация — повторяем через whisper-large-v3 (точнее, но медленнее)
        if _is_whisper_hallucination(result):
            logging.warning(f"[Whisper] turbo галлюцинация: {repr(result)}, пробуем whisper-large-v3")
            with open(tmp_path, "rb") as f:
                tr2 = groq_client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=("voice.ogg", f, "audio/ogg"),
                    language="ru",
                    prompt=ru_prompt,
                )
            result = tr2.text.strip()

        # Если и повтор галлюцинация — сообщаем пользователю
        if _is_whisper_hallucination(result):
            logging.warning(f"[Whisper] оба варианта дали галлюцинацию, файл {file_size} байт")
            return "[Не удалось распознать голос: Whisper не смог разобрать аудио. Попробуй отправить ещё раз или напиши текстом.]"

        return result

    except Exception as e:
        logging.error(f"[Whisper] ошибка транскрипции: {e}")
        return f"[Не удалось распознать голос: {e}]"
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

# ── Доступ ────────────────────────────────────────────────────
def is_allowed(user_id: int) -> bool:
    return not config.ALLOWED_USER_IDS or user_id in config.ALLOWED_USER_IDS

# ── Хендлеры ─────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer(
        "Привет! Я персональный ассистент Александра.\n\n"
        "Умею:\n"
        "• Отвечать на вопросы и искать в интернете\n"
        "• Принимать голосовые сообщения\n"
        "• Сохранять заметки и напоминания\n"
        "• Работать с Google Calendar\n"
        "• Запоминать важные факты о тебе и проектах\n\n"
        "Команды: /notes /reminders /memory /reset"
    )

@dp.message(Command("whoami"))
async def cmd_whoami(message: Message):
    uid = message.from_user.id
    await message.answer(
        f"Telegram ID: `{uid}`\nИмя: {message.from_user.full_name}",
        parse_mode="Markdown",
    )

@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    if not is_allowed(message.from_user.id):
        return
    histories.pop(message.from_user.id, None)
    await message.answer("История диалога очищена.")

@dp.message(Command("notes"))
async def cmd_notes(message: Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer(notes.list_notes(10))

@dp.message(Command("reminders"))
async def cmd_reminders(message: Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer(rem_tool.list_reminders(message.from_user.id))

@dp.message(Command("memory"))
async def cmd_memory(message: Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer(mem_tool.list_memories())


@dp.message(Command("facts"))
async def cmd_facts(message: Message):
    """Показывает факты, ожидающие подтверждения."""
    if not is_allowed(message.from_user.id):
        return
    pending = mem_tool.get_pending_facts()
    if not pending:
        await message.answer("✅ Нет фактов на проверке.")
        return
    await message.answer(f"⏳ Факты на проверке ({len(pending)}):")
    for f in pending:
        await message.answer(
            f"#{f['id']} [{f['category']}]: {f['text']}",
            reply_markup=_fact_approval_keyboard(f["id"]),
        )

@dp.message(Command("restart"))
async def cmd_restart(message: Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer("♻️ Перезапускаю бота...")
    import subprocess
    subprocess.Popen(
        ["systemctl", "restart", "telegram-assistant"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

# ── Кнопки напоминаний ────────────────────────────────────────
@dp.callback_query(F.data.startswith("ack_"))
async def handle_ack(callback: CallbackQuery):
    if not is_allowed(callback.from_user.id):
        return
    reminder_id = int(callback.data.split("_")[1])
    rem_tool.ack_reminder_by_id(reminder_id, callback.from_user.id)
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ _Выполнено_",
        parse_mode="Markdown",
        reply_markup=None,
    )
    await callback.answer("Выполнено!")

@dp.callback_query(F.data.startswith("snz_"))
async def handle_snooze(callback: CallbackQuery):
    if not is_allowed(callback.from_user.id):
        return
    parts = callback.data.split("_")
    reminder_id = int(parts[1])

    if len(parts) == 2:
        await callback.message.edit_reply_markup(
            reply_markup=rem_tool._snooze_keyboard(reminder_id)
        )
        await callback.answer()
    elif parts[2] == "back":
        await callback.message.edit_reply_markup(
            reply_markup=rem_tool._main_keyboard(reminder_id)
        )
        await callback.answer()
    else:
        minutes = 0 if parts[2] == "tmr" else int(parts[2])
        label = rem_tool.snooze_reminder(reminder_id, callback.from_user.id, minutes)
        await callback.message.edit_text(
            callback.message.text + f"\n\n⏰ _Отложено: {label}_",
            parse_mode="Markdown",
            reply_markup=None,
        )
        await callback.answer(f"Отложено: {label}")

# ── Подтверждение фактов ─────────────────────────────────────
@dp.callback_query(F.data.startswith("fact_ok_"))
async def handle_fact_approve(callback: CallbackQuery):
    if not is_allowed(callback.from_user.id):
        return
    fact_id = int(callback.data.split("_")[2])
    result = mem_tool.approve_fact(fact_id)
    await callback.message.edit_text(f"✅ {result}", reply_markup=None)
    await callback.answer("Сохранено!")


@dp.callback_query(F.data.startswith("fact_fix_"))
async def handle_fact_fix(callback: CallbackQuery):
    if not is_allowed(callback.from_user.id):
        return
    fact_id = int(callback.data.split("_")[2])
    _awaiting_correction[callback.from_user.id] = fact_id
    await callback.message.edit_text(
        callback.message.text + "\n\n✏️ _Введи правильный текст:_",
        parse_mode="Markdown",
        reply_markup=None,
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("fact_no_"))
async def handle_fact_deny(callback: CallbackQuery):
    if not is_allowed(callback.from_user.id):
        return
    fact_id = int(callback.data.split("_")[2])
    mem_tool.reject_fact(fact_id)
    await callback.message.edit_text("❌ Факт отклонён", reply_markup=None)
    await callback.answer("Отклонено")


# ── Обработка сообщений ───────────────────────────────────────
@dp.message(F.text | F.voice)
async def handle_message(message: Message):
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return

    # Режим исправления факта: следующее сообщение — новый текст факта
    if message.text and user_id in _awaiting_correction:
        fact_id = _awaiting_correction.pop(user_id)
        result = mem_tool.correct_fact(fact_id, message.text.strip())
        await message.answer(f"✅ {result}")
        return

    if message.voice:
        text = await transcribe_voice(message)
        if text.startswith("[Не удалось"):
            await message.answer(text)
            return
        await message.answer(f"🎙 _{text}_", parse_mode="Markdown")
    else:
        text = message.text

    history = histories.setdefault(user_id, [])
    history.append({"role": "user", "content": text})

    if len(history) > 20:
        histories[user_id] = history[-20:]
        history = histories[user_id]

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(message.chat.id, stop_typing))
    try:
        response = await run_llm(history, user_id, message.chat.id)
        response = _clean_response(response)
    except openai.APITimeoutError:
        response = "Сервер думает слишком долго — попробуй повторить запрос."
    except Exception as e:
        response = f"Ошибка: {e}"
    finally:
        stop_typing.set()
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    # Ядерная страховка: если DSML всё ещё есть — не отправлять мусор
    if _has_dsml(response):
        response = _strip_dsml(response)
    if _has_dsml(response):
        response = "Ищу информацию... попробуй повторить запрос."

    history.append({"role": "assistant", "content": response})

    if response and response != "(пустой ответ)":
        for i in range(0, len(response), 4000):
            await message.answer(response[i:i+4000])

# ── Форматирование расписания ─────────────────────────────────
def _format_schedule(date_iso: str, cal_events: list, reminders: list, header: str = "") -> str:
    date_label = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    lines = [header or f"📆 *План на {date_label}:*\n"]
    if cal_events:
        lines.append("📅 *Календарь:*")
        for ev in cal_events:
            start = ev["start"].get("dateTime", ev["start"].get("date", ""))
            prefix = datetime.fromisoformat(start).strftime("%H:%M") if "T" in start else "весь день"
            lines.append(f"• {prefix} — {ev.get('summary', '(без названия)')}")
    else:
        lines.append("📅 *Календарь:* событий нет")
    if reminders:
        lines.append("\n⏰ *Напоминания:*")
        for r in reminders:
            lines.append(f"• {r['remind_at'][11:16]} — {r['text']}")
    if not cal_events and not reminders:
        lines.append("Ничего не запланировано 🎉")
    return "\n".join(lines)


# ── Утренний дайджест ─────────────────────────────────────────
async def morning_briefing():
    """Отправляет план на день в 09:00 МСК каждому пользователю."""
    for user_id in config.ALLOWED_USER_IDS:
        try:
            today_iso = datetime.now(_MSK).strftime("%Y-%m-%d")
            today_label = datetime.now(_MSK).strftime("%d.%m.%Y")
            try:
                cal_events = calendar.get_schedule_for_date(config.GOOGLE_CALENDAR_ID, config.SERVICE_ACCOUNT_JSON, today_iso)
            except Exception as e:
                cal_events = []
            reminders = rem_tool.get_reminders_for_date(user_id, today_iso)
            text = _format_schedule(today_iso, cal_events, reminders, header=f"☀️ *Доброе утро! План на {today_label}:*\n")
            await bot.send_message(user_id, text, parse_mode="Markdown")
        except Exception as e:
            print(f"[morning_briefing] ошибка для {user_id}: {e}")


# ── Команда /schedule ─────────────────────────────────────────
@dp.message(Command("schedule"))
async def cmd_schedule(message: Message):
    if not is_allowed(message.from_user.id):
        return
    today_iso = datetime.now(_MSK).strftime("%Y-%m-%d")
    try:
        cal_events = calendar.get_schedule_for_date(config.GOOGLE_CALENDAR_ID, config.SERVICE_ACCOUNT_JSON, today_iso)
    except Exception:
        cal_events = []
    reminders = rem_tool.get_reminders_for_date(message.from_user.id, today_iso)
    await message.answer(_format_schedule(today_iso, cal_events, reminders), parse_mode="Markdown")


# ── Запуск ────────────────────────────────────────────────────
async def main():
    init_db()
    mem_tool._init_memory_table()
    rem_tool.init_scheduler(bot, scheduler)
    scheduler.add_job(
        morning_briefing, "cron",
        hour=9, minute=0,
        timezone="Europe/Moscow",
        id="morning_briefing",
        replace_existing=True,
    )
    scheduler.start()
    print(f"[{datetime.now(_MSK).strftime('%H:%M:%S')} МСК] Бот запущен.")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
