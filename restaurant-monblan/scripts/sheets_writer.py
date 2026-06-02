"""
sheets_writer.py — запись данных в Google Sheets.
Структура: колонка A — параметры, строка 1 — даты.
Каждый новый день добавляет новую колонку.
"""

import json
import logging
import os
from datetime import date

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ---------------------------------------------------------------------------
# Параметры листа «Ежедневно» (колонка A)
# ---------------------------------------------------------------------------

METRICS_DAILY = [
    # --- Строка 2: день недели (авто) ---
    "День недели",
    # --- Авто-данные из iiko (строки 3–16) ---
    "Выручка итого",
    "Кол-во чеков",
    "Средний чек",
    "Гости",
    "Кухня",
    "Бар",
    "Утро — выручка (09–11)",
    "Утро — гости (09-11)",
    "День — выручка (11–17)",
    "День — гости (11-17)",
    "Вечер — выручка (17–23)",
    "Вечер — гости (17-23)",
    "Отмены (руб)",
    "Списания (руб)",
    # --- Ручной ввод (строки 17+) ---
    "Инкассация",
    "Расход из кассы",
    "Остаток нал",
    "Повара — кол-во",
    "Официанты — кол-во",
    "Бармены — кол-во",
    "Посудомойщицы — кол-во",
    "Персонал кол-во итого",
    "Завтраки (кол-во гостей по жетонам)",
]

# Параметры листа «Еженедельно»
METRICS_WEEKLY = [
    "Выручка за неделю",
    "Ср. выручка/день",
    "Чеков за неделю",
    "Ср. чеков/день",
    "Гостей за неделю",
    "Ср. гостей/день",
    "Средний чек",
    "Ср. чек на гостя",
    "Кухня",
    "Бар",
    "Утро — выручка",
    "День — выручка",
    "Вечер — выручка",
    "Отмены (руб)",
    "Списания (руб)",
    "Оборачиваемость стола",
    "Оборачиваемость места",
    "Гостей 1 чел",
    "Гостей 2 чел",
    "Гостей 3+ чел",
    "Чеки 0–500",
    "Чеки 500–1000",
    "Чеки 1000–1500",
    "Чеки 1500–3000",
    "Чеки 3000–5000",
    "Чеки 5000+",
    "Топ-1 блюдо",
    "Топ-2 блюдо",
    "Топ-3 блюдо",
    "Мероприятия — кол-во",
    "Мероприятия — выручка",
    "З/п итого за неделю",
]

# Для обратной совместимости с main.py
HEADERS_DAILY = METRICS_DAILY
HEADERS_WEEKLY = METRICS_WEEKLY


# ---------------------------------------------------------------------------
# Подключение
# ---------------------------------------------------------------------------

def get_service(credentials_path: str = None, credentials_json: str = None):
    """
    Создать сервис Google Sheets API.
    credentials_path — путь к JSON-файлу сервисного аккаунта.
    credentials_json — JSON-строка (для GitHub Actions Secrets).
    """
    if credentials_json:
        info = json.loads(credentials_json)
    elif credentials_path:
        with open(credentials_path) as f:
            info = json.load(f)
    else:
        raise ValueError("Нужен credentials_path или credentials_json")

    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    logger.info("Google Sheets API подключён")
    return service


# ---------------------------------------------------------------------------
# Создание структуры таблицы
# ---------------------------------------------------------------------------

