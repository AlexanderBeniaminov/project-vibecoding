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
    # --- Выручка ---
    "Выручка итого",
    "Нал",
    "СБП",
    "Карта",
    "По счёту",
    # --- Трафик ---
    "Кол-во чеков",
    "Средний чек",
    "Гости",
    # --- Категории ---
    "Кухня",
    "Бар",
    # --- Временные срезы ---
    "Утро — выручка (09–11)",
    "Утро — гости",
    "День — выручка (11–17)",
    "День — гости",
    "Вечер — выручка (17–21)",
    "Вечер — гости",
    # --- Потери ---
    "Отмены (руб)",
    "Списания (руб)",
    # --- Касса (ручной ввод) ---
    "Инкассация",
    "Расход из кассы",
    "Остаток нал",
    # --- Персонал (ручной ввод) ---
    "Повара — кол-во",
    "Повара — з/п",
    "Официанты — кол-во",
    "Официанты — з/п",
    "Бармены — кол-во",
    "Бармены — з/п",
    "Посудомойщицы — кол-во",
    "Посудомойщицы — з/п",
    "Персонал итого",
    "З/п итого",
    # --- Прочее ---
    "Завтраки (гостей)",
    "Статус",
]

# Параметры листа «Еженедельно»
METRICS_WEEKLY = [
    "Неделя №",
    "Дата от",
    "Дата до",
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

    _write_metric_columns(service, spreadsheet_id)
    logger.info("Структура таблицы готова")


def _write_metric_columns(service, spreadsheet_id: str):
    """Записать названия параметров в колонку A каждого листа."""
    # A1 — заголовок колонки, A2:An — параметры
    daily_col   = [["Показатель"]] + [[m] for m in METRICS_DAILY]
    weekly_col  = [["Показатель"]] + [[m] for m in METRICS_WEEKLY]

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

def _find_or_create_date_column(service, spreadsheet_id: str, sheet_name: str, date_str: str) -> int:
    """
    Найти колонку с нужной датой в строке 1 или создать новую.
    Возвращает номер колонки (1-based, где 1=A, 2=B...).
    """
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!1:1"
    ).execute()
    row1 = result.get("values", [[]])[0]

    # Ищем существующую колонку с этой датой (начиная с B = индекс 1)
    for i, cell in enumerate(row1):
        if str(cell).strip() == date_str:
            return i + 1  # 1-based

    # Не нашли — добавляем новую колонку после последней заполненной
    next_col = max(len(row1), 1) + 1  # минимум колонка B (2)
    return next_col


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

def write_daily_row(service, spreadsheet_id: str, data: dict):
    """
    Записать данные за день в колонку с соответствующей датой.
    Строка 1 — дата, строки 2..N — значения параметров.
    """
    report_date = data.get("date", str(date.today()))

    summary  = data.get("orders_summary") or {}
    payments = data.get("payment_types") or {}
    cats     = data.get("category_revenue") or {}
    hourly   = data.get("hourly") or {}
    manual   = data.get("manual") or {}

    revenue  = summary.get("revenue", 0)
    orders   = summary.get("orders", 0)
    guests   = summary.get("guests", 0)
    avg_chk  = summary.get("avg_check", 0)

    kitchen = _find_category(cats, ["кухня", "kitchen", "еда", "food"])
    bar     = _find_category(cats, ["бар", "bar", "напитки", "drink"])

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

    has_manual = bool(manual)
    status = "✅ полный" if has_manual else "⚠️ авто (без кассы)"

    # Значения в том же порядке, что METRICS_DAILY
    values = [
        _v(revenue), _v(payments.get("Наличные", payments.get("Нал", 0))),
        _v(payments.get("СБП", payments.get("Безналичный", 0))),
        _v(payments.get("Банковская карта", payments.get("Карта", 0))),
        _v(payments.get("По счёту", payments.get("Безнал", 0))),
        _v(orders), _v(avg_chk), _v(guests),
        _v(kitchen), _v(bar),
        _v(утро.get("revenue", 0)),  _v(утро.get("guests", 0)),
        _v(день.get("revenue", 0)),  _v(день.get("guests", 0)),
        _v(вечер.get("revenue", 0)), _v(вечер.get("guests", 0)),
        _v(data.get("cancellations", 0)),
        _v(data.get("writeoffs", 0)),
        _v(manual.get("инкассация", "")),
        _v(manual.get("расход_кассы", "")),
        _v(manual.get("остаток_нал", "")),
        _v(повара.get("кол", "")),    _v(повара.get("зп", "")),
        _v(официанты.get("кол", "")), _v(официанты.get("зп", "")),
        _v(бармены.get("кол", "")),   _v(бармены.get("зп", "")),
        _v(посудомой.get("кол", "")), _v(посудомой.get("зп", "")),
        _v(staff_total or ""), _v(zp_total or ""),
        _v(manual.get("завтраки", "")),
        status,
    ]

    col_num = _find_or_create_date_column(service, spreadsheet_id, "Ежедневно", report_date)
    col_ltr = _col_letter(col_num)

    # Строка 1 — дата, строки 2..N — значения
    col_data = [[report_date]] + [[v] for v in values]

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Ежедневно!{col_ltr}1",
        valueInputOption="USER_ENTERED",
        body={"values": col_data}
    ).execute()

    logger.info(f"Данные за {report_date} записаны в колонку {col_ltr}")


# ---------------------------------------------------------------------------
# Запись еженедельных данных
# ---------------------------------------------------------------------------

def write_weekly_row(service, spreadsheet_id: str, data: dict):
    """
    Записать еженедельные данные в колонку с номером недели.
    Строка 1 — идентификатор недели, строки 2..N — значения.
    """
    week_label = f"Нед. {data.get('week_num')} ({data.get('date_from', '')[:10]})"

    values = [
        _v(data.get("week_num")),
        _v(data.get("date_from")),
        _v(data.get("date_to")),
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
        "", "", "",  # Гостей 1/2/3+ чел
        "", "", "", "", "", "",  # Градация чеков
        "", "", "",  # Топ-3 блюда
        "", "",      # Мероприятия
        _v(data.get("zp_total")),
    ]

    col_num = _find_or_create_date_column(service, spreadsheet_id, "Еженедельно", week_label)
    col_ltr = _col_letter(col_num)

    col_data = [[week_label]] + [[v] for v in values]

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Еженедельно!{col_ltr}1",
        valueInputOption="USER_ENTERED",
        body={"values": col_data}
    ).execute()

    logger.info(f"Еженедельные данные (неделя {data.get('week_num')}) записаны в колонку {col_ltr}")


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
