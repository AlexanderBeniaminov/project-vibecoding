"""
sheets_writer.py — запись данных в Google Sheets.
Создаёт структуру листов и записывает ежедневные данные.
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
# Заголовки листов
# ---------------------------------------------------------------------------

# Лист 1 — Ежедневно
HEADERS_DAILY = [
    "Дата",
    # Автоматически из iiko
    "Выручка итого", "Нал", "СБП", "Карта", "По счёту",
    "Кол-во чеков", "Средний чек", "Гости",
    "Кухня", "Бар",
    "Утро (выручка)", "Утро (гости)", "День (выручка)", "День (гости)", "Вечер (выручка)", "Вечер (гости)",
    "Отмены (руб)", "Списания (руб)",
    # Ручной ввод через Telegram
    "Инкассация", "Расход из кассы", "Остаток нал",
    "Повара (кол)", "Повара (з/п)",
    "Официанты (кол)", "Официанты (з/п)",
    "Бармены (кол)", "Бармены (з/п)",
    "Посудомойщицы (кол)", "Посудомойщицы (з/п)",
    "Персонал итого", "З/п итого",
    "Завтраки (гостей)",
    "Статус",
]

# Лист 2 — Еженедельно
HEADERS_WEEKLY = [
    "Неделя", "Дата от", "Дата до",
    "Выручка за неделю", "Ср. выручка/день",
    "Чеков за неделю", "Ср. чеков/день",
    "Гостей за неделю", "Ср. гостей/день",
    "Средний чек", "Ср. чек на гостя",
    "Кухня (неделя)", "Бар (неделя)",
    "Утро (выручка)", "День (выручка)", "Вечер (выручка)",
    "Отмены (руб)", "Списания (руб)",
    "Оборачиваемость стола", "Оборачиваемость места",
    "Гостей 1 чел", "Гостей 2 чел", "Гостей 3+ чел",
    "Чеки 0–500", "Чеки 500–1000", "Чеки 1000–1500",
    "Чеки 1500–3000", "Чеки 3000–5000", "Чеки 5000+",
    "Топ-1 блюдо", "Топ-2 блюдо", "Топ-3 блюдо",
    "Мероприятия (кол)", "Мероприятия (выручка)",
    "З/п итого за неделю",
]


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
    Создать листы и заголовки если их ещё нет.
    Безопасно вызывать повторно — не затирает данные.
    """
    sheets_api = service.spreadsheets()

    # Получить список существующих листов
    meta = sheets_api.get(spreadsheetId=spreadsheet_id).execute()
    existing = {s["properties"]["title"] for s in meta["sheets"]}
    logger.info(f"Существующие листы: {existing}")

    requests = []

    # Создать листы если не существуют
    for title in ["Ежедневно", "Еженедельно", "Дашборд"]:
        if title not in existing:
            requests.append({
                "addSheet": {"properties": {"title": title}}
            })

    if requests:
        sheets_api.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()
        logger.info(f"Созданы листы: {[r['addSheet']['properties']['title'] for r in requests]}")

    # Записать заголовки
    _write_headers(service, spreadsheet_id)
    logger.info("Структура таблицы готова")


def _write_headers(service, spreadsheet_id: str):
    """Записать заголовки в первую строку каждого листа."""
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "RAW",
            "data": [
                {"range": "Ежедневно!A1", "values": [HEADERS_DAILY]},
                {"range": "Еженедельно!A1", "values": [HEADERS_WEEKLY]},
            ]
        }
    ).execute()
    logger.info("Заголовки записаны")


# ---------------------------------------------------------------------------
# Запись ежедневных данных
# ---------------------------------------------------------------------------

def write_daily_row(service, spreadsheet_id: str, data: dict):
    """
    Добавить строку с ежедневными данными в лист «Ежедневно».
    data — словарь из collect_daily_data() + ручные данные из Telegram.
    """
    report_date = data.get("date", str(date.today()))

    # Автоматические данные из iiko
    summary  = data.get("orders_summary") or {}
    payments = data.get("payment_types") or {}
    cats     = data.get("category_revenue") or {}
    hourly   = data.get("hourly") or {}
    manual   = data.get("manual") or {}  # ручной ввод из Telegram

    revenue  = summary.get("revenue", 0)
    orders   = summary.get("orders", 0)
    guests   = summary.get("guests", 0)
    avg_chk  = summary.get("avg_check", 0)

    # Подбираем ключи кухни и бара (зависит от названий категорий в iiko)
    kitchen = _find_category(cats, ["кухня", "kitchen", "еда", "food"])
    bar     = _find_category(cats, ["бар", "bar", "напитки", "drink"])

    утро  = hourly.get("утро",  {})
    день  = hourly.get("день",  {})
    вечер = hourly.get("вечер", {})

    # Персонал
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

    # Статус заполнения
    has_manual = bool(manual)
    status = "✅ полный" if has_manual else "⚠️ авто (без кассы)"

    row = [
        report_date,
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
        # Ручной ввод
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

    # Найти первую пустую строку (после заголовка)
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="Ежедневно!A:A"
    ).execute()
    next_row = len(result.get("values", [])) + 1

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Ежедневно!A{next_row}",
        valueInputOption="USER_ENTERED",
        body={"values": [row]}
    ).execute()

    logger.info(f"Строка за {report_date} записана в строку {next_row}")


# ---------------------------------------------------------------------------
# Запись еженедельных данных
# ---------------------------------------------------------------------------

def write_weekly_row(service, spreadsheet_id: str, data: dict):
    """
    Добавить строку с еженедельными данными в лист «Еженедельно».
    data — словарь из _aggregate_weekly() в main.py.
    """
    row = [
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
        "", "", "",  # Гостей 1/2/3+ чел — из iiko отдельным запросом (Этап 4)
        "", "", "", "", "", "",  # Градация чеков
        "", "", "",  # Топ-3 блюда
        "", "",      # Мероприятия
        _v(data.get("zp_total")),
    ]

    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="Еженедельно!A:A"
    ).execute()
    next_row = len(result.get("values", [])) + 1

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Еженедельно!A{next_row}",
        valueInputOption="USER_ENTERED",
        body={"values": [row]}
    ).execute()

    logger.info(f"Еженедельная строка (неделя {data.get('week_num')}) записана в строку {next_row}")


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