def setup_spreadsheet(service, spreadsheet_id: str):
    """
    Создать листы и записать параметры в колонку A.
    Безопасно вызывать повторно — не затирает данные.
    """
    sheets_api = service.spreadsheets()

    meta = sheets_api.get(spreadsheetId=spreadsheet_id).execute()
    existing = {s["properties"]["title"] for s in meta["sheets"]}
    existing_lower = {t.lower() for t in existing}
    logger.info(f"Существующие листы: {existing}")

    requests = []
    for title in ["Ежедневно", "Еженедельно", "Дашборд"]:
        if title.lower() not in existing_lower:
            requests.append({"addSheet": {"properties": {"title": title}}})

    if requests:
        try:
            sheets_api.batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests}
            ).execute()
            logger.info(f"Созданы листы: {[r['addSheet']['properties']['title'] for r in requests]}")
        except Exception as e:
            if "already exists" in str(e):
                logger.warning(f"Листы уже существуют (race condition): {e}")
            else:
                raise

    # Расширяем лист «Ежедневно» до 500 колонок (хватит на ~2 года данных)
    meta2 = sheets_api.get(spreadsheetId=spreadsheet_id).execute()
    expand_requests = []
    for sheet in meta2["sheets"]:
        props = sheet["properties"]
        if props["title"] == "Ежедневно":
            current_cols = props.get("gridProperties", {}).get("columnCount", 0)
            if current_cols < 500:
                expand_requests.append({
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": props["sheetId"],
                            "gridProperties": {"columnCount": 500}
                        },
                        "fields": "gridProperties.columnCount"
                    }
                })
    if expand_requests:
        sheets_api.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": expand_requests}
        ).execute()
        logger.info("Лист «Ежедневно» расширен до 500 колонок")

    _write_metric_columns(service, spreadsheet_id)
    _apply_number_format(service, spreadsheet_id)
    logger.info("Структура таблицы готова")


def _write_metric_columns(service, spreadsheet_id: str):
    """Записать названия параметров в колонку A листа «Ежедневно».
    Лист «Монблан»/«Еженедельно» (gid=2051236241) — НЕ ТРОГАТЬ:
    его 96-строчная структура управляется setup_weekly_structure.py + monblan_protect.gs.
    """
    daily_col = [["Дата"]] + [[m] for m in METRICS_DAILY]

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="Ежедневно!A1",
        valueInputOption="RAW",
        body={"values": daily_col},
    ).execute()
    logger.info("Колонка A листа «Ежедневно» записана")


# ---------------------------------------------------------------------------
# Вспомогательные функции навигации
# ---------------------------------------------------------------------------

def _apply_number_format(service, spreadsheet_id: str):
    """
    Применить числовой формат # ##0 к листу «Ежедневно» (колонки B+, строки 2+).
    Лист «Монблан»/«Еженедельно» (gid=2051236241) — НЕ ТРОГАТЬ:
    его форматы (# ##0 и 0% по строкам) управляются fix_formats_and_dates.py.
    """
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_ids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}

    sid = sheet_ids.get("Ежедневно")
    if sid is None:
        logger.warning("Лист «Ежедневно» не найден — формат не применён")
        return

    fmt_number = {"type": "NUMBER", "pattern": "# ##0"}
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{
            "repeatCell": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": 1,   # строка 2 (0-based)
                    "startColumnIndex": 1, # колонка B
                },
                "cell": {"userEnteredFormat": {"numberFormat": fmt_number}},
                "fields": "userEnteredFormat.numberFormat",
            }
        }]},
    ).execute()
    logger.info("Числовой формат # ##0 применён к листу «Ежедневно»")


def _excel_serial_to_date(serial: int) -> str:
    """
    Конвертировать Excel serial number в ISO дату (YYYY-MM-DD).
    Нужно когда дата записана через USER_ENTERED и Sheets преобразовал
    строку «2026-03-30» в число (серийный номер дня).
    Эпоха Excel: 30 декабря 1899 (с учётом ошибки Lotus 1-2-3).
    """
    from datetime import date as _date, timedelta
    base = _date(1899, 12, 30)
    return (base + timedelta(days=int(serial))).strftime("%Y-%m-%d")


def _find_or_create_date_column(service, spreadsheet_id: str, sheet_name: str, key: str, search_row: int = 1) -> int:
    """
    Найти колонку с нужным ключом в указанной строке или создать новую.
    Обрабатывает два варианта хранения дат:
      - строка «2026-03-30» (правильный, RAW)
      - Excel serial number (неправильный, появляется при USER_ENTERED)
    Возвращает номер колонки (1-based, где 1=A, 2=B...).
    """
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!{search_row}:{search_row}",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    row = result.get("values", [[]])[0] if result.get("values") else []

    for i, cell in enumerate(row):
        # Прямое совпадение строки
        if str(cell).strip() == key:
            return i + 1  # 1-based
        # Excel serial number → пробуем конвертировать в ISO и сравнить
        if isinstance(cell, (int, float)) and cell > 10000:
            try:
                if _excel_serial_to_date(int(cell)) == key:
                    return i + 1
            except Exception:
                pass

    # Не нашли — новая колонка после последней заполненной, минимум B (2)
    return max(len(row), 1) + 1


