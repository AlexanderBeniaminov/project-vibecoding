"""Google Sheets — визуальный слой. Таблица — главный интерфейс управления расписанием.
Push — мгновенно при событиях бота. Pull — APScheduler раз в сутки (sheets.sync_from_sheets).

Структура листа «Посты»:
  A: Gen ID  |  B: Формат  |  C: Текст поста  |  D: Статус  |  E: Дата публикации  |  F: Ссылка
"""
import hashlib
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

import config
import db

_MSK = ZoneInfo("Europe/Moscow")

SHEET_IDEAS    = "📋 Идеи"
SHEET_POSTS    = "✏️ Посты"
SHEET_CALENDAR = "📅 Календарь"
SHEET_BLACKLIST = "🚫 Блэклист"

_HEADERS = {
    SHEET_IDEAS:    ["Дата", "Тема"],
    SHEET_POSTS:    ["Gen ID", "Дата", "Формат", "Текст поста", "Статус", "Дата публикации"],
    SHEET_CALENDAR: ["Дата", "День", "Время", "Тема", "Пост", "Статус", "Ссылка"],
    SHEET_BLACKLIST: ["Тема", "Режим", "Заблокировано до", "Причина", "Добавлено"],
}

# Статусы в Посты
_STATUS_DRAFT      = "✏️ Черновик"
_STATUS_ON_REVIEW  = "📬 На согласование"   # Алексей отправил на утверждение Александру
_STATUS_TO_PUBLISH = "К публикации"          # Александр утвердил — бот поставит в расписание
_STATUS_PUBLISHED  = "✔️ Опубликован"
_STATUS_DELETE     = "🗑 Удалить"

# Dropdown для колонки Статус (E)
_STATUS_OPTIONS = [_STATUS_DRAFT, _STATUS_ON_REVIEW, _STATUS_TO_PUBLISH, _STATUS_PUBLISHED, _STATUS_DELETE]

_IDEA_SOURCE_LABEL = {"text": "✍️ текст", "voice": "🎙 голос", "manual": "✍️ Sheets"}
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
    """Создаёт листы с заголовками, если их ещё не существуют. Вызывать при старте бота."""
    ss = _get_spreadsheet()
    existing = {ws.title for ws in ss.worksheets()}
    for name, headers in _HEADERS.items():
        if name not in existing:
            ws = ss.add_worksheet(title=name, rows=500, cols=len(headers))
            ws.append_row(headers)


def _hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


# ── Push: бот → Sheets (мгновенно при событиях) ──────────────
def push_idea(idea: dict):
    """Записывает идею в лист «Идеи» — только дата и тема."""
    ws = _get_spreadsheet().worksheet(SHEET_IDEAS)
    created = datetime.fromisoformat(idea["created_at"])
    ws.append_row([created.strftime("%d.%m"), idea["text"]])


def push_generation_draft(idea: dict, gen: dict):
    """Записывает вариант в «Посты» со статусом Черновик (нажата кнопка «Сохранить»)."""
    ws = _get_spreadsheet().worksheet(SHEET_POSTS)
    created = datetime.fromisoformat(gen["created_at"]) if gen.get("created_at") else datetime.now(_MSK)
    ws.append_row([
        gen["id"],                          # A: Gen ID
        created.strftime("%d.%m.%Y"),       # B: Дата
        gen["format"],                      # C: Формат
        gen["text"],                        # D: Текст поста
        _STATUS_DRAFT,                      # E: Статус
        "",                                 # F: Дата публикации — ставит пользователь
    ])
    db.update_generation_hash(gen["id"], _hash(gen["text"]))
    # Обновляем дропдауны после каждого добавления черновика
    try:
        _apply_sheet_validations()
    except Exception as e:
        logging.warning(f"[sheets] validations после push не удались: {e}")


def update_post_status_by_gen_id(gen_id: int, new_status: str) -> bool:
    """Находит строку по Gen ID в колонке A и обновляет статус (E). Возвращает True если нашёл."""
    ws = _get_spreadsheet().worksheet(SHEET_POSTS)
    cell = ws.find(str(gen_id), in_column=1)
    if cell:
        ws.update_cell(cell.row, 5, new_status)
        return True
    return False


def push_blacklist_entry(entry: dict):
    ws = _get_spreadsheet().worksheet(SHEET_BLACKLIST)
    added = datetime.fromisoformat(entry["created_at"])
    mode_label = "⏳ Временно" if entry["mode"] == "temporary" else "♾ Навсегда"
    until = entry["blocked_until"][:10] if entry["blocked_until"] else "—"
    ws.append_row([entry["text"], mode_label, until, entry.get("reason", ""), added.strftime("%d.%m.%Y")])


