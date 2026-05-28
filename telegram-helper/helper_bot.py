#!/usr/bin/env python3
"""
helper_bot.py — @pomoshniknamac_bot «Помощник»
Работает 24/7 на VPS. Функции: задачи Губаха, CRM, таблицы, email, фото, AI-чат.
"""
import asyncio
import base64
import re
import json
import imaplib
import smtplib
import sqlite3
import email as email_lib
import email.header
import email.utils
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.header import Header
from pathlib import Path
from zoneinfo import ZoneInfo

import openai
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from groq import Groq

import config

# ── Инициализация ─────────────────────────────────────────────────
_MSK = ZoneInfo("Europe/Moscow")
bot = Bot(token=config.TELEGRAM_TOKEN)
dp = Dispatcher()

ai_client = openai.AsyncOpenAI(
    base_url=config.ROUTERAI_BASE_URL,
    api_key=config.ROUTERAI_API_KEY,
)

histories: dict[int, list] = {}

# ── Проверка доступа ──────────────────────────────────────────────
def is_allowed(user_id: int) -> bool:
    return user_id in config.ALLOWED_USER_IDS

# ── Системный промпт ──────────────────────────────────────────────
def _system_prompt() -> str:
    now = datetime.now(_MSK).strftime("%d.%m.%Y %H:%M")
    base_prompt = (
        f"Ты бизнес-ассистент Александра Бениаминова. Сейчас {now} МСК. Язык: русский.\n\n"
        "МОДЕЛЬ: Если задача требует глубокого анализа, составления отчёта или сложного "
        "рассуждения — сам предложи: «Это лучше решит Claude Sonnet 4.6 — переключить?»\n\n"
        "СХЕМА РЕШЕНИЙ — выполняй первое подходящее:\n\n"
        "① Имя из команды + задача → add_team_task.\n"
        "   Команда: Виктор/Витя, Евгения/Женя, Надежда/Надя, Управляющий, Тех.директор.\n"
        "   При нечётком имени — сначала уточни: «Имеешь в виду Евгению?»\n"
        "   ОБЯЗАТЕЛЬНО уточни дедлайн если не указан — задачу без срока не ставь.\n"
        "   Если задача неясна — уточни до конца перед записью.\n"
        "   Голосовое сообщение с задачей обрабатывай так же как текст — уточни если неясно.\n"
        "   После записи задачи → спроси: «Поставить напоминание проверить [имя] к [дедлайн]?»\n\n"
        "② Вопрос про выручку / загрузку / гостей / ADR / RevPar / фудкост / Монблан / Губаха → query_sheets.\n"
        "   Ответ: метрика + значение + период — одной строкой.\n"
        "   Нет данных за период → «Данных за [период] нет». Не ищи замену. Не угадывай.\n\n"
        "③ «задачи [имя]» / «что висит у [имя]» / «что у [имя] в работе» →\n"
        "   query_sheets фильтр по исполнителю. Выводи: задача — дедлайн — статус.\n\n"
        "④ «что по [имя]» / /crm [имя] → crm_get.\n"
        "   Триггеры авто-сохранения в CRM из текста:\n"
        "   «договорились с», «встреча с», «[Имя] хочет», «[Имя] должен», «[Имя] обещал».\n"
        "   При сохранении даты следующего контакта → спроси:\n"
        "   «Поставить напоминание связаться с [имя] [дата]?»\n\n"
        "⑤ /mail / «почта» / «письма» / «что пришло» → mail_digest.\n"
        "   Только папка «Входящие». Фильтруй рассылки, автоуведомления, no-reply — не показывай.\n"
        "   Показывай: от кого, тема, требует ли ответа.\n\n"
        "⑥ «напиши письмо [кому] о [теме]» / «отправь письмо» → compose_email.\n"
        "   Если нужны цифры или даты → сначала вызови query_sheets, подтяни данные,\n"
        "   затем составляй письмо с реальными числами.\n"
        "   Показать черновик → ждать правок или ✅ → только тогда отправить.\n"
        "   Контакты: Виктор (karpenko@entens.ru), Катя (info@entens.ru), Алексей (ap@entens.ru).\n"
        "   НЕЛЬЗЯ отправлять без явного подтверждения.\n\n"
        "⑦ Фото → analyze_photo.\n"
        "   Чек → поставщик, сумма, дата, позиции.\n"
        "   Накладная → поставщик, позиции, итоговая сумма.\n"
        "   Договор → стороны, предмет, сумма, срок, ключевые условия.\n"
        "   Список / текст → транскрибируй дословно.\n"
        "   Если тип = «проблема на объекте»:\n"
        "     1. Опиши проблему кратко.\n"
        "     2. Спроси: «Кому поставить задачу? Виктор / Евгения / Надежда / Управляющий / Тех.директор»\n"
        "     3. После ответа → уточни дедлайн → add_team_task (поле фото не заполняй).\n\n"
        "⑧ «запомни что...» / важный факт о человеке, компании, договорённости → remember_fact.\n"
        "   Категории не навязывай — используй тег по контексту. Память общая с Напоминатором.\n\n"
        "ЖЁСТКИЕ ЗАПРЕТЫ:\n"
        "- НЕЛЬЗЯ ставить задачу без дедлайна.\n"
        "- НЕЛЬЗЯ выдумывать данные из таблиц.\n"
        "- НЕЛЬЗЯ записывать задачу с нечётким именем без уточнения.\n"
        "- НЕЛЬЗЯ отправлять письмо без подтверждения.\n"
        "- НЕЛЬЗЯ предлагать альтернативный период если данных нет — говори прямо.\n\n"
        "СТИЛЬ: коротко и конкретно. Уточняй неполные запросы — не угадывай."
    )
    try:
        sys.path.insert(0, "/home/parser/bots/shared")
        from rule_engine import get_system_addons as _get_addons
        addons = _get_addons("helper")
        if addons:
            base_prompt += f"\n\nПРАВИЛА ПОЛЬЗОВАТЕЛЯ:\n{addons}"
    except Exception:
        pass
    return base_prompt