def _col_letter(n: int) -> str:
    """Номер колонки (1-based) → буква(ы): 1→A, 2→B, 27→AA."""
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


# ---------------------------------------------------------------------------
# Запись ежедневных данных
# ---------------------------------------------------------------------------

_WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def write_daily_row(service, spreadsheet_id: str, data: dict):
    """
    Записать ТОЛЬКО авто-данные iiko за день в колонку с соответствующей датой.
    Строка 1  — дата (RAW).
    Строки 2–16 — авто-данные из iiko (всегда перезаписываются).
    Строки 17+ — ручной ввод администратора (НЕ ТРОГАЮТСЯ — только если
                 явно переданы в data["manual"]).

    ВАЖНО: администратор может свободно заполнять строки 17+ в Sheets —
    они не будут перезаписаны ночным сбором данных.
    """
    report_date = data.get("date", str(date.today()))

    # День недели на русском
    try:
        d = date.fromisoformat(report_date)
        weekday_ru = _WEEKDAYS_RU[d.weekday()]
    except (ValueError, IndexError):
        weekday_ru = ""

    summary = data.get("orders_summary") or {}
    cats    = data.get("category_revenue") or {}
    hourly  = data.get("hourly") or {}

    revenue = summary.get("revenue", 0)
    orders  = summary.get("orders", 0)
    guests  = summary.get("guests", 0)
    avg_chk = summary.get("avg_check", 0)

    kitchen = cats.get("Кухня", 0)
    bar     = cats.get("Бар", 0)

    утро  = hourly.get("утро",  {})
    день  = hourly.get("день",  {})
    вечер = hourly.get("вечер", {})

    # Авто-данные — ТОЛЬКО строки 2–14.
    # Строки 15–27 (Отмены, Списания, Нал, Инкассация, персонал и т.д.) —
    # ручной ввод администратора. Скрипт их НЕ ТРОГАЕТ.
    auto_values = [
        weekday_ru,                          # стр.2  День недели
        _v(revenue),                         # стр.3  Выручка итого
        _v(orders),                          # стр.4  Кол-во чеков
        _v(avg_chk),                         # стр.5  Средний чек
        _v(guests),                          # стр.6  Гости
        _v(kitchen),                         # стр.7  Кухня
        _v(bar),                             # стр.8  Бар
        _v(утро.get("revenue", 0)),          # стр.9  Утро — выручка (09–11)
        _v(утро.get("guests", 0)),           # стр.10 Утро — гости (09-11)
        _v(день.get("revenue", 0)),          # стр.11 День — выручка (11–17)
        _v(день.get("guests", 0)),           # стр.12 День — гости (11-17)
        _v(вечер.get("revenue", 0)),         # стр.13 Вечер — выручка (17–23)
        _v(вечер.get("guests", 0)),          # стр.14 Вечер — гости (17-23)
        # ← строка 15 и далее — только ручной ввод, скрипт останавливается здесь
    ]

    col_num = _find_or_create_date_column(service, spreadsheet_id, "Ежедневно", report_date, search_row=1)
    col_ltr = _col_letter(col_num)

    # Строка 1 — дата RAW (не превращать в Excel serial number)
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Ежедневно!{col_ltr}1",
        valueInputOption="RAW",
        body={"values": [[report_date]]},
    ).execute()

    # Строки 2–14 — авто-данные. Строки 15–27 скрипт не трогает.
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Ежедневно!{col_ltr}2",
        valueInputOption="USER_ENTERED",
        body={"values": [[v] for v in auto_values]},
    ).execute()

    logger.info(f"Авто-данные за {report_date} записаны в колонку {col_ltr} (строки 1–14)")


# ---------------------------------------------------------------------------
# Запись еженедельных данных
# ---------------------------------------------------------------------------

