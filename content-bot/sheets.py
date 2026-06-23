"""Google Sheets — визуальный слой. Таблица — главный интерфейс управления расписанием.
Push — мгновенно при событиях бота. Pull — APScheduler раз в сутки (sheets.sync_from_sheets)."""
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
    SHEET_IDEAS:    ["ID", "Дата", "Источник", "Тема", "Описание", "Статус", "Рубрика"],
    SHEET_POSTS:    ["ID идеи", "ID варианта", "Вариант №", "Формат", "Текст поста", "Статус", "Дата публикации", "Ссылка"],
    SHEET_CALENDAR: ["Дата", "День", "Время", "Тема", "Рубрика", "Статус", "Ссылка"],
    SHEET_BLACKLIST: ["Тема", "Режим", "Заблокировано до", "Причина", "Добавлено"],
}

# Статусы в Посты (то, что видит и меняет пользователь)
_STATUS_DRAFT      = "✏️ Черновик"
_STATUS_TO_PUBLISH = "К публикации"   # пользователь ставит вручную
_STATUS_PUBLISHED  = "✔️ Опубликован"
_STATUS_DELETE     = "🗑 Удалить"     # помечает на удаление

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
    """Записывает идею в лист «Идеи» — сырой текст без AI-обработки."""
    ws = _get_spreadsheet().worksheet(SHEET_IDEAS)
    created = datetime.fromisoformat(idea["created_at"])
    ws.append_row([
        idea["id"],
        created.strftime("%d.%m"),
        _IDEA_SOURCE_LABEL.get(idea["source"], idea["source"]),
        idea["text"],
        "",  # Описание — пустое, пользователь может заполнить вручную
        "💾 Сохранена",
        idea.get("rubric", "regular"),
    ])


def push_generation_draft(idea: dict, gen: dict):
    """Записывает один вариант в лист «Посты» со статусом Черновик (нажата кнопка «Сохранить»)."""
    ws = _get_spreadsheet().worksheet(SHEET_POSTS)
    ws.append_row([
        idea["id"],
        gen["id"],
        gen["variant_num"],
        gen["format"],
        gen["text"],
        _STATUS_DRAFT,
        "",  # Дата публикации — ставит пользователь
        "",  # Ссылка — появится после публикации
    ])
    db.update_generation_hash(gen["id"], _hash(gen["text"]))


def push_blacklist_entry(entry: dict):
    ws = _get_spreadsheet().worksheet(SHEET_BLACKLIST)
    added = datetime.fromisoformat(entry["created_at"])
    mode_label = "⏳ Временно" if entry["mode"] == "temporary" else "♾ Навсегда"
    until = entry["blocked_until"][:10] if entry["blocked_until"] else "—"
    ws.append_row([entry["text"], mode_label, until, entry.get("reason", ""), added.strftime("%d.%m.%Y")])


# ── История для ротации форматов ─────────────────────────────
def get_recent_history(limit: int = 15) -> list[dict]:
    """Читает лист «Календарь» для аналитики тем и форматов."""
    try:
        ws = _get_spreadsheet().worksheet(SHEET_CALENDAR)
        rows = ws.get_all_values()[1:]  # пропускаем заголовок
        result = []
        for row in rows:
            if len(row) < 6:
                continue
            result.append({
                "date":   row[0],
                "topic":  row[3] if len(row) > 3 else "",
                "rubric": row[4] if len(row) > 4 else "",
                "status": row[5] if len(row) > 5 else "",
                "format": row[6] if len(row) > 6 else "",
            })
        return result[-limit:]
    except Exception as e:
        logging.warning(f"[sheets] get_recent_history не удался: {e}")
        return []


# ── Пересборка «Календаря» (вызывается при 3:00-sync) ────────
def rebuild_calendar():
    """Полностью перезаписывает лист «Календарь» из текущих данных SQLite.
    Включает все generations со статусом 'to_publish' и 'published'."""
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

    # Очищаем всё и перезаписываем
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
            f"https://t.me/{config.CHANNEL_ID.lstrip('@')}/{row['channel_message_id']}"
            if row["channel_message_id"] else ""
        )
        ws.append_row([
            date_label, day_label, time_label,
            row["idea_text"], row["rubric"], status_label, link,
        ])


