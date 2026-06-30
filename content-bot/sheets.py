"""Google Sheets — визуальный слой. Таблица — главный интерфейс управления расписанием.
Push — мгновенно при событиях бота. Pull — APScheduler раз в сутки (sheets.sync_from_sheets).

Структура листа «Посты»:
  A: Gen ID  |  B: Формат  |  C: Текст поста  |  D: Статус  |  E: Дата публикации  |  F: Ссылка
"""
import hashlib
import html
import logging
from datetime import datetime
from html.parser import HTMLParser as _HTMLParser
from zoneinfo import ZoneInfo

import gspread
from google.auth.transport.requests import AuthorizedSession
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
_STATUS_URGENT     = "🚨 Срочно"             # публикация в канал немедленно, минуя расписание
_STATUS_PUBLISHED  = "✔️ Опубликован"
_STATUS_DELETE     = "🗑 Удалить"

# Dropdown для колонки Статус (E)
_STATUS_OPTIONS = [_STATUS_DRAFT, _STATUS_ON_REVIEW, _STATUS_TO_PUBLISH, _STATUS_URGENT, _STATUS_PUBLISHED, _STATUS_DELETE]

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


# ── Rich text: Sheets → Telegram HTML ────────────────────────

_sheets_session: AuthorizedSession | None = None