def write_weekly_row(service, spreadsheet_id: str, data: dict):
    """
    Записать еженедельные данные.
    Строка 1 — номер недели («Неделя 13»).
    Строка 2 — период («23.03.2026 – 29.03.2026»).
    Строки 3..N — значения параметров (порядок = METRICS_WEEKLY).
    """
    from datetime import date as _date

    week_num = data.get("week_num", "?")
    week_title = f"Неделя {week_num}"

    # Форматируем период пн–вс
    try:
        d_from = _date.fromisoformat(data.get("date_from", ""))
        d_to   = _date.fromisoformat(data.get("date_to", ""))
        period = f"{d_from.strftime('%d.%m.%Y')} – {d_to.strftime('%d.%m.%Y')}"
    except ValueError:
        period = f"{data.get('date_from', '')} – {data.get('date_to', '')}"

    values = [
        _v(data.get("revenue")),
        _v(data.get("avg_revenue_day")),
        _v(data.get("orders")),
        _v(data.get("avg_orders_day")),
        _v(data.get("guests")),
        _v(data.get("avg_guests_day")),
        _v(data.get("avg_check")),
        _v(data.get("avg_check_guest")),
        _v(data.get("kitchen")),
        _v(data.get("bar")),
        _v(data.get("rev_morning")),
        _v(data.get("rev_day")),
        _v(data.get("rev_evening")),
        _v(data.get("cancellations")),
        _v(data.get("writeoffs")),
        _v(data.get("turnover_table")),
        _v(data.get("turnover_seat")),
        "", "", "",        # Гостей 1/2/3+ чел
        "", "", "", "", "", "",  # Градация чеков
        "", "", "",        # Топ-3 блюда
        "", "",            # Мероприятия
        _v(data.get("zp_total")),
    ]

    # Ищем колонку по номеру недели в строке 1
    col_num = _find_or_create_date_column(service, spreadsheet_id, "Еженедельно", week_title, search_row=1)
    col_ltr = _col_letter(col_num)

    # Строка 1: номер недели, строка 2: период, строки 3+: значения
    col_data = [[week_title], [period]] + [[v] for v in values]

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Еженедельно!{col_ltr}1",
        valueInputOption="USER_ENTERED",
        body={"values": col_data}
    ).execute()

    logger.info(f"Еженедельные данные (неделя {week_num}, {period}) записаны в колонку {col_ltr}")


# ---------------------------------------------------------------------------
# Чтение ежедневных данных
# ---------------------------------------------------------------------------

def read_daily_row(service, spreadsheet_id: str, report_date: str) -> dict:
    """
    Прочитать все метрики за указанную дату из листа «Ежедневно».
    Возвращает словарь {название метрики: значение}.
    Если дата не найдена — возвращает пустой словарь.
    """
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="Ежедневно!A:AZ"
    ).execute()
    rows = result.get("values", [])

    if not rows or len(rows) < 2:
        logger.warning(f"Лист «Ежедневно» пуст или только заголовок")
        return {}

    header_row = rows[0]  # строка 1: «Показатель», дата1, дата2, ...

    # Ищем колонку с нужной датой
    col_idx = None
    for i, cell in enumerate(header_row):
        if str(cell).strip() == str(report_date):
            col_idx = i
            break

    if col_idx is None:
        logger.warning(f"Дата {report_date} не найдена в листе «Ежедневно»")
        return {}

    # Читаем значения: строка → {метрика: значение}
    data = {}
    for row in rows[1:]:
        if not row:
            continue
        metric_name = str(row[0]).strip() if row else ""
        value = row[col_idx] if col_idx < len(row) else ""
        if metric_name:
            data[metric_name] = value

    logger.info(f"Прочитано {len(data)} метрик за {report_date}")
    return data


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def delete_columns_before_date(service, spreadsheet_id: str, cutoff_date) -> int:
    """
    Удалить из листа «Ежедневно» все столбцы, где дата в строке 1
    строго раньше cutoff_date (тип datetime.date или строка YYYY-MM-DD).
    Возвращает количество удалённых столбцов.
    """
    from datetime import date as _date
    if isinstance(cutoff_date, str):
        cutoff_date = _date.fromisoformat(cutoff_date)

    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_id = None
    for s in meta["sheets"]:
        if s["properties"]["title"] == "Ежедневно":
            sheet_id = s["properties"]["sheetId"]
            break
    if sheet_id is None:
        logger.warning("Лист «Ежедневно» не найден — удаление не выполнено")
        return 0

    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="Ежедневно!1:1",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    header = result.get("values", [[]])[0] if result.get("values") else []

    # Собираем индексы (0-based) колонок, которые нужно удалить (дата < cutoff)
    cols_to_delete = []
    for i, cell in enumerate(header):
        if i == 0:
            continue  # колонка A — метки
        cell_str = str(cell).strip()
        # Обработка Excel serial number
        if isinstance(cell, (int, float)) and cell > 10000:
            try:
                cell_str = _excel_serial_to_date(int(cell))
            except Exception:
                continue
        try:
            d = _date.fromisoformat(cell_str)
            if d < cutoff_date:
                cols_to_delete.append(i)
        except ValueError:
            pass

    if not cols_to_delete:
        logger.info(f"Нет столбцов до {cutoff_date} — ничего не удаляем")
        return 0

    # Удаляем от большего индекса к меньшему, чтобы не сдвигать предыдущие
    cols_to_delete.sort(reverse=True)
    requests = [
        {
            "deleteDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": col_idx,
                    "endIndex": col_idx + 1,
                }
            }
        }
        for col_idx in cols_to_delete
    ]
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()
    logger.info(f"Удалено {len(cols_to_delete)} столбцов до {cutoff_date}: индексы {cols_to_delete}")
    return len(cols_to_delete)