# ── Валидация (дропдауны) ─────────────────────────────────────
def _apply_sheet_validations():
    """Устанавливает дропдауны Статус и Дата публикации в листе «Посты».
    Вызывается при push нового черновика и при ежесуточном sync."""
    import publisher  # локальный импорт — избегаем циклической зависимости

    ss = _get_spreadsheet()
    ws = ss.worksheet(SHEET_POSTS)
    sheet_id = ws._properties["sheetId"]

    # Свободные слоты на 2 месяца вперёд
    slots = publisher.get_free_slots_2months()
    date_options = [
        f"{dt.strftime('%d.%m.%Y %H:%M')} ({_DAY_NAMES.get(dt.weekday(), '')})"
        for dt in slots
    ]

    requests = [
        # E (индекс 4) — дропдаун Статус
        {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1, "endRowIndex": 500,
                    "startColumnIndex": 4, "endColumnIndex": 5,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": v} for v in _STATUS_OPTIONS],
                    },
                    "showCustomUi": True,
                    "strict": True,
                },
            }
        },
    ]

    # F (индекс 5) — дропдаун Дата публикации (только если есть слоты)
    if date_options:
        requests.append({
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1, "endRowIndex": 500,
                    "startColumnIndex": 5, "endColumnIndex": 6,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": v} for v in date_options],
                    },
                    "showCustomUi": True,
                    "strict": False,  # пользователь может вписать произвольную дату
                },
            }
        })

    ss.batch_update({"requests": requests})


# ── История для ротации форматов ─────────────────────────────
def get_recent_history(limit: int = 15) -> list[dict]:
    """Читает лист «Календарь» для аналитики тем и форматов."""
    try:
        ws = _get_spreadsheet().worksheet(SHEET_CALENDAR)
        rows = ws.get_all_values()[1:]
        result = []
        for row in rows:
            if len(row) < 6:
                continue
            result.append({
                "date":   row[0],
                "topic":  row[3] if len(row) > 3 else "",
                "post":   row[4] if len(row) > 4 else "",
                "status": row[5] if len(row) > 5 else "",
                "format": row[6] if len(row) > 6 else "",
            })
        return result[-limit:]
    except Exception as e:
        logging.warning(f"[sheets] get_recent_history не удался: {e}")
        return []


# ── Пересборка «Календаря» (вызывается при 3:00-sync) ────────
def rebuild_calendar():
    """Полностью перезаписывает «Календарь» из SQLite generations."""
    conn = db.get_conn()
    rows = conn.execute(
        """SELECT g.id, g.text, g.format, g.status, g.scheduled_at, g.published_at,
                  g.channel_message_id, i.text as idea_text, i.rubric
           FROM generations g
           JOIN ideas i ON i.id = g.idea_id
           WHERE g.status IN ('to_publish', 'published')
           ORDER BY COALESCE(g.scheduled_at, g.published_at) ASC""",
    ).fetchall()
    conn.close()

    ss = _get_spreadsheet()
    ws = ss.worksheet(SHEET_CALENDAR)
    ws.clear()
    ws.append_row(_HEADERS[SHEET_CALENDAR])

    for row in rows:
        dt_str = row["scheduled_at"] or row["published_at"] or ""
        try:
            dt = datetime.fromisoformat(dt_str)
            date_label = dt.strftime("%d.%m.%Y")
            day_label  = _DAY_NAMES.get(dt.weekday(), "")
            time_label = dt.strftime("%H:%M")
        except Exception:
            date_label = dt_str[:10]
            day_label  = ""
            time_label = ""

        status_label = _STATUS_PUBLISHED if row["status"] == "published" else "📅 Запланирован"
        link = (
            f"https://t.me/c/{str(config.CHANNEL_ID).lstrip('-100')}/{row['channel_message_id']}"
            if row["channel_message_id"] else ""
        )
        ws.append_row([
            date_label, day_label, time_label,
            row["idea_text"], row["text"], status_label, link,
        ])


# ── Миграции (одноразово) ────────────────────────────────────
def migrate_ideas_sheet():
    """Очищает «Идеи» и перезаписывает из SQLite в формате Дата / Тема."""
    ss = _get_spreadsheet()
    ws = ss.worksheet(SHEET_IDEAS)
    ws.clear()
    ws.append_row(_HEADERS[SHEET_IDEAS])

    ideas = db.list_ideas(status="saved", limit=500)
    for idea in reversed(ideas):  # хронологический порядок
        created = datetime.fromisoformat(idea["created_at"])
        ws.append_row([created.strftime("%d.%m"), idea["text"]])

    logging.info(f"[migrate] Идеи: записано {len(ideas)} строк")