def _get_sheets_session() -> AuthorizedSession:
    global _sheets_session
    if _sheets_session is None:
        creds = Credentials.from_service_account_file(
            config.SERVICE_ACCOUNT_JSON,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        _sheets_session = AuthorizedSession(creds)
    return _sheets_session


def _textformat_runs_to_html(plain: str, runs: list) -> str:
    """Конвертирует textFormatRuns из Sheets API в Telegram HTML.
    plain — чистый текст ячейки, runs — список {startIndex, format}."""
    if not runs:
        return html.escape(plain)

    # Строим границы сегментов: startIndex каждого run + len(plain) в конце
    boundaries = [r.get("startIndex", 0) for r in runs] + [len(plain)]
    result = []
    for idx, run in enumerate(runs):
        start = boundaries[idx]
        end = boundaries[idx + 1]
        segment = html.escape(plain[start:end])
        if not segment:
            continue
        fmt = run.get("format", {})
        link_uri = (fmt.get("link") or {}).get("uri", "")
        # Применяем теги изнутри наружу: link → bold → italic → underline → strikethrough
        if link_uri:
            segment = f'<a href="{html.escape(link_uri, quote=True)}">{segment}</a>'
        if fmt.get("bold"):
            segment = f"<b>{segment}</b>"
        if fmt.get("italic"):
            segment = f"<i>{segment}</i>"
        if fmt.get("underline"):
            segment = f"<u>{segment}</u>"
        if fmt.get("strikethrough"):
            segment = f"<s>{segment}</s>"
        result.append(segment)
    return "".join(result)


def _apply_blockquotes(text: str) -> str:
    """Абзацы, где все строки начинаются с '> ', превращает в <blockquote expandable>."""
    paragraphs = text.split("\n\n")
    out = []
    for para in paragraphs:
        lines = para.split("\n")
        if lines and all(ln.startswith("> ") or ln == ">" for ln in lines):
            inner = "\n".join(ln[2:] if ln.startswith("> ") else "" for ln in lines)
            out.append(f"<blockquote expandable>{inner}</blockquote>")
        else:
            out.append(para)
    return "\n\n".join(out)


def _fetch_posts_rich_text() -> dict[int, str]:
    """Один API-запрос к Sheets v4 — возвращает {row_num: html} для колонки D листа «Посты».
    row_num соответствует номеру строки в таблице (начиная с 2, строка 1 — заголовок)."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{config.SPREADSHEET_ID}"
    sheet_name = SHEET_POSTS.replace("'", "\\'")
    params = {
        "includeGridData": "true",
        "ranges": f"'{sheet_name}'!D2:D500",
        "fields": "sheets.data.rowData.values(formattedValue,textFormatRuns)",
    }
    try:
        resp = _get_sheets_session().get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logging.warning(f"[sheets] rich text fetch failed: {e}")
        return {}

    result: dict[int, str] = {}
    rows_data = (
        data.get("sheets", [{}])[0]
        .get("data", [{}])[0]
        .get("rowData", [])
    )
    for i, row_data in enumerate(rows_data):
        sheet_row = i + 2  # строка 1 — заголовок
        values = row_data.get("values", [])
        if not values:
            continue
        cell = values[0]
        plain = cell.get("formattedValue", "")
        if not plain:
            continue
        runs = cell.get("textFormatRuns", [])
        html_text = _textformat_runs_to_html(plain, runs)
        html_text = _apply_blockquotes(html_text)
        result[sheet_row] = html_text
    return result


# ── Rich text: Telegram HTML → Sheets textFormatRuns ─────────

class _RunsBuilder(_HTMLParser):
    """Парсит Telegram HTML и строит textFormatRuns для Sheets API batchUpdate."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._pos: int = 0
        self._runs: list[dict] = []
        self._stack: list[dict] = [{}]
        self._last_fmt: dict = {}
        self._in_blockquote: bool = False

    def _current_fmt(self) -> dict:
        result: dict = {}
        for layer in self._stack:
            result.update(layer)
        return result

    def handle_starttag(self, tag: str, attrs: list):
        a = dict(attrs)
        if tag == "b":
            self._stack.append({"bold": True})
        elif tag == "i":
            self._stack.append({"italic": True})
        elif tag == "u":
            self._stack.append({"underline": True})
        elif tag == "s":
            self._stack.append({"strikethrough": True})
        elif tag == "a":
            self._stack.append({"link": {"uri": a.get("href", "")}})
        elif tag == "blockquote":
            self._in_blockquote = True
            self._stack.append({})
        else:
            self._stack.append({})

    def handle_endtag(self, tag: str):
        if tag == "blockquote":
            self._in_blockquote = False
        if len(self._stack) > 1:
            self._stack.pop()

    def handle_data(self, data: str):
        if not data:
            return
        if self._in_blockquote:
            lines = data.split("\n")
            data = "\n".join(f"> {ln}" if ln else ">" for ln in lines)
        fmt = self._current_fmt()
        if fmt != self._last_fmt:
            self._runs.append({"startIndex": self._pos, "format": fmt})
            self._last_fmt = fmt
        self._parts.append(data)
        self._pos += len(data)

    def result(self) -> tuple[str, list]:
        plain = "".join(self._parts)
        # Убираем начальный run с пустым форматом — он избыточен (это дефолт)
        runs = self._runs[:]
        if runs and runs[0]["startIndex"] == 0 and not any(v for v in runs[0]["format"].values() if v):
            runs = runs[1:]
        return plain, runs


def _html_to_textformat_runs(html_text: str) -> tuple[str, list]:
    """Конвертирует Telegram HTML в (plain_text, textFormatRuns) для Sheets API."""
    parser = _RunsBuilder()
    parser.feed(html_text)
    return parser.result()


def _write_cell_rich(sheet_gid: int, row: int, col: int, html_text: str):
    """Перезаписывает ячейку (row, col) с rich text форматированием через Sheets batchUpdate."""
    plain, runs = _html_to_textformat_runs(html_text)
    cell_data: dict = {"userEnteredValue": {"stringValue": plain}}
    if runs:
        cell_data["textFormatRuns"] = runs
    body = {
        "requests": [{
            "updateCells": {
                "rows": [{"values": [cell_data]}],
                "fields": "userEnteredValue,textFormatRuns",
                "range": {
                    "sheetId": sheet_gid,
                    "startRowIndex": row - 1,
                    "endRowIndex": row,
                    "startColumnIndex": col - 1,
                    "endColumnIndex": col,
                },
            }
        }]
    }
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{config.SPREADSHEET_ID}:batchUpdate"
    resp = _get_sheets_session().post(url, json=body, timeout=15)
    resp.raise_for_status()


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
    plain_text, runs = _html_to_textformat_runs(gen["text"])
    ws.append_row([
        gen["id"],                          # A: Gen ID
        created.strftime("%d.%m.%Y"),       # B: Дата
        gen["format"],                      # C: Формат
        plain_text,                         # D: Текст поста (plain — форматирование ниже)
        _STATUS_DRAFT,                      # E: Статус
        "",                                 # F: Дата публикации — ставит пользователь
    ])
    # Если текст содержит форматирование — применить через batchUpdate
    if runs:
        try:
            cell = ws.find(str(gen["id"]), in_column=1)
            if cell:
                _write_cell_rich(ws._properties["sheetId"], cell.row, col=4, html_text=gen["text"])
        except Exception as e:
            logging.warning(f"[sheets] rich text push для gen_id={gen['id']} не удался: {e}")
    db.update_generation_hash(gen["id"], _hash(gen["text"]))
    # Обновляем дропдауны после каждого добавления черновика
    try:
        _apply_sheet_validations()
    except Exception as e:
        logging.warning(f"[sheets] validations после push не удались: {e}")


def update_post_status_by_gen_id(gen_id: int, new_status: str) -> tuple[bool, int | None, int | None]:
    """Находит строку по Gen ID в колонке A и обновляет статус (E).
    Возвращает (найдено, номер_строки, gid_листа) — row/gid нужны для прямой ссылки на пост."""
    ws = _get_spreadsheet().worksheet(SHEET_POSTS)
    cell = ws.find(str(gen_id), in_column=1)
    if cell:
        ws.update_cell(cell.row, 5, new_status)
        return True, cell.row, ws.id
    return False, None, None


def build_post_link(row: int, gid: int) -> str:
    """Прямая ссылка на строку поста в Google Sheets (не на весь лист)."""
    base = config.SPREADSHEET_URL.rstrip("/")
    return f"{base}/edit#gid={gid}&range=A{row}"


def get_pending_actions() -> dict[str, list[dict]]:
    """Один проход по листу «✏️ Посты» — строки со статусом «На согласование», «🚨 Срочно»
    и «К публикации». Объединено в одну функцию, чтобы поллинг ходил в Sheets API один раз.
    «К публикации» включена сюда же (не только в суточный _sync_posts()) — иначе пост,
    поставленный в расписание после ночного sync, не попадёт в APScheduler до следующих суток
    и пропустит свою дату публикации.
    Перед тем как вернуть строку — синхронизирует ручную правку текста (колонка D) в SQLite,
    тот же приём, что в _sync_posts(), иначе публикация/уведомление уйдут со старым текстом из БД."""
    ws = _get_spreadsheet().worksheet(SHEET_POSTS)
    rows = ws.get_all_values()
    rich_texts = _fetch_posts_rich_text()
    gid = ws.id

    review, urgent, to_publish = [], [], []
    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 5:
            continue
        gen_id_raw = row[0]
        text = rich_texts.get(i) or (row[3] if len(row) > 3 else "")
        status = row[4].strip()
        pub_date = row[5].strip() if len(row) > 5 else ""
        if not gen_id_raw or status not in (_STATUS_ON_REVIEW, _STATUS_URGENT, _STATUS_TO_PUBLISH):
            continue
        try:
            gen_id = int(gen_id_raw)
        except ValueError:
            continue

        gen = db.get_generation(gen_id)
        if gen and text:
            new_hash = _hash(text)
            if new_hash != (gen.get("sheets_hash") or ""):
                db.update_generation_text(gen_id, text)
                db.update_generation_hash(gen_id, new_hash)

        item = {"gen_id": gen_id, "row": i, "gid": gid}
        if status == _STATUS_ON_REVIEW:
            review.append(item)
        elif status == _STATUS_URGENT:
            urgent.append(item)
        elif pub_date:
            item["pub_date"] = pub_date
            to_publish.append(item)
    return {"review": review, "urgent": urgent, "to_publish": to_publish}


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
        # D (индекс 3) — снять старую валидацию (Статус раньше был здесь, до сдвига схемы)
        {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1, "endRowIndex": 500,
                    "startColumnIndex": 3, "endColumnIndex": 4,
                },
            }
        },
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
    rich_texts = _fetch_posts_rich_text()

    rows_to_delete = []

    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 4:
            continue
        gen_id_raw = row[0]
        # row[1] = Дата (пропускаем)
        # row[2] = Формат (пропускаем)
        text       = rich_texts.get(i) or (row[3] if len(row) > 3 else "")
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