def _v(val):
    """Заменить None на пустую строку."""
    return val if val is not None else ""


def _find_category(cats: dict, keywords: list) -> float:
    """Найти сумму по категории iiko по ключевым словам (регистронезависимо)."""
    for key, val in cats.items():
        if any(kw in (key or "").lower() for kw in keywords):
            return val
    return 0.0


# ---------------------------------------------------------------------------
# Запись ежемесячных данных (лист «ЕжеМесячный»)
# ---------------------------------------------------------------------------

# Карта: ключ словаря данных → номер строки листа (1-based)
_MONTHLY_ROW_MAP = {
    # строка 2 — дата (обрабатывается отдельно)
    "revenue_total":              3,
    "revenue_kitchen":            4,
    "revenue_kitchen_pct":        5,
    "revenue_bar":                6,
    "revenue_bar_pct":            7,
    # строка 8 — заголовок секции
    "revenue_morning":            9,
    "revenue_morning_pct":       10,
    "revenue_day":               11,
    "revenue_day_pct":           12,
    "revenue_evening":           13,
    "revenue_evening_pct":       14,
    # строка 15 — заголовок секции
    "weekday_mon":               16,
    "weekday_mon_pct":           17,
    "weekday_tue":               18,
    "weekday_tue_pct":           19,
    "weekday_wed":               20,
    "weekday_wed_pct":           21,
    "weekday_thu":               22,
    "weekday_thu_pct":           23,
    "weekday_fri":               24,
    "weekday_fri_pct":           25,
    "weekday_sat":               26,
    "weekday_sat_pct":           27,
    "weekday_sun":               28,
    "weekday_sun_pct":           29,
    "margin_total":              30,
    "margin_pct":                31,
    "margin_kitchen":            32,
    "margin_kitchen_pct":        33,
    "margin_bar":                34,
    "margin_bar_pct":            35,
    "markup_total":              36,
    "markup_kitchen":            37,
    "markup_bar":                38,
    "foodcost_total":            39,
    "foodcost_kitchen":          40,
    "foodcost_bar":              41,
    "guests_total":              42,
    "guests_morning":            43,
    "guests_morning_pct":        44,
    "guests_day":                45,
    "guests_day_pct":            46,
    "guests_evening":            47,
    "guests_evening_pct":        48,
    "avg_check_per_guest":       49,
    "avg_check_per_guest_morning": 50,
    "avg_check_per_guest_day":   51,
    "avg_check_per_guest_evening": 52,
    "checks_total":              53,
    "checks_morning":            54,
    "checks_day":                55,
    "checks_evening":            56,
    "dishes_kitchen":            57,
    "avg_check":                 58,
    "avg_check_per_dish":        59,
    "avg_per_guest_kitchen":     60,
    "avg_per_guest_bar":         61,
    "avg_dishes_per_guest":      62,
    "turnover_table":            63,
    "turnover_table_morning":    64,
    "turnover_table_day":        65,
    "turnover_table_evening":    66,
    "turnover_seat":             67,
    "turnover_seat_morning":     68,
    "turnover_seat_day":         69,
    "turnover_seat_evening":     70,
    # строка 71 — заголовок секции
    "revenue_1guest":            72,
    "revenue_1guest_pct":        73,
    "revenue_2guests":           74,
    "revenue_2guests_pct":       75,
    "revenue_3plus":             76,
    "revenue_3plus_pct":         77,
    "group_loyalty":             78,
    "checks_1guest":             79,
    "checks_1guest_pct":         80,
    "checks_2guests":            81,
    "checks_2guests_pct":        82,
    "checks_3plus":              83,
    "checks_3plus_pct":          84,
    # строка 85 — заголовок секции
    "bracket_0_500":             86,
    "bracket_0_500_pct":         87,
    "bracket_500_1000":          88,
    "bracket_500_1000_pct":      89,
    "bracket_1000_1500":         90,
    "bracket_1000_1500_pct":     91,
    "bracket_1500_3000":         92,
    "bracket_1500_3000_pct":     93,
    "bracket_3000_5000":         94,
    "bracket_3000_5000_pct":     95,
    "bracket_5000_plus":         96,
    "bracket_5000_plus_pct":     97,
    "tables":                    98,
    "seats":                     99,
    "days_in_month":            100,
}

