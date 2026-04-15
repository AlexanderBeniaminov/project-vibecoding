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
    "Повара — з/п",
    "Официанты — кол-во",
    "Официанты — з/п",
    "Бармены — кол-во",
    "Бармены — з/п",
    "Посудомойщицы — кол-во",
    "Посудомойщицы — з/п",
    "Персонал кол-во итого",
    "З/п итого",
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
    logger.info(f"Существующие листы: {existing}")

    requests = []
    for title in ["Ежедневно", "Еженедельно", "Дашборд"]:
        if title not in existing:
            requests.append({"addSheet": {"properties": {"title": title}}})

    if requests:
        sheets_api.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()
        logger.info(f"Созданы листы: {[r['addSheet']['properties']['title'] for r in requests]}")

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
    """Записать названия параметров в колонку A каждого листа."""
    # Ежедневно: A1 — «Дата», A2:An — параметры
    daily_col = [["Дата"]] + [[m] for m in METRICS_DAILY]

    # Еженедельно: A1 — «Неделя №», A2 — «Период (пн–вс)», A3:An — параметры
    weekly_col = [["Неделя №"], ["Период (пн–вс)"]] + [[m] for m in METRICS_WEEKLY]

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "RAW",
            "data": [
                {"range": "Ежедневно!A1",   "values": daily_col},
                {"range": "Еженедельно!A1", "values": weekly_col},
            ]
        }
    ).execute()
    logger.info("Колонка A с параметрами записана")


# ---------------------------------------------------------------------------
# Вспомогательные функции навигации
# ---------------------------------------------------------------------------

def _apply_number_format(service, spreadsheet_id: str):
    """
    Применить числовой формат с пробелом как разделителем тысяч
    ко всем ячейкам с данными (колонки B+) на обоих листах.
    """
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_ids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}

    fmt_number  = {"type": "NUMBER", "pattern": "# ##0"}
    fmt_decimal = {"type": "NUMBER", "pattern": "# ##0.00"}

    requests = []
    for sheet_name, data_start_row in [("Ежедневно", 1), ("Еженедельно", 2)]:
        sid = sheet_ids.get(sheet_name)
        if sid is None:
            continue
        # Все данные начиная с колонки B (index 1), строка data_start_row+1 (0-based)
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": data_start_row,
                    "startColumnIndex": 1,
                },
                "cell": {"userEnteredFormat": {"numberFormat": fmt_number}},
                "fields": "userEnteredFormat.numberFormat",
            }
        })

    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()
        logger.info("Числовой формат применён")


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
    Записать данные за день в колонку с соответствующей датой.
    Строка 1 — дата (RAW), строка 2 — день недели, строки 3..16 — авто-данные iiko,
    строки 17+ — ручной ввод администратора.
    """
    report_date = data.get("date", str(date.today()))

    # День недели на русском
    try:
        d = date.fromisoformat(report_date)
        weekday_ru = _WEEKDAYS_RU[d.weekday()]
    except (ValueError, IndexError):
        weekday_ru = ""

    summary  = data.get("orders_summary") or {}
    cats     = data.get("category_revenue") or {}
    hourly   = data.get("hourly") or {}
    manual   = data.get("manual") or {}

    revenue  = summary.get("revenue", 0)
    orders   = summary.get("orders", 0)
    guests   = summary.get("guests", 0)
    avg_chk  = summary.get("avg_check", 0)

    kitchen = cats.get("Кухня", 0)
    bar     = cats.get("Бар", 0)

    утро  = hourly.get("утро",  {})
    день  = hourly.get("день",  {})
    вечер = hourly.get("вечер", {})

    повара    = manual.get("повара",    {})
    официанты = manual.get("официанты", {})
    бармены   = manual.get("бармены",   {})
    посудомой = manual.get("посудомойщицы", {})
    zp_total  = sum([
        повара.get("зп", 0), официанты.get("зп", 0),
        бармены.get("зп", 0), посудомой.get("зп", 0),
    ])
    staff_total = sum([
        повара.get("кол", 0), официанты.get("кол", 0),
        бармены.get("кол", 0), посудомой.get("кол", 0),
    ])

    # Значения в том же порядке, что METRICS_DAILY (строки 2..N)
    values = [
        weekday_ru,                          # День недели
        _v(revenue),                         # Выручка итого
        _v(orders),                          # Кол-во чеков
        _v(avg_chk),                         # Средний чек
        _v(guests),                          # Гости
        _v(kitchen),                         # Кухня
        _v(bar),                             # Бар
        _v(утро.get("revenue", 0)),          # Утро — выручка (09–11)
        _v(утро.get("guests", 0)),           # Утро — гости (09-11)
        _v(день.get("revenue", 0)),          # День — выручка (11–17)
        _v(день.get("guests", 0)),           # День — гости (11-17)
        _v(вечер.get("revenue", 0)),         # Вечер — выручка (17–23)
        _v(вечер.get("guests", 0)),          # Вечер — гости (17-23)
        _v(data.get("cancellations", 0)),    # Отмены (руб)
        _v(data.get("writeoffs", 0)),        # Списания (руб)
        # --- Ручной ввод ---
        _v(manual.get("инкассация", "")),
        _v(manual.get("расход_кассы", "")),
        _v(manual.get("остаток_нал", "")),
        _v(повара.get("кол", "")),    _v(повара.get("зп", "")),
        _v(официанты.get("кол", "")), _v(официанты.get("зп", "")),
        _v(бармены.get("кол", "")),   _v(бармены.get("зп", "")),
        _v(посудомой.get("кол", "")), _v(посудомой.get("зп", "")),
        _v(staff_total or ""), _v(zp_total or ""),
        _v(manual.get("завтраки", "")),
    ]

    col_num = _find_or_create_date_column(service, spreadsheet_id, "Ежедневно", report_date, search_row=1)
    col_ltr = _col_letter(col_num)

    # Строка 1 — дата: записываем как RAW-строку, чтобы Sheets не превращал
    # «2026-03-30» в Excel serial number (который отображается как «пн/вт/...»).
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Ежедневно!{col_ltr}1",
        valueInputOption="RAW",
        body={"values": [[report_date]]},
    ).execute()

    # Строки 2..N — числа и текст: USER_ENTERED чтобы числа корректно
    # интерпретировались формулами Sheets.
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Ежедневно!{col_ltr}2",
        valueInputOption="USER_ENTERED",
        body={"values": [[v] for v in values]},
    ).execute()

    logger.info(f"Данные за {report_date} записаны в колонку {col_ltr}")


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

def _v(val):
    """Заменить None на пустую строку."""
    return val if val is not None else ""


def _find_category(cats: dict, keywords: list) -> float:
    """Найти сумму по категории iiko по ключевым словам (регистронезависимо)."""
    for key, val in cats.items():
        if any(kw in (key or "").lower() for kw in keywords):
            return val
    return 0.0