# ── Миграция листа «Посты» (одноразово) ──────────────────────
def migrate_posts_sheet():
    """Очищает «Посты» и перезаписывает из SQLite всеми draft/to_publish generations.
    Вызывать один раз при переходе на новую структуру колонок."""
    ss = _get_spreadsheet()
    ws = ss.worksheet(SHEET_POSTS)
    ws.clear()
    ws.append_row(_HEADERS[SHEET_POSTS])

    conn = db.get_conn()
    rows = conn.execute(
        """SELECT g.id, g.text, g.format, g.status, g.scheduled_at,
                  g.created_at, g.sheets_hash
           FROM generations g
           WHERE g.status IN ('generated', 'draft', 'to_publish', 'published')
           ORDER BY g.id""",
    ).fetchall()
    conn.close()

    for row in rows:
        if row["status"] in ("generated",):
            # generated — ещё не был показан в Sheets, пропускаем
            continue
        if row["status"] == "published":
            status_label = _STATUS_PUBLISHED
        elif row["status"] == "to_publish":
            status_label = _STATUS_TO_PUBLISH
        else:
            status_label = _STATUS_DRAFT

        try:
            created_label = datetime.fromisoformat(row["created_at"]).strftime("%d.%m.%Y")
        except Exception:
            created_label = ""

        pub_date = ""
        if row["scheduled_at"]:
            try:
                dt = datetime.fromisoformat(row["scheduled_at"])
                pub_date = f"{dt.strftime('%d.%m.%Y %H:%M')} ({_DAY_NAMES.get(dt.weekday(), '')})"
            except Exception:
                pass

        ws.append_row([
            row["id"],       # Gen ID
            created_label,   # Дата
            row["format"],
            row["text"],
            status_label,
            pub_date,
        ])

    try:
        _apply_sheet_validations()
    except Exception as e:
        logging.warning(f"[migrate] validations не удались: {e}")

    logging.info(f"[migrate] Посты: записано {len(rows)} строк")


# ── Pull: Sheets → бот (раз в сутки в 3:00 МСК) ─────────────
def sync_from_sheets():
    """Главный ежесуточный sync."""
    _sync_posts()
    _sync_new_ideas()
    _apply_sheet_validations()
    rebuild_calendar()


def _sync_posts():
    import publisher

    ss = _get_spreadsheet()
    ws = ss.worksheet(SHEET_POSTS)
    rows = ws.get_all_values()

    rows_to_delete = []

    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 4:
            continue
        gen_id_raw = row[0]
        # row[1] = Дата (пропускаем)
        # row[2] = Формат (пропускаем)
        text       = row[3] if len(row) > 3 else ""
        status     = row[4] if len(row) > 4 else ""
        pub_date   = row[5] if len(row) > 5 else ""

        if not gen_id_raw:
            continue
        try:
            gen_id = int(gen_id_raw)
        except ValueError:
            continue
        gen = db.get_generation(gen_id)
        if not gen:
            continue

        # Статус «🗑 Удалить» → удалить из БД + пометить строку
        if status.strip() == _STATUS_DELETE:
            db.delete_generation(gen_id)
            rows_to_delete.append(i)
            continue

        # Текст изменён вручную → обновить SQLite
        new_hash = _hash(text)
        if text and new_hash != (gen.get("sheets_hash") or ""):
            db.update_generation_text(gen_id, text)
            db.update_generation_hash(gen_id, new_hash)

        # Статус «К публикации» + дата → ставим в расписание
        if status.strip() == _STATUS_TO_PUBLISH and pub_date and gen["status"] not in ("to_publish", "published"):
            clean = pub_date.strip().split("(")[0].strip()
            dt = None
            for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
                try:
                    dt = datetime.strptime(clean, fmt)
                    break
                except ValueError:
                    continue
            if dt is None:
                logging.warning(f"[sheets] не удалось разобрать дату '{pub_date}' для gen_id={gen_id}")
                continue

            now = datetime.now(_MSK).replace(tzinfo=None)
            if dt <= now:
                import asyncio, concurrent.futures
                try:
                    loop = asyncio.get_event_loop()
                    loop.run_until_complete(publisher.publish_now(gen_id))
                except RuntimeError:
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, publisher.publish_now(gen_id))
                        future.result(timeout=30)
            else:
                publisher.schedule_generation(gen_id, dt)

    for row_idx in sorted(rows_to_delete, reverse=True):
        ws.delete_rows(row_idx)


def _sync_new_ideas():
    """Подхватывает идеи, добавленные вручную в лист «Идеи».
    Дедупликация по тексту — если тема уже есть в SQLite, пропускаем."""
    ws = _get_spreadsheet().worksheet(SHEET_IDEAS)
    rows = ws.get_all_values()[1:]
    existing_texts = {i["text"].strip().lower() for i in db.list_ideas(status="saved", limit=500)}
    for row in rows:
        if len(row) < 2:
            continue
        text = row[1].strip()  # колонка B: Тема
        if not text or text.lower() in existing_texts:
            continue
        db.add_idea(text, source="manual")
        existing_texts.add(text.lower())