MONTHLY_SHEET = "ЕжеМесячный"

# Строки с денежным форматом (# ##0 — пробел как разделитель тысяч)
_MONTHLY_MONEY_ROWS = {
    3, 4, 6, 9, 11, 13,
    16, 18, 20, 22, 24, 26, 28,
    30, 32, 34,
    42, 43, 45, 47,
    49, 50, 51, 52,
    53, 54, 55, 56,
    57, 58, 59, 60, 61,
    72, 74, 76,
    79, 81, 83,
    86, 88, 90, 92, 94, 96,
    98, 99, 100,
}
# Строки с процентным форматом (0%)
_MONTHLY_PCT_ROWS = {
    5, 7, 10, 12, 14,
    17, 19, 21, 23, 25, 27, 29,
    31, 33, 35,
    36, 37, 38,  # наценка (markup) — процентный формат
    39, 40, 41,
    44, 46, 48,
    73, 75, 77,
    80, 82, 84,
    87, 89, 91, 93, 95, 97,
}
# Строки с дробным форматом (0.00 — оборачиваемость, коэф. лояльности)
_MONTHLY_DECIMAL_ROWS = {
    62, 63, 64, 65, 66, 67, 68, 69, 70,
    78,
}


def setup_monthly_formats(service, spreadsheet_id: str):
    """
    Применить числовые форматы к листу «ЕжеМесячный» по строкам:
    — деньги (# ##0): суммы в рублях
    — проценты (0%):  доли и процентные строки
    — дробные (0.00): коэффициенты, оборачиваемость, наценки
    Применяется к столбцам B и далее (не затрагивает колонку A с метками).
    """
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_id = None
    for s in meta["sheets"]:
        if s["properties"]["title"] == MONTHLY_SHEET:
            sheet_id = s["properties"]["sheetId"]
            break
    if sheet_id is None:
        logger.warning(f"Лист «{MONTHLY_SHEET}» не найден — форматы не применены")
        return

    # #,##0 — Google Sheets сам заменяет запятую на пробел по российской локали.
    # Это единственный способ получить рекурсивный разделитель тысяч (1 234 567, не 1234 567).
    fmt_money   = {"type": "NUMBER",     "pattern": "#,##0"}
    fmt_pct     = {"type": "PERCENT",    "pattern": "0%"}
    fmt_decimal = {"type": "NUMBER",     "pattern": "0.0"}   # один знак: оборачиваемость

    requests = []

    def _row_request(row_num: int, fmt: dict):
        return {
            "repeatCell": {
                "range": {
                    "sheetId":          sheet_id,
                    "startRowIndex":    row_num - 1,  # 0-based
                    "endRowIndex":      row_num,
                    "startColumnIndex": 1,            # с колонки B (A — метки)
                },
                "cell": {
                    "userEnteredFormat": {"numberFormat": fmt}
                },
                "fields": "userEnteredFormat.numberFormat",
            }
        }

    for row in _MONTHLY_MONEY_ROWS:
        requests.append(_row_request(row, fmt_money))
    for row in _MONTHLY_PCT_ROWS:
        requests.append(_row_request(row, fmt_pct))
    for row in _MONTHLY_DECIMAL_ROWS:
        requests.append(_row_request(row, fmt_decimal))

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()
    logger.info(
        f"Форматы листа «{MONTHLY_SHEET}» применены: "
        f"{len(_MONTHLY_MONEY_ROWS)} денежных, {len(_MONTHLY_PCT_ROWS)} %, "
        f"{len(_MONTHLY_DECIMAL_ROWS)} дробных строк"
    )


