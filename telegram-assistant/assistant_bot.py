"""
assistant_bot.py — Персональный AI-ассистент Александра
"""
import asyncio
import json
import sys
import tempfile
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import re

_MSK = ZoneInfo("Europe/Moscow")

sys.path.insert(0, "/home/parser/bots/assistant")


def _clean_response(text: str) -> str:
    # Вырезаем целые DSML-блоки вместе с содержимым
    text = re.sub(r'<\|+DSML\|+tool_calls>.*?</\|+DSML\|+tool_calls>', '', text, flags=re.DOTALL)
    # Вырезаем одиночные DSML-теги, которые могли остаться
    text = re.sub(r'</?‌\|+DSML\|+[^>]*>', '', text, flags=re.DOTALL)
    text = re.sub(r'<\|?\s*DSML\s*\|?[^>]*>', '', text, flags=re.DOTALL)
    text = re.sub(r'<function_calls>.*?</function_calls>', '', text, flags=re.DOTALL)
    text = re.sub(r'<invoke\b.*?</invoke>', '', text, flags=re.DOTALL)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() or "(пустой ответ)"


def _parse_dsml_tool_calls(text: str) -> list[tuple[str, dict]]:
    """Парсит DSML-формат тул-коллов из текста ответа модели."""
    if not re.search(r'<\|+DSML\|+tool_calls>', text):
        return []
    invoke_re = re.compile(
        r'<\|+DSML\|+invoke\s+name="([^"]+)"[^>]*>(.*?)</\|+DSML\|+invoke>',
        re.DOTALL,
    )
    param_re = re.compile(
        r'<\|+DSML\|+parameter\s+name="([^"]+)"[^>]*>(.*?)</\|+DSML\|+parameter>',
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
from aiogram.types import Message, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import openai

import config
from tools.db import init_db
from tools import notes, reminders as rem_tool, calendar, web, memory as mem_tool, files as files_tool

# ── Инициализация ─────────────────────────────────────────────
bot = Bot(token=config.TELEGRAM_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

ai_client = openai.AsyncOpenAI(
    base_url=config.ROUTERAI_BASE_URL,
    api_key=config.ROUTERAI_API_KEY,
)

histories: dict[int, list[dict]] = {}

# ── База знаний ───────────────────────────────────────────────
def _load_knowledge() -> str:
    knowledge_dir = Path(getattr(config, "KNOWLEDGE_DIR", "/home/parser/bots/assistant/knowledge"))
    parts = []
    for fname in ["projects.md", "user.md"]:
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
                        "enum": ["projects", "user"],
                        "description": "'projects' — изменения в проектах, 'user' — информация об Александре",
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
                "Поиск файлов на Mac Александра по имени или содержимому. "
                "Работает по последнему синхронизированному индексу (обновляется каждые 2 часа). "
                "Умеет искать в презентациях .pptx, документах .docx, PDF, таблицах .xlsx, "
                "а также по имени любого файла. Всегда показывает дату последнего обновления индекса."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Что искать — слова из имени файла или из содержимого",
                    },
                    "file_type": {
                        "type": "string",
                        "description": "Необязательно: фильтр по расширению без точки, например pptx, pdf, docx, xlsx",
                    },
                },
                "required": ["query"],
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
            return files_tool.search_files(args["query"], args.get("file_type"))
        else:
            return f"Неизвестный инструмент: {name}"
    except Exception as e:
        return f"Ошибка инструмента {name}: {e}"

# ── LLM-цикл ─────────────────────────────────────────────────
async def run_llm(history: list[dict], user_id: int) -> str:
    recent_memory = mem_tool.get_recent_summary(5)
    memory_section = f"\n\n## Из памяти (последние факты):\n{recent_memory}" if recent_memory else ""

    knowledge_section = f"\n\n## База знаний:\n{KNOWLEDGE}" if KNOWLEDGE else ""

    system_msg = {
        "role": "system",
        "content": (
            f"Ты персональный ассистент Александра Бениаминова. "
            f"Сейчас {datetime.now(_MSK).strftime('%d.%m.%Y %H:%M')} МСК.\n"
            "Правила: отвечай максимум 2-3 предложения, только по последнему вопросу, без списков. "
            "После вызова инструмента — одно короткое подтверждение. "
            "Если узнал что-то важное о пользователе или проектах — вызови remember_fact. "
            "Для напоминаний конвертируй время в ISO8601. "
            "После получения результата инструмента — сразу финальный ответ. "
            "Когда пользователь спрашивает о планах/делах/расписании на любой день (сегодня, завтра, "
            "конкретная дата, день недели) — всегда вызывай get_schedule с датой в формате YYYY-MM-DD. "
            "Результат get_schedule выводи как есть, без сокращений."
            f"{knowledge_section}"
            f"{memory_section}"
        ),
    }
    messages = [system_msg] + history
    total_tool_calls = 0

    for _ in range(10):
        force_text = total_tool_calls >= 3
        resp = await ai_client.chat.completions.create(
            model=config.MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="none" if force_text else "auto",
            max_tokens=2000,
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            content = msg.content or ""
            # DeepSeek иногда возвращает тул-коллы в текстовом DSML-формате вместо API tool_calls
            dsml_calls = _parse_dsml_tool_calls(content)
            if dsml_calls and total_tool_calls < 6:
                stripped = re.sub(
                    r'<\|+DSML\|+tool_calls>.*?</\|+DSML\|+tool_calls>', '',
                    content, flags=re.DOTALL,
                ).strip()
                messages.append({"role": "assistant", "content": stripped or ""})
                results_parts = []
                for name, args in dsml_calls:
                    result = execute_tool(name, args, user_id)
                    results_parts.append(f"[{name}]: {result}")
                    total_tool_calls += 1
                messages.append({
                    "role": "user",
                    "content": "Результаты инструментов:\n\n" + "\n\n".join(results_parts) + "\n\nОтветь пользователю.",
                })
                continue
            return content or "(пустой ответ)"

        messages.append(msg.model_dump(exclude_unset=True))
        total_tool_calls += len(msg.tool_calls)

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = execute_tool(tc.function.name, args, user_id)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result),
            })

    return "Не удалось обработать запрос. Попробуй переформулировать."

# ── Транскрипция голоса ───────────────────────────────────────
async def transcribe_voice(message: Message) -> str:
    from groq import Groq
    voice = message.voice
    file = await bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        await bot.download_file(file.file_path, tmp_path)
        groq_client = Groq(api_key=config.GROQ_API_KEY)
        with open(tmp_path, "rb") as f:
            tr = groq_client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=("voice.ogg", f, "audio/ogg"),
                language="ru",
            )
        return tr.text
    except Exception as e:
        return f"[Не удалось распознать голос: {e}]"
    finally:
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
        callback.message.text + "\n\n✅ _Принято_",
        parse_mode="Markdown",
        reply_markup=None,
    )
    await callback.answer("Принято!")

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

# ── Обработка сообщений ───────────────────────────────────────
@dp.message(F.text | F.voice)
async def handle_message(message: Message):
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return

    await bot.send_chat_action(message.chat.id, "typing")

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

    try:
        await bot.send_chat_action(message.chat.id, "typing")
        response = await run_llm(history, user_id)
        response = _clean_response(response)
    except Exception as e:
        response = f"Ошибка: {e}"

    history.append({"role": "assistant", "content": response})

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