# ── Нормализация ASR-ошибок Whisper ──────────────────────────────
_ASR_FIXES = [
    # Монблан — частые ошибки распознавания
    (r'\bмаун\w*лан\w*', 'монблан'),
    (r'\bман\w*лан\w*', 'монблан'),
    (r'\bмонб\w{2,}\b', 'монблан'),
    (r'\bmont\s*blanc\b', 'монблан'),
]
def _fix_asr(text: str) -> str:
    result = text
    for pattern, replacement in _ASR_FIXES:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result

# ── Очистка ответа ────────────────────────────────────────────────
def _clean(text: str) -> str:
    text = re.sub(r'<\|?\s*(?:think|thinking|DSML)\s*\|?>.*?<\|?\s*/?\s*(?:think|thinking|DSML)\s*\|?>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() or "(пустой ответ)"

# ── Транскрипция голоса ───────────────────────────────────────────
async def transcribe_voice(message: Message) -> str:
    voice = message.voice or message.audio
    if not voice:
        return ""
    file = await bot.get_file(voice.file_id)
    file_bytes = await bot.download_file(file.file_path)
    groq_client = Groq(api_key=config.GROQ_API_KEY)
    try:
        tr = groq_client.audio.transcriptions.create(
            file=("voice.ogg", file_bytes.read()),
            model="whisper-large-v3-turbo",
            language="ru",
        )
        return tr.text.strip()
    except Exception as e:
        return f"[Не удалось распознать: {e}]"

# ── Безопасная отправка (fallback без Markdown) ───────────────────
async def _safe_answer(message: Message, text: str, parse_mode: str = "Markdown"):
    try:
        await message.answer(text, parse_mode=parse_mode)
    except Exception:
        # Если Markdown сломан — отправляем plain text
        await message.answer(text, parse_mode=None)

# ── Typing indicator ──────────────────────────────────────────────
async def _keep_typing(chat_id: int, stop: asyncio.Event):
    while not stop.is_set():
        await bot.send_chat_action(chat_id, "typing")
        try:
            await asyncio.wait_for(stop.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass

# ── LLM вызов ────────────────────────────────────────────────────
async def run_llm(messages: list, model: str = None) -> str:
    m = model or config.MODEL
    resp = await ai_client.chat.completions.create(
        model=m,
        messages=messages,
        max_tokens=2000,
        temperature=0.5,
    )
    msg = resp.choices[0].message
    content = (msg.content or "").strip()
    if not content and hasattr(msg, "reasoning"):
        content = (msg.reasoning or "")[-600:]
    return _clean(content)


# ══════════════════════════════════════════════════════════════════
# БЛОК 1: ЗАДАЧИ КОМАНДЕ ГУБАХА → Google Sheets
# ══════════════════════════════════════════════════════════════════
_TEAM_ALIASES = {
    "виктор": "Виктор", "viktor": "Виктор",
    "евгения": "Евгения", "женя": "Евгения",
    "надежда": "Надежда", "надя": "Надежда",
    "управляющий": "Управляющий",
    "техдиректор": "Тех.директор", "тех.директор": "Тех.директор",
    "технический директор": "Тех.директор",
}

def _normalize_executor(name: str) -> str:
    return _TEAM_ALIASES.get(name.strip().lower(), name.strip().capitalize())

def _add_gubaha_task_sync(executor: str, task: str, deadline: str = "") -> str:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_service_account_file(
        config.PERSONAL_SA, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    executor_clean = _normalize_executor(executor)
    row = [executor_clean, "Устно", task.strip(), "", "", deadline]
    svc.spreadsheets().values().append(
        spreadsheetId=config.STRATEGY_SHEET_ID,
        range="'Задачи недели'!A:F",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
    deadline_str = f" (срок: {deadline})" if deadline else ""
    return f"✅ Задача добавлена: *{executor_clean}* — {task}{deadline_str}"

async def add_gubaha_task(executor: str, task: str, deadline: str = "") -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _add_gubaha_task_sync, executor, task, deadline)

# Детектор задачи в тексте
_TASK_RE = re.compile(
    r"(виктор[уа]?|евгени[ия]|жен[ея]|надежд[еы]?|над[еяь]|управляющему?|техдиректор[уа]?|тех\.директор[уа]?)"
    r"[\s,]+задач[ауие]?:?\s*(.+?)(?:\s+(?:до|срок|дедлайн)\s+(.+))?$",
    re.IGNORECASE | re.DOTALL
)


# ══════════════════════════════════════════════════════════════════
# БЛОК 2: CRM
# ══════════════════════════════════════════════════════════════════
_CRM_DB = Path(config.DATA_DIR) / "crm.db"

def _crm_conn():
    _CRM_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_CRM_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        note TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON contacts(name COLLATE NOCASE)")
    conn.commit()
    return conn

def crm_save(name: str, note: str) -> str:
    name_clean = name.strip().title()
    conn = _crm_conn()
    conn.execute("INSERT INTO contacts (name, note) VALUES (?, ?)", (name_clean, note.strip()))
    conn.commit()
    conn.close()
    return f"✅ CRM: сохранено для *{name_clean}*\n_{note.strip()}_"

def crm_get(name: str) -> str:
    conn = _crm_conn()
    rows = conn.execute(
        "SELECT note, created_at FROM contacts WHERE name LIKE ? ORDER BY id DESC LIMIT 8",
        (f"%{name.strip().title()}%",)
    ).fetchall()
    conn.close()
    if not rows:
        return f"По контакту «{name}» ничего не найдено."
    lines = [f"📇 *{name.strip().title()}*:"]
    for r in rows:
        lines.append(f"  • ({r['created_at'][:16]}) {r['note']}")
    return "\n".join(lines)

# Авто-детектор CRM фраз
_CRM_TRIGGERS = ["договорились с ", "сказал ", " хочет ", " должен ", "позвонить ", "встреча с "]


# ══════════════════════════════════════════════════════════════════
# БЛОК 3: ДАННЫЕ ИЗ ТАБЛИЦ
# ══════════════════════════════════════════════════════════════════

# ID таблиц (из Drive-папки 1mfJEc9_XefwJQUWbfnMLOFf7EKSKEJgL)
_MONBLAN_ID    = "1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI"  # Отчет из IIKO
_GOG_MONTHLY_ID = "1ADBN7fecyqFvEG6igJfVfwG2vso6oW742y3-ai9ps8c" # ЕжеМесячный отчет ГОГ
_GOG_WEEKLY_ID  = "1Ohm7tst750zDzSeIewJFj_cPC6vl0-5J0UiuNfZvY_k" # ЕжеНедельный отчет ГОГ

_MONTH_NUM = {
    "январ": 1, "феврал": 2, "март": 3, "марта": 3, "апрел": 4,
    "май": 5, "мая": 5, "июн": 6, "июл": 7,
    "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}
_MONTH_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}

def _idx_to_col(i: int) -> str:
    """Индекс колонки → буква (0=A, 26=AA, ...)"""
    if i < 26:
        return chr(65 + i)
    return chr(64 + i // 26) + chr(65 + i % 26)

def _parse_month_year(q: str) -> tuple:
    """Извлекает (месяц: int, год: int) из текста запроса."""
    year = datetime.now().year
    # Год: "26 года", "2026", "25", "2025"
    y_m = re.search(r'\b(20(\d{2})|(\d{2}))\s*(?:год|г\.?)?', q)
    if y_m:
        raw = y_m.group(1)
        y = int(raw)
        year = 2000 + y if y < 100 else y
    # Месяц
    for prefix, num in _MONTH_NUM.items():
        if prefix in q:
            return (num, year)
    return (None, year)

def _sheets_svc(sa_path: str):
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_service_account_file(
        sa_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)

def _read_range(sa_path: str, sheet_id: str, range_str: str) -> list:
    return _sheets_svc(sa_path).spreadsheets().values().get(
        spreadsheetId=sheet_id, range=range_str
    ).execute().get("values", [])

def _direct_lookup(rows_kv: list, question: str, context: str) -> str | None:
    """Прямой поиск без LLM — для типовых запросов по выручке/загрузке/гостям."""
    q = question.lower()
    result_lines = []

    # Выручка — ищем строку "Выручка всего"
    if any(k in q for k in ["выручк", "доход"]):
        for row in rows_kv:
            if re.match(r"выручка всего", row, re.IGNORECASE) or re.match(r"доход", row, re.IGNORECASE):
                if ":" in row:
                    label, value = row.split(":", 1)
                    return f"{label.strip()} {context}: {value.strip()} руб."

    # Загрузка
    if "загрузк" in q:
        for row in rows_kv:
            if re.match(r"загрузка", row, re.IGNORECASE) and ":" in row:
                label, value = row.split(":", 1)
                return f"{label.strip()} {context}: {value.strip()}"

    # Гости / количество гостей
    if any(k in q for k in ["гост", "посетит", "человек"]):
        for row in rows_kv:
            if re.match(r"(кол-во гостей|гост|посетит)", row, re.IGNORECASE) and ":" in row:
                label, value = row.split(":", 1)
                return f"{label.strip()} {context}: {value.strip()}"

    # ADR / RevPar
    if "adr" in q:
        for row in rows_kv:
            if re.match(r"adr", row, re.IGNORECASE) and ":" in row:
                label, value = row.split(":", 1)
                return f"{label.strip()} {context}: {value.strip()} руб."
    if "revpar" in q:
        for row in rows_kv:
            if re.match(r"revpar", row, re.IGNORECASE) and ":" in row:
                label, value = row.split(":", 1)
                return f"{label.strip()} {context}: {value.strip()} руб."

    return None   # не нашли — идём в LLM

def _extract_answer(text: str, question: str = "") -> str:
    """Вырезает финальный ответ из текста с рассуждениями DeepSeek."""
    if not text:
        return ""
    # Убираем кавычки и артефакты в начале
    text = text.strip().strip('"«»').strip()
    # Если ответ — эхо вопроса (похоже на повтор), возвращаем пусто
    if question:
        q_words = set(re.findall(r'\w{4,}', question.lower()))
        a_words = set(re.findall(r'\w{4,}', text.lower()))
        overlap = len(q_words & a_words) / max(len(q_words), 1)
        if overlap > 0.6 and not re.search(r'\d{3,}', text):
            return "Нет данных за этот период."
    # Ищем строку с числом (ответ с цифрой) или вопросом
    for line in text.split("\n"):
        line = line.strip().strip('"«»').strip()
        if not line:
            continue
        if re.search(r'\d{3,}', line):   # есть число ≥ 3 цифр — это цифра выручки
            return line
        if line.endswith("?"):            # уточняющий вопрос
            return line
    # Fallback — первая непустая строка
    for line in text.split("\n"):
        line = line.strip()
        if line:
            return line[:200]
    return text[:200]

# Загрузка данных (sync) — возвращает (rows_kv, context)
def _monblan_monthly_load(month: int, year: int) -> tuple:
    svc = _sheets_svc(config.MONBLAN_SA)
    header = svc.spreadsheets().values().get(
        spreadsheetId=_MONBLAN_ID, range="ЕжеМесячный!A2:AZ2"
    ).execute().get("values", [[]])[0]
    target = f"{year}-{month:02d}"
    if target not in header:
        return (None, f"Данных Монблан за {_MONTH_RU.get(month, month)} {year} нет в таблице.")
    col_idx = header.index(target)
    col_letter = _idx_to_col(col_idx)
    rows = svc.spreadsheets().values().get(
        spreadsheetId=_MONBLAN_ID, range=f"ЕжеМесячный!A3:{col_letter}60"
    ).execute().get("values", [])
    kv = []
    for row in rows:
        label = row[0].strip() if row and row[0] else ""
        value = row[col_idx].strip() if len(row) > col_idx and row[col_idx] else ""
        if label and value and not label.startswith("%"):
            kv.append(f"{label}: {value}")
    return (kv, f"Монблан {_MONTH_RU.get(month, month)} {year}")

def _gog_monthly_load(month: int, year: int) -> tuple:
    short_year = str(year)[-2:]
    sheet_name = f"{_MONTH_RU.get(month, month)} {short_year}"
    try:
        rows = _read_range(config.AIHOTEL_SA, _GOG_MONTHLY_ID, f"'{sheet_name}'!A1:F30")
    except Exception:
        return (None, f"Данных ГОГ за {sheet_name} нет в таблице.")
    kv = []
    for row in rows:
        if len(row) >= 2 and row[1]:
            parts = [row[1]]
            if len(row) > 2 and row[2]: parts.append(f"{year-1}: {row[2]}")
            if len(row) > 4 and row[4]: parts.append(f"{year}: {row[4]}")
            kv.append(" | ".join(parts))
    return (kv, f"ГОГ Губаха {sheet_name}")

def _load_sheets_data(question: str) -> tuple:
    """Sync: роутинг и загрузка данных. Возвращает (rows_kv | None, context_or_error)."""
    q = question.lower()
    month, year = _parse_month_year(q)
    is_monblan = any(k in q for k in ["монблан", "monblan", "кафе", "ресторан"])
    is_gog     = any(k in q for k in ["губаха", "отель", "хостел", "коттедж", "гог", "номер", "загрузк", "заезд", "бронь"])
    is_weekly  = any(k in q for k in ["недел", "неделю", "неделя"])
    is_daily   = any(k in q for k in ["сегодня", "вчера", "день", "дневн"])
    is_tasks   = any(k in q for k in ["задач", "kpi", "стратег"])

    if is_tasks:
        rows = _read_range(config.PERSONAL_SA, config.STRATEGY_SHEET_ID, "'Задачи недели'!A1:H50")
        kv = [" | ".join(str(c) for c in row if c) for row in rows if any(row)]
        return (kv, "Задачи недели Губаха")

    if is_monblan:
        if month and not is_weekly and not is_daily:
            return _monblan_monthly_load(month, year)
        elif is_daily:
            rows = _read_range(config.MONBLAN_SA, _MONBLAN_ID, "ЕжеДневно!A1:AZ15")
            kv = [" | ".join(str(c) for c in row if c) for row in rows if any(row)]
            return (kv, "Монблан ежедневно")
        else:
            rows = _read_range(config.MONBLAN_SA, _MONBLAN_ID, "ЕжеНедельно!A1:CZ30")
            kv = [" | ".join(str(c) for c in row[:15] if c) for row in rows if any(row)]
            return (kv, "Монблан еженедельно")

    if is_gog or (not is_monblan and month):
        if month and not is_weekly:
            return _gog_monthly_load(month, year)
        else:
            rows = _read_range(config.AIHOTEL_SA, _GOG_WEEKLY_ID, "Дайджест!A1:D50")
            kv = [" | ".join(str(c) for c in row if c) for row in rows if any(row)]
            return (kv, "ГОГ Губаха еженедельный дайджест")

    return (None, "Уточни: это про Монблан (кафе) или про Губаха (отель/коттеджи/хостел)?")

async def query_sheets(question: str) -> str:
    """Async: грузит данные → прямой поиск → если не нашли, спрашивает Claude."""
    loop = asyncio.get_event_loop()
    rows_kv, context = await loop.run_in_executor(None, _load_sheets_data, question)

    if rows_kv is None:
        return context

    # 1. Сначала прямой поиск без LLM (быстро и точно)
    direct = _direct_lookup(rows_kv, question, context)
    if direct:
        return direct

    # 2. Fallback — Claude для сложных/составных вопросов
    today = datetime.now(_MSK).strftime("%d.%m.%Y")
    table_str = "\n".join(rows_kv[:60])
    resp = await ai_client.chat.completions.create(
        model=config.VISION_MODEL,
        messages=[
            {"role": "system", "content": (
                f"Данные из таблицы за {context} (уже загружены, период точный).\n"
                "Ответь на вопрос одной строкой: метрика и число. Пример: Кухня март 2026: 2 564 170 руб.\n"
                "Только цифра, никаких объяснений."
            )},
            {"role": "user", "content": f"{table_str}\n\n{question}\n\nОтвет:"}
        ],
        max_tokens=60,
        temperature=0.0,
    )
    raw = (resp.choices[0].message.content or "").strip()
    return _extract_answer(raw, question) or f"Данные за {context} загружены, но ответ не найден."

_SHEETS_KEYWORDS = ["выручка", "загрузка", "гост", "бронь", "заезд", "фудкост",
                    "монблан", "губаха", "отель", "хостел", "коттедж", "номер", "adr", "revpar"]


# ══════════════════════════════════════════════════════════════════
# БЛОК 4: EMAIL (ab@entens.ru, Mail.ru)
# ══════════════════════════════════════════════════════════════════
_MAIL_CONTACTS = {
    "виктор": "karpenko@entens.ru",
    "алексей": "ap@entens.ru",
    "катя": "info@entens.ru",
    "алексей личная": "aprosandeev@mail.ru",
    "себе": "ab@entens.ru",
}

def _mail_cfg() -> dict:
    return json.loads(Path(config.MAILRU_CFG).read_text())

def _resolve_email(name: str) -> str:
    if "@" in name:
        return name
    key = name.lower().strip()
    for k, v in _MAIL_CONTACTS.items():
        if key in k or k in key:
            return v
    raise ValueError(f"Контакт не найден: {name}")

def _smtp_send(to: str, subject: str, body: str) -> None:
    cfg = _mail_cfg()
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = f"{Header(cfg.get('display_name',''), 'utf-8').encode()} <{cfg['email']}>"
    msg["To"] = to
    msg["Subject"] = Header(subject, "utf-8").encode()
    msg["Date"] = email.utils.formatdate(localtime=True)
    with smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"]) as server:
        server.login(cfg["email"], cfg["password"])
        server.sendmail(cfg["email"], [to], msg.as_string().encode("utf-8"))

def _imap_connect():
    cfg = _mail_cfg()
    mail = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"])
    mail.login(cfg["email"], cfg["password"])
    return mail

def _decode_hdr(raw: str) -> str:
    parts = email.header.decode_header(raw or "")
    return " ".join(
        p.decode(c or "utf-8", errors="replace") if isinstance(p, bytes) else p
        for p, c in parts
    )

def mail_digest_sync() -> str:
    import urllib.request
    mail = _imap_connect()
    mail.select("INBOX")
    since = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
    _, uids = mail.search(None, f'(SINCE "{since}" UNSEEN)')
    mail_uids = uids[0].split() if uids[0] else []
    if not mail_uids:
        mail.logout()
        return "📭 Нет новых писем за 24 часа."
    summaries = []
    for uid in mail_uids[-15:]:
        _, data = mail.fetch(uid, "(RFC822.HEADER)")
        msg = email_lib.message_from_bytes(data[0][1])
        summaries.append(f"UID:{uid.decode()} От:{_decode_hdr(msg.get('From',''))[:50]} Тема:{_decode_hdr(msg.get('Subject',''))[:70]}")
    mail.logout()
    inbox_text = "\n".join(summaries)
    payload = {
        "model": config.MODEL,
        "messages": [
            {"role": "system", "content": "Помощник. Кратко по-русски."},
            {"role": "user", "content": f"Входящие:\n{inbox_text}\n\nВыдели требующие ответа: от кого, тема, что сделать, UID."}
        ],
        "max_tokens": 1500, "temperature": 0.2,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{config.ROUTERAI_BASE_URL}/chat/completions", data=data,
        headers={"Authorization": f"Bearer {config.ROUTERAI_API_KEY}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode())
    msg_r = result["choices"][0]["message"]
    return f"📬 Дайджест ({len(mail_uids)} непрочитанных):\n\n" + ((msg_r.get("content") or "").strip() or (msg_r.get("reasoning") or "")[-600:])

# Pending email drafts
_pending_drafts: dict[int, dict] = {}

async def compose_email(user_id: int, recipient: str, subject_hint: str, voice_text: str) -> str:
    to_email = _resolve_email(recipient)
    today = datetime.now(_MSK).strftime("%d.%m.%Y")
    prompt = (
        f"Напиши деловое письмо.\nПолучатель: {recipient}\nТема: {subject_hint}\n"
        f"Содержание: {voice_text}\nОтвет — JSON: {{\"subject\": \"...\", \"body\": \"...\"}}"
    )
    resp = await ai_client.chat.completions.create(
        model=config.MODEL,
        messages=[
            {"role": "system", "content": f"Деловая переписка. Отправитель — Александр Бениаминов (ab@entens.ru). Сегодня {today}."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1500, temperature=0.3,
    )
    msg = resp.choices[0].message
    content = (msg.content or "").strip()
    try:
        parsed = json.loads(content.replace("```json","").replace("```","").strip())
        subject = parsed.get("subject", subject_hint)
        body = parsed.get("body", voice_text)
    except Exception:
        subject, body = subject_hint, content

    _pending_drafts[user_id] = {"to": to_email, "subject": subject, "body": body}
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Отправить", callback_data="mail_send"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="mail_cancel"),
    ]])
    return (f"📧 Черновик:\nКому: {to_email}\nТема: {subject}\n\n{body}", kb)


# ══════════════════════════════════════════════════════════════════
# БЛОК 5: ВЕБ-ПОИСК (DuckDuckGo)
# ══════════════════════════════════════════════════════════════════
_SEARCH_RE = re.compile(
    r"^(найди|поищи|найдите|поищите|погугли|ищи|покажи|расскажи про|что такое|кто такой|узнай)\b",
    re.IGNORECASE
)

def _web_search(query: str, max_results: int = 6) -> str:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "По этому запросу ничего не найдено."
        lines = []
        for r in results:
            lines.append(f"{r['title']}\n{r['body']}\n{r['href']}")
        return "\n\n".join(lines)
    except Exception as e:
        return f"Ошибка поиска: {e}"

async def web_search_and_answer(query: str) -> str:
    """Ищет в интернете и суммаризирует ответ через LLM."""
    loop = asyncio.get_event_loop()
    raw = await loop.run_in_executor(None, _web_search, query)
    if raw.startswith("Ошибка") or raw.startswith("По этому"):
        return raw
    now = datetime.now(_MSK).strftime("%d.%m.%Y %H:%M")
    messages = [
        {"role": "system", "content": f"Ты помощник. Сейчас {now} МСК. Отвечай коротко по-русски — только факты из результатов поиска."},
        {"role": "user", "content": f"Запрос: {query}\n\nРезультаты поиска:\n{raw}\n\nДай краткий ответ."}
    ]
    return await run_llm(messages)


# ══════════════════════════════════════════════════════════════════
# БЛОК 6: ФОТО (Vision через Claude)
# ══════════════════════════════════════════════════════════════════
async def analyze_photo(message: Message, voice_hint: str = "") -> str:
    photo = message.photo[-1] if message.photo else None
    if not photo:
        return "Фото не найдено."
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    img_b64 = base64.b64encode(file_bytes.read()).decode("utf-8")

    hint_part = f"\n\nКомментарий пользователя: {voice_hint}" if voice_hint else ""
    user_content = [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
        {"type": "text", "text": (
            "Проанализируй фото. Определи тип: проблема на объекте / документ / чек / накладная / список / другое.\n"
            "Для проблемы: опиши коротко что не так.\n"
            "Для документа/чека: извлеки поставщик, сумму, дату, ключевые условия.\n"
            "Для списка/текста: транскрибируй дословно.\n"
            "Отвечай по-русски, структурированно." + hint_part
        )}
    ]
    resp = await ai_client.chat.completions.create(
        model=config.VISION_MODEL,
        messages=[{"role": "user", "content": user_content}],
        max_tokens=1000,
    )
    return (resp.choices[0].message.content or "").strip()


# ══════════════════════════════════════════════════════════════════
# БЛОК 6: ПРОЕКТНЫЕ ЗАМЕТКИ → Google Sheets
# ══════════════════════════════════════════════════════════════════
_PROJ_NOTES_SHEET_ID = "1aiCKUs-Le-adHSfAOOC2AHRs1vCWzm-E3lucPTbRRkc"
_PROJ_MAP = {
    "губаха": "Губаха", "губахи": "Губаха", "губахе": "Губаха", "губаху": "Губаха",
    "юникорн": "Юникорн", "unicorn": "Юникорн",
    "прочее": "Без проекта", "офис": "Без проекта",
    "разное": "Без проекта", "без проекта": "Без проекта",
}
_PROJ_RE = re.compile(
    r"(?:для\s+)?(?:проект(?:а|е|у)?\s+)?(губах[аиу]?|юникорн|unicorn|прочее?|офис|разное|без\s+проекта)\W+(.+)",
    re.IGNORECASE | re.DOTALL
)

def _save_proj_note_sync(project_raw: str, text: str) -> str:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    project = _PROJ_MAP.get(project_raw.strip().lower(), project_raw.strip().capitalize())
    now = datetime.now()
    creds = Credentials.from_service_account_file(
        config.PERSONAL_SA, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    meta = svc.spreadsheets().get(spreadsheetId=_PROJ_NOTES_SHEET_ID).execute()
    if project not in [s["properties"]["title"] for s in meta["sheets"]]:
        svc.spreadsheets().batchUpdate(spreadsheetId=_PROJ_NOTES_SHEET_ID, body={
            "requests": [{"addSheet": {"properties": {"title": project}}}]
        }).execute()
        svc.spreadsheets().values().update(
            spreadsheetId=_PROJ_NOTES_SHEET_ID, range=f"'{project}'!A1:C1",
            valueInputOption="USER_ENTERED", body={"values": [["Дата","Время","Мысль / Идея / План"]]}
        ).execute()
    svc.spreadsheets().values().append(
        spreadsheetId=_PROJ_NOTES_SHEET_ID, range=f"'{project}'!A:C",
        valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
        body={"values": [[now.strftime("%d.%m.%Y"), now.strftime("%H:%M"), text.strip()]]},
    ).execute()
    return f"✅ Записано в *{project}*:\n_{text.strip()}_"


# ══════════════════════════════════════════════════════════════════
# HANDLERS
# ══════════════════════════════════════════════════════════════════
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer(
        "👋 *Помощник* — работаю 24/7\n\n"
        "Что умею:\n"
        "• Задачи команде Губаха → Sheets\n"
        "• Данные из таблиц голосом\n"
        "• CRM контактов\n"
        "• Почта ab@entens.ru\n"
        "• Фото → анализ/задача\n"
        "• Проектные заметки\n\n"
        "/help — подробная шпаргалка",
        parse_mode="Markdown"
    )

@dp.message(Command("new", "reset"))
async def cmd_reset(message: Message):
    if not is_allowed(message.from_user.id):
        return
    histories.pop(message.from_user.id, None)
    await message.answer("🔄 Контекст очищен.")

@dp.message(Command("crm"))
async def cmd_crm(message: Message):
    if not is_allowed(message.from_user.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /crm Богданов")
        return
    await message.answer(crm_get(args[1]), parse_mode="Markdown")

@dp.message(Command("mail"))
async def cmd_mail(message: Message):
    if not is_allowed(message.from_user.id):
        return
    loop = asyncio.get_event_loop()
    await message.answer("📬 Загружаю...")
    result = await loop.run_in_executor(None, mail_digest_sync)
    await message.answer(result, parse_mode="Markdown")

# ── Callback: отправить / отменить письмо ─────────────────────────
@dp.callback_query(F.data == "mail_send")
async def cb_mail_send(call: CallbackQuery):
    user_id = call.from_user.id
    draft = _pending_drafts.pop(user_id, None)
    if not draft:
        await call.answer("Черновик не найден.")
        return
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _smtp_send, draft["to"], draft["subject"], draft["body"])
        await call.message.edit_text(f"✅ Письмо отправлено!\nКому: {draft['to']}\nТема: {draft['subject']}")
    except Exception as e:
        await call.message.edit_text(f"❌ Ошибка отправки: {e}")

@dp.callback_query(F.data == "mail_cancel")
async def cb_mail_cancel(call: CallbackQuery):
    _pending_drafts.pop(call.from_user.id, None)
    await call.message.edit_text("🗑 Письмо отменено.")

# ── Фото ──────────────────────────────────────────────────────────
_pending_photo_voice: dict[int, Message] = {}

@dp.message(F.photo)
async def handle_photo(message: Message):
    if not is_allowed(message.from_user.id):
        return
    caption = message.caption or ""
    stop = asyncio.Event()
    typing = asyncio.create_task(_keep_typing(message.chat.id, stop))
    try:
        result = await analyze_photo(message, caption)
    finally:
        stop.set(); typing.cancel()
        try: await typing
        except asyncio.CancelledError: pass

    # Если упомянута задача и исполнитель → предложить записать
    task_m = _TASK_RE.search(caption)
    if task_m:
        executor = task_m.group(1)
        task_text = task_m.group(2) or result[:100]
        loop = asyncio.get_event_loop()
        task_result = await loop.run_in_executor(None, _add_gubaha_task_sync, executor, task_text, "")
        await message.answer(f"{result}\n\n{task_result}", parse_mode="Markdown")
    else:
        await message.answer(result, parse_mode="Markdown")

# ── Главный обработчик текст/голос ───────────────────────────────
@dp.message(F.text | F.voice)
async def handle_message(message: Message):
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return

    if message.voice:
        text = await transcribe_voice(message)
        if text.startswith("[Не удалось"):
            await message.answer(text)
            return
        text = _fix_asr(text)   # исправляем ошибки Whisper
        await message.answer(f"🎙 _{text}_", parse_mode="Markdown")
    else:
        text = message.text

    q = text.lower()

    # ── 1. Проектные заметки ──────────────────────────────────────
    proj_m = _PROJ_RE.match(text.strip())
    if proj_m:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _save_proj_note_sync, proj_m.group(1), proj_m.group(2))
        await message.answer(result, parse_mode="Markdown")
        return

    # ── 2. Задача команде Губаха ──────────────────────────────────
    task_m = _TASK_RE.search(text)
    if task_m:
        result = await add_gubaha_task(task_m.group(1), task_m.group(2), task_m.group(3) or "")
        await message.answer(result, parse_mode="Markdown")
        return

    # ── 3. CRM запрос ─────────────────────────────────────────────
    crm_q = re.match(r"что по (.+?)\??$", q)
    if crm_q:
        await message.answer(crm_get(crm_q.group(1)), parse_mode="Markdown")
        return

    # ── 4. CRM авто-сохранение ────────────────────────────────────
    for trigger in _CRM_TRIGGERS:
        if trigger in q:
            # Простое авто-сохранение — имя после триггера
            idx = q.find(trigger)
            snippet = text[idx:idx+120]
            # Имя — первое слово с большой буквы после триггера
            name_m = re.search(r'\b([А-ЯЁ][а-яёА-ЯЁ]+)\b', snippet)
            if name_m:
                crm_save(name_m.group(1), text.strip())
            break

    # ── 5. Данные из таблиц ───────────────────────────────────────
    if any(k in q for k in _SHEETS_KEYWORDS):
        await message.answer("📊 Загружаю данные...")
        stop = asyncio.Event()
        typing = asyncio.create_task(_keep_typing(message.chat.id, stop))
        try:
            result = await query_sheets(text)
        except Exception as e:
            result = f"Ошибка загрузки данных: {e}"
        finally:
            stop.set(); typing.cancel()
            try: await typing
            except asyncio.CancelledError: pass
        await _safe_answer(message, result, parse_mode=None)
        return

    # ── 6. Почта — дайджест ───────────────────────────────────────
    if any(k in q for k in ["почта", "письм", "входящ", "пришло на почту"]):
        await message.answer("📬 Загружаю...")
        stop = asyncio.Event()
        typing = asyncio.create_task(_keep_typing(message.chat.id, stop))
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, mail_digest_sync)
        finally:
            stop.set(); typing.cancel()
            try: await typing
            except asyncio.CancelledError: pass
        await _safe_answer(message, result)
        return

    # ── 7. Написать письмо ────────────────────────────────────────
    email_m = re.match(r"напиши(?:\s+письмо)?\s+(\w+)\s+(?:о|про|насчёт|по\s+поводу)?\s*(.+)", q)
    if email_m or ("отправь письмо" in q) or ("напиши письмо" in q):
        # Извлекаем получателя и тему
        if email_m:
            recipient = email_m.group(1)
            content = email_m.group(2)
        else:
            recipient = "себе"
            content = text
        try:
            result, kb = await compose_email(user_id, recipient, content[:50], content)
            await message.answer(result, reply_markup=kb, parse_mode="Markdown")
        except ValueError as e:
            await message.answer(f"❌ {e}")
        return

    # ── 8. Веб-поиск ─────────────────────────────────────────────
    if _SEARCH_RE.match(text.strip()) or any(k in q for k in ["расписание", "онлайн табло", "курс валют", "погода", "новости"]):
        stop = asyncio.Event()
        typing = asyncio.create_task(_keep_typing(message.chat.id, stop))
        try:
            result = await web_search_and_answer(text)
        finally:
            stop.set(); typing.cancel()
            try: await typing
            except asyncio.CancelledError: pass
        await _safe_answer(message, result)
        return

    # ── 9. AI-чат (fallback) ──────────────────────────────────────
    history = histories.setdefault(user_id, [])
    if not history:
        history.append({"role": "system", "content": _system_prompt()})
    history.append({"role": "user", "content": text})
    if len(history) > 22:
        histories[user_id] = history[:1] + history[-20:]
        history = histories[user_id]

    stop = asyncio.Event()
    typing = asyncio.create_task(_keep_typing(message.chat.id, stop))
    try:
        response = await run_llm(history)
    except Exception as e:
        response = f"Ошибка: {e}"
    finally:
        stop.set(); typing.cancel()
        try: await typing
        except asyncio.CancelledError: pass

    try:
        from rule_engine import apply_rules as _apply_rules
        response = await _apply_rules(response, text, "helper", ai_client)
    except Exception:
        pass

    history.append({"role": "assistant", "content": response})
    await _safe_answer(message, response)


# ══════════════════════════════════════════════════════════════════
# ЗАПУСК
# ══════════════════════════════════════════════════════════════════
async def main():
    print(f"[{datetime.now(_MSK).strftime('%H:%M:%S')} МСК] Помощник запущен.")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