def setup_monthly_visual_format(service, spreadsheet_id: str):
    """
    Применить визуальное цветовое оформление листа «ЕжеМесячный»:
    жёлто-оранжевая гамма для визуального отличия от синей гаммы листа «Монблан».

    Аналог buildColumnA_() из monblan_build.gs, но через Sheets API v4.
    Закрепляет строки 1–2 и столбец A. Ширина столбца A — 260px, данных — 90px.
    """
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_id = None
    for s in meta["sheets"]:
        if s["properties"]["title"] == MONTHLY_SHEET:
            sheet_id = s["properties"]["sheetId"]
            break
    if sheet_id is None:
        logger.warning(f"Лист «{MONTHLY_SHEET}» не найден — цветовое оформление не применено")
        return

    def _rgb(h):
        h = h.lstrip("#")
        return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255, "blue": int(h[4:6], 16) / 255}

    # Жёлто-оранжевая палитра (аналог синей гаммы листа «Монблан»)
    HDR_BG    = _rgb("#7c3e0d")  # тёмно-коричневый ← #1a3a5c тёмно-синий
    HDR_TEXT  = _rgb("#ffffff")
    DATE_BG   = _rgb("#fde8c8")  # светло-персиковый ← #d0e4f7 светло-голубой
    DATE_TEXT = _rgb("#1a1a1a")
    SEC_BG    = _rgb("#92400e")  # тёмно-янтарный ← #3d3d3d тёмно-серый
    SEC_TEXT  = _rgb("#ffffff")
    PCT_BG    = _rgb("#fef3e2")  # очень светло-янтарный ← #eef3fa светло-голубой
    PCT_TEXT  = _rgb("#92400e")
    CALC_BG   = _rgb("#fff8dc")  # светло-кремовый ← #f0f4f0 светло-зелёный
    CALC_TEXT = _rgb("#78350f")
    DATA_BG   = _rgb("#ffffff")
    DATA_ALT  = _rgb("#fffbf5")  # очень светло-жёлтый ← #f8f9fa
    DATA_TEXT = _rgb("#1a1a1a")
    STAT_BG   = _rgb("#faf8f0")  # тёплый белый ← #f5f5f0
    STAT_TEXT = _rgb("#555555")
    COL_A_BG  = _rgb("#fef9f0")  # кремовый ← #f0f0f0

    # Строки-заголовки блоков — тёмно-янтарный фон.
    # Включает как чистые разделители (без данных), так и ключевые метрики каждого блока.
    _SECTION_ROWS    = {8, 15, 30, 36, 39, 42, 49, 53, 57, 63, 67, 71, 78, 85}
    # Расчётные строки — светло-кремовый фон (средние, коэффициенты, оборачиваемость).
    # Не включает строки из _SECTION_ROWS.
    _CALC_COLOR_ROWS = _MONTHLY_DECIMAL_ROWS | {32, 34, 50, 51, 52, 58, 59, 60, 61, 62, 64, 65, 66, 68, 69, 70}
    _STATIC_ROWS     = {98, 99, 100}

    def _req(r_from, r_to, bg, text=None, bold=None, c_from=0, c_to=None):
        fmt = {"backgroundColor": bg}
        tf = {}
        if text is not None:
            tf["foregroundColor"] = text
        if bold is not None:
            tf["bold"] = bold
        if tf:
            fmt["textFormat"] = tf
        rng = {
            "sheetId": sheet_id,
            "startRowIndex": r_from - 1,
            "endRowIndex": r_to,          # r_to — 0-based exclusive (= 1-based r_to)
            "startColumnIndex": c_from,
        }
        if c_to is not None:
            rng["endColumnIndex"] = c_to
        fields = "userEnteredFormat.backgroundColor"
        if tf:
            fields += ",userEnteredFormat.textFormat"
        return {"repeatCell": {"range": rng, "cell": {"userEnteredFormat": fmt}, "fields": fields}}

    reqs = []

    # 1. Столбец A (строки 1-100): кремовый фон, не жирный
    reqs.append(_req(1, 100, COL_A_BG, text=DATA_TEXT, bold=False, c_from=0, c_to=1))

    # 2. Строка 1 (шапка) — полная строка: тёмно-коричневый, белый жирный
    reqs.append(_req(1, 1, HDR_BG, HDR_TEXT, bold=True, c_from=0))

    # 3. Строка 2 (даты месяцев) — полная строка: светло-персиковый, жирный
    reqs.append(_req(2, 2, DATE_BG, DATE_TEXT, bold=True, c_from=0))

    # 4. Строки 3–100 (колонки B+) — по типу строки
    for row in range(3, 101):
        if row in _SECTION_ROWS:
            continue  # раздел — обрабатывается ниже
        elif row in _MONTHLY_PCT_ROWS:
            reqs.append(_req(row, row, PCT_BG, PCT_TEXT, bold=False, c_from=1))
        elif row in _CALC_COLOR_ROWS:
            reqs.append(_req(row, row, CALC_BG, CALC_TEXT, bold=False, c_from=1))
        elif row in _STATIC_ROWS:
            reqs.append(_req(row, row, STAT_BG, STAT_TEXT, bold=False, c_from=1))
        else:
            bg = DATA_ALT if row % 2 == 0 else DATA_BG
            reqs.append(_req(row, row, bg, DATA_TEXT, bold=False, c_from=1))

    # 5. Строки-заголовки разделов — полная строка: тёмно-янтарный, белый жирный
    for row in sorted(_SECTION_ROWS):
        reqs.append(_req(row, row, SEC_BG, SEC_TEXT, bold=True, c_from=0))

    # 6. Шрифт 11px для всех строк 1-100 (специфичный field-path, не сбрасывает bold/color)
    reqs.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 100},
            "cell": {"userEnteredFormat": {"textFormat": {"fontSize": 11}}},
            "fields": "userEnteredFormat.textFormat.fontSize",
        }
    })
    # 6б. Строка 3 (Выручка итого) — жирная (специфичный path, не трогает size/color)
    reqs.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 2, "endRowIndex": 3},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold",
        }
    })

    # 7. Ширина столбца A — 260px, данных — 90px
    reqs.append({
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 260},
            "fields": "pixelSize",
        }
    })
    reqs.append({
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 50},
            "properties": {"pixelSize": 90},
            "fields": "pixelSize",
        }
    })

    # 8. Закрепить строки 1–2 и столбец A
    reqs.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 2, "frozenColumnCount": 1},
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }
    })

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": reqs},
    ).execute()
    logger.info(
        f"Визуальное оформление листа «{MONTHLY_SHEET}» применено: "
        f"жёлто-оранжевая гамма, {len(reqs)} запросов, заморозка строк 1-2 + столбца A"
    )


