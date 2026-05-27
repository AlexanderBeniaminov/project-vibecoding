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
    return (
        f"Ты личный помощник Александра Бениаминова. Сейчас {now} МСК. "
        "Язык: русский. "
        "Ты умеешь: ставить задачи команде Губаха, читать данные из таблиц, "
        "управлять CRM-контактами, работать с почтой ab@entens.ru, "
        "анализировать фото документов и проблем на объекте. "
        "ВАЖНЫЕ ПРАВИЛА: "
        "1. Если запрос непонятен или не хватает информации для выполнения — задай уточняющий вопрос. Не угадывай. "
        "2. Продолжай уточнять до тех пор, пока не сможешь выполнить задачу на 100%. "
        "3. Если всё понятно — отвечай коротко и конкретно, максимум 2-3 предложения. "
        "4. Никогда не выдумывай данные и не рассуждай вслух."
    )

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
def _sheets_read(sa_path: str, sheet_id: str, range_str: str) -> list:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_service_account_file(
        sa_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return svc.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=range_str
    ).execute().get("values", [])

def _ask_ai_sync(table_data: list, query: str, context: str) -> str:
    import urllib.request
    rows_text = [" | ".join(str(c) for c in row[:20]) for row in table_data[:40]]
    table_str = "\n".join(rows_text)
    today = datetime.now().strftime("%d.%m.%Y")
    payload = {
        "model": config.MODEL,
        "messages": [
            {"role": "system", "content": (
                f"Ты аналитик данных. Сегодня {today}. "
                "ЗАПРЕЩЕНО: рассуждать, объяснять структуру таблицы, думать вслух, писать промежуточные вычисления. "
                "РАЗРЕШЕНО только одно из двух: "
                "A) Если ответ есть в данных — одна строка с цифрой. Формат: «[Метрика] за [период]: [число] ₽». "
                "B) Если ответа нет или запрос неоднозначен — один короткий уточняющий вопрос. "
                "Примеры правильных ответов: "
                "«Выручка Монблан за апрель 2026: 4 823 500 ₽» "
                "«За какой год интересует апрель — 2025 или 2026?»"
            )},
            {"role": "user", "content": f"Таблица ({context}):\n{table_str}\n\nВопрос пользователя: {query}\n\nОтвет (одна строка):"}
        ],
        "max_tokens": 100, "temperature": 0.0,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{config.ROUTERAI_BASE_URL}/chat/completions", data=data,
        headers={"Authorization": f"Bearer {config.ROUTERAI_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    msg = result["choices"][0]["message"]
    content = (msg.get("content") or "").strip()
    return content or (msg.get("reasoning") or "")[-500:]

def query_sheets_sync(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ["монблан", "ресторан", "monblan"]):
        _months = ["январ", "феврал", "март", "апрел", "май", "июн", "июл",
                   "август", "сентябр", "октябр", "ноябр", "декабр", "месяц"]
        if any(w in q for w in _months):
            data = _sheets_read(config.MONBLAN_SA, config.MONBLAN_SHEET_ID, "ЕжеМесячный!A1:Z30")
            ctx = "Монблан ежемесячная таблица"
        elif any(w in q for w in ["сегодня", "вчера", "день"]):
            data = _sheets_read(config.MONBLAN_SA, config.MONBLAN_SHEET_ID, "ЕжеДневно!A1:AZ15")
            ctx = "Монблан ежедневная таблица"
        else:
            data = _sheets_read(config.MONBLAN_SA, config.MONBLAN_SHEET_ID, "ЕжеНедельно!A1:CZ30")
            ctx = "Монблан еженедельная таблица"
    elif any(k in q for k in ["задачи", "kpi", "стратег"]):
        data = _sheets_read(config.PERSONAL_SA, config.STRATEGY_SHEET_ID, "'Задачи недели'!A1:F50")
        ctx = "Губаха задачи недели"
    else:
        try:
            data = _sheets_read(config.AIHOTEL_SA, config.GUBAHA_FINANCE_SHEET_ID, "Дайджест!A1:D50")
            ctx = "Губаха финансовый дайджест"
        except Exception:
            data = _sheets_read(config.AIHOTEL_SA, config.GUBAHA_FINANCE_SHEET_ID, "2026!A1:Z30")
            ctx = "Губаха финансы 2026"
    return _ask_ai_sync(data, question, ctx)

_SHEETS_KEYWORDS = ["выручка", "загрузка", "гост", "бронь", "заезд", "фудкост", "монблан", "губаха"]


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
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, query_sheets_sync, text)
        await message.answer(result, parse_mode="Markdown")
        return

    # ── 6. Почта — дайджест ───────────────────────────────────────
    if any(k in q for k in ["почта", "письм", "входящ", "пришло на почту"]):
        loop = asyncio.get_event_loop()
        await message.answer("📬 Загружаю...")
        result = await loop.run_in_executor(None, mail_digest_sync)
        await message.answer(result, parse_mode="Markdown")
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
        await message.answer(result, parse_mode="Markdown")
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

    history.append({"role": "assistant", "content": response})
    await message.answer(response, parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════════
# ЗАПУСК
# ══════════════════════════════════════════════════════════════════
async def main():
    print(f"[{datetime.now(_MSK).strftime('%H:%M:%S')} МСК] Помощник запущен.")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