# ── Обновление дропдауна свободных дат в «Посты» ─────────────
def _update_free_slots_dropdown():
    """Устанавливает data validation в колонке «Дата публикации» для черновиков.
    Показывает список ближайших свободных слотов — чтобы нельзя было выбрать занятую дату."""
    import publisher  # локальный импорт — избегаем циклической зависимости
    try:
        slots = publisher.get_free_slots(8)
        date_options = [
            f"{dt.strftime('%d.%m.%Y %H:%M')} ({_DAY_NAMES.get(dt.weekday(), '')})"
            for dt in slots
        ]
        if not date_options:
            return

        ss = _get_spreadsheet()
        ws = ss.worksheet(SHEET_POSTS)
        sheet_id = ws._properties["sheetId"]

        # Колонка «Дата публикации» = индекс 6 (0-based, столбец G)
        ss.batch_update({"requests": [{
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 500,
                    "startColumnIndex": 6,
                    "endColumnIndex": 7,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": v} for v in date_options],
                    },
                    "showCustomUi": True,
                    "strict": False,  # пользователь может вписать произвольную дату тоже
                },
            }
        }]})
    except Exception as e:
        logging.warning(f"[sheets] _update_free_slots_dropdown не удался: {e}")


# ── Pull: Sheets → бот (раз в сутки в 3:00 МСК) ─────────────
def sync_from_sheets():
    """Главный ежесуточный sync:
    1. Подхватывает правки текстов черновиков
    2. Удаляет помеченные на удаление
    3. Ставит в расписание те, у кого стоит «К публикации» + дата
    4. Обновляет дропдаун свободных слотов
    5. Пересобирает «Календарь»
    """
    _sync_posts()
    _sync_new_ideas()
    _update_free_slots_dropdown()
    rebuild_calendar()


def _sync_posts():
    import publisher  # локальный импорт
    from datetime import datetime

    ss = _get_spreadsheet()
    ws = ss.worksheet(SHEET_POSTS)
    rows = ws.get_all_values()

    # Ищем строки на удаление отдельно, чтобы удалять снизу вверх (не сбить индексы)
    rows_to_delete = []

    for i, row in enumerate(rows[1:], start=2):  # start=2 потому что строки Sheets 1-based, первая — заголовок
        if len(row) < 6:
            continue
        idea_id_raw, gen_id_raw, _var_num, _fmt, text, status = row[:6]
        pub_date = row[6] if len(row) > 6 else ""
        link     = row[7] if len(row) > 7 else ""

        if not gen_id_raw:
            continue
        gen_id = int(gen_id_raw)
        gen = db.get_generation(gen_id)
        if not gen:
            continue

        # 1. Статус «🗑 Удалить» → удалить из БД, пометить строку на удаление
        if status.strip() == _STATUS_DELETE:
            db.delete_generation(gen_id)
            rows_to_delete.append(i)
            continue

        # 2. Текст изменён вручную → обновить SQLite
        new_hash = _hash(text)
        if text and new_hash != (gen.get("sheets_hash") or ""):
            db.update_generation_text(gen_id, text)
            db.update_generation_hash(gen_id, new_hash)

        # 3. Статус «К публикации» + дата → ставим в расписание
        if status.strip() == _STATUS_TO_PUBLISH and pub_date and gen["status"] not in ("to_publish", "published"):
            # Пробуем несколько форматов даты
            dt = None
            for fmt in ("%d.%m.%Y %H:%M (%a)", "%d.%m.%Y %H:%M (Пн)", "%d.%m.%Y %H:%M"):
                try:
                    # Срезаем скобочную часть если есть
                    clean = pub_date.strip().split("(")[0].strip()
                    dt = datetime.strptime(clean, "%d.%m.%Y %H:%M")
                    break
                except ValueError:
                    continue
            if dt is None:
                logging.warning(f"[sheets] не удалось разобрать дату '{pub_date}' для gen_id={gen_id}")
                continue

            now = datetime.now(_MSK).replace(tzinfo=None)
            if dt <= now:
                # Дата уже наступила — публикуем немедленно в этом же sync-прогоне
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    loop.run_until_complete(publisher.publish_now(gen_id))
                except RuntimeError:
                    # В asyncio-контексте (при вызове из async) используем другой подход
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, publisher.publish_now(gen_id))
                        future.result(timeout=30)
            else:
                publisher.schedule_generation(gen_id, dt)

    # Удаляем помеченные строки снизу вверх чтобы не сбить индексы
    for row_idx in sorted(rows_to_delete, reverse=True):
        ws.delete_rows(row_idx)


def _sync_new_ideas():
    """Подхватывает идеи, добавленные вручную в лист «Идеи» (без ID)."""
    ws = _get_spreadsheet().worksheet(SHEET_IDEAS)
    rows = ws.get_all_values()[1:]
    for row in rows:
        if len(row) < 4:
            continue
        idea_id_raw, _date, _source, text = row[:4]
        rubric = row[6] if len(row) > 6 and row[6] else "regular"
        if idea_id_raw or not text.strip():
            continue  # уже есть ID (известна боту) или пустая строка
        db.add_idea(text.strip(), source="manual", rubric=rubric)