def write_monthly_col(service, spreadsheet_id: str, data: dict):
    """
    Записать данные за месяц в лист «ЕжеМесячный».
    data["date"] — строка "YYYY-MM-01".
    Строка 2 листа — даты; находим колонку по дате или создаём новую.
    Пишем строки 2–100 одним запросом.
    """
    month_date = data.get("date", "")   # "YYYY-MM-01"
    if not month_date:
        logger.error("write_monthly_col: нет поля 'date' в данных")
        return

    col_num = _find_or_create_date_column(
        service, spreadsheet_id, MONTHLY_SHEET, month_date, search_row=2
    )
    col_ltr = _col_letter(col_num)

    # Строим колонку значений строк 2–100 (индексы 0–98)
    col_values: list = [""] * 100   # 100 позиций → строки 1–100

    # Строка 2 (индекс 1): дата
    col_values[1] = month_date

    # Заполняем по карте
    for key, row_num in _MONTHLY_ROW_MAP.items():
        val = data.get(key, "")
        col_values[row_num - 1] = _v(val)

    # Пишем строки 2–100 (99 строк, начиная со строки 2)
    body_values = [[v] for v in col_values[1:100]]   # индексы 1–99 → строки 2–100

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{MONTHLY_SHEET}!{col_ltr}2",
        valueInputOption="RAW",
        body={"values": body_values},
    ).execute()

    logger.info(
        f"Ежемесячные данные за {month_date} записаны в колонку {col_ltr} "
        f"листа «{MONTHLY_SHEET}» (строки 2–100)"
    )
