"""Google Sheets — визуальный слой. SQLite остаётся источником правды.
Push — мгновенно при событиях бота. Pull — APScheduler 2 раза в сутки (sheets.sync_from_sheets)."""
import hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

import config
import db

_MSK = ZoneInfo("Europe/Moscow")

SHEET_IDEAS = "📋 Идеи"
SHEET_POSTS = "✏️ Посты"
SHEET_CALENDAR = "📅 Календарь"
SHEET_BLACKLIST = "🚫 Блэклист"

_HEADERS = {
    SHEET_IDEAS: ["ID", "Дата", "Источник", "Тема", "Описание", "Статус", "Рубрика"],
    SHEET_POSTS: ["ID идеи", "Вариант", "Аудитория", "Формат", "Текст поста", "Статус", "Дата публикации", "Ссылка"],
    SHEET_CALENDAR: ["Дата", "День", "Время", "Тема", "Рубрика", "Статус", "Ссылка"],
    SHEET_BLACKLIST: ["Тема", "Режим", "Заблокировано до", "Причина", "Добавлено"],
}

_IDEA_SOURCE_LABEL = {"text": "✍️ текст", "voice": "🎙 голос", "manual": "✍️ Sheets"}
_IDEA_STATUS_LABEL = {"saved": "💾 Сохранена", "in_progress": "🔄 В работе", "paused": "⏸ Пауза"}
_POST_STATUS_DRAFT = "✏️ Черновик"
_POST_STATUS_APPROVED = "✅ Утверждён"
_POST_STATUS_SCHEDULED = "📅 Запланирован"
_POST_STATUS_PUBLISHED = "✔️ Опубликован"

_DAY_NAMES = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}

_client = None


def _get_client():
    global _client
    if _client is None:
        creds = Credentials.from_service_account_file(
            config.SERVICE_ACCOUNT_JSON,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        _client = gspread.authorize(creds)
    return _client


def _get_spreadsheet():
    return _get_client().open_by_key(config.SPREADSHEET_ID)


def ensure_sheets():
    """Создаёт листы с заголовками, если они ещё не существуют. Вызывать при старте бота."""
    ss = _get_spreadsheet()
    existing = {ws.title for ws in ss.worksheets()}
    for name, headers in _HEADERS.items():
        if name not in existing:
            ws = ss.add_worksheet(title=name, rows=200, cols=len(headers))
            ws.append_row(headers)


def _hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


# ── Push: бот → Sheets ────────────────────────────────────────
def push_idea(idea: dict):
    ws = _get_spreadsheet().worksheet(SHEET_IDEAS)
    created = datetime.fromisoformat(idea["created_at"])
    ws.append_row([
        idea["id"],
        created.strftime("%d.%m"),
        _IDEA_SOURCE_LABEL.get(idea["source"], idea["source"]),
        idea["text"],
        "",
        _IDEA_STATUS_LABEL.get(idea["status"], idea["status"]),
        idea["rubric"],
    ])


def push_generations(idea: dict, generations: list[dict]):
    ws = _get_spreadsheet().worksheet(SHEET_POSTS)
    for gen in generations:
        ws.append_row([
            idea["id"], gen["variant_num"], gen["audience"], gen["format"],
            gen["text"], _POST_STATUS_DRAFT, "", "",
        ])
        db.update_generation_hash(gen["id"], _hash(gen["text"]))


def push_scheduled(idea: dict, gen: dict, dt: datetime):
    _update_post_row(idea["id"], gen["variant_num"], status=_POST_STATUS_SCHEDULED,
                      publish_date=dt.strftime("%d.%m.%Y %H:%M"))
    ws = _get_spreadsheet().worksheet(SHEET_CALENDAR)
    ws.append_row([
        dt.strftime("%d.%m.%Y"), _DAY_NAMES[dt.weekday()], dt.strftime("%H:%M"),
        idea["text"], idea["rubric"], _POST_STATUS_SCHEDULED, "",
    ])


def push_published(idea: dict, gen: dict, link: str = ""):
    _update_post_row(idea["id"], gen["variant_num"], status=_POST_STATUS_PUBLISHED, link=link)
    ws = _get_spreadsheet().worksheet(SHEET_CALENDAR)
    rows = ws.get_all_values()
    for i, row in enumerate(rows[1:], start=2):
        if len(row) > 3 and row[3] == idea["text"]:
            ws.update_cell(i, 6, _POST_STATUS_PUBLISHED)
            ws.update_cell(i, 7, link)
            break


def push_blacklist_entry(entry: dict):
    ws = _get_spreadsheet().worksheet(SHEET_BLACKLIST)
    added = datetime.fromisoformat(entry["created_at"])
    mode_label = "⏳ Временно" if entry["mode"] == "temporary" else "♾ Навсегда"
    until = entry["blocked_until"][:10] if entry["blocked_until"] else "—"
    ws.append_row([entry["text"], mode_label, until, entry.get("reason", ""), added.strftime("%d.%m.%Y")])


def _update_post_row(idea_id: int, variant_num: int, status: str | None = None,
                      publish_date: str | None = None, link: str | None = None):
    ws = _get_spreadsheet().worksheet(SHEET_POSTS)
    rows = ws.get_all_values()
    for i, row in enumerate(rows[1:], start=2):
        if len(row) > 1 and row[0] == str(idea_id) and row[1] == str(variant_num):
            if status is not None:
                ws.update_cell(i, 6, status)
            if publish_date is not None:
                ws.update_cell(i, 7, publish_date)
            if link is not None:
                ws.update_cell(i, 8, link)
            break


# ── Pull: Sheets → бот (2 раза в сутки, см. config.SHEETS_SYNC_HOURS) ──
def sync_from_sheets():
    _sync_posts()
    _sync_new_ideas()


def _sync_posts():
    import publisher  # локальный импорт — избегаем циклической зависимости при старте модуля

    ws = _get_spreadsheet().worksheet(SHEET_POSTS)
    rows = ws.get_all_values()[1:]
    for row in rows:
        if len(row) < 8:
            continue
        idea_id_raw, variant_raw, _aud, _fmt, text, status, pub_date, _link = row[:8]
        if not idea_id_raw or not variant_raw:
            continue
        idea = db.get_idea(int(idea_id_raw))
        if not idea:
            continue
        gens = db.get_generations_for_idea(idea["id"])
        gen = next((g for g in gens if g["variant_num"] == int(variant_raw)), None)
        if not gen:
            continue

        # 1. Текст изменён вручную в Sheets → обновить SQLite
        new_hash = _hash(text)
        if text and new_hash != (gen.get("sheets_hash") or ""):
            db.update_generation_text(gen["id"], text)
            db.update_generation_hash(gen["id"], new_hash)

        # 2. Утверждён + дата заполнена + ещё не запланирован → поставить в расписание
        if status == _POST_STATUS_APPROVED and pub_date and idea["status"] != "scheduled":
            try:
                dt = datetime.strptime(pub_date.strip(), "%d.%m.%Y %H:%M")
            except ValueError:
                continue
            publisher.schedule_post(idea["id"], gen["id"], dt)


def _sync_new_ideas():
    ws = _get_spreadsheet().worksheet(SHEET_IDEAS)
    rows = ws.get_all_values()[1:]
    for row in rows:
        if len(row) < 4:
            continue
        idea_id_raw, _date, _source, text = row[:4]
        rubric = row[6] if len(row) > 6 and row[6] else "regular"
        if idea_id_raw or not text.strip():
            continue  # уже есть ID — идея известна боту; пустой текст — пустая строка
        db.add_idea(text.strip(), source="manual", rubric=rubric)
