"""
iiko_client.py — клиент для работы с iiko REST API.
Документация: https://ru.iiko.help (iikoServer API)
"""

import hashlib
import logging
import time
from datetime import date, datetime, timedelta

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

TIMEOUT = 30          # секунды ожидания ответа
RETRY_COUNT = 3       # количество попыток при ошибке
RETRY_PAUSE = 60      # пауза между попытками (сек); в боевом режиме — 600


# ---------------------------------------------------------------------------
# Авторизация
# ---------------------------------------------------------------------------

def _md5(text: str) -> str:
    """MD5-хэш строки в нижнем регистре — формат iiko."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def get_token(base_url: str, login: str, password: str) -> str:
    """
    Получить токен авторизации.
    Токен живёт ~15 минут — вызывать в начале каждого запуска.
    """
    url = f"{base_url}/auth"
    params = {"login": login, "pass": _md5(password)}
    response = _request("GET", url, params=params)
    token = response.text.strip()
    if not token:
        raise ValueError("iiko вернул пустой токен авторизации")
    logger.info("Токен iiko получен успешно")
    return token


# ---------------------------------------------------------------------------
# Базовый запрос с retry
# ---------------------------------------------------------------------------

def _request(method: str, url: str, *, params=None, json=None) -> requests.Response:
    """
    HTTP-запрос с retry-логикой.
    3 попытки с паузой RETRY_PAUSE секунд между ними.
    """
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            logger.debug(f"[{method}] {url} | попытка {attempt}")
            resp = requests.request(
                method, url,
                params=params,
                json=json,
                timeout=TIMEOUT
            )
            resp.raise_for_status()
            logger.debug(f"[{method}] {url} → {resp.status_code}")
            return resp
        except requests.exceptions.HTTPError as e:
            # 401 — токен протух, пробрасываем выше для повторной авторизации
            if resp.status_code == 401:
                raise
            logger.warning(f"HTTP ошибка {resp.status_code} на попытке {attempt}: {e}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Сетевая ошибка на попытке {attempt}: {e}")

        if attempt < RETRY_COUNT:
            logger.info(f"Пауза {RETRY_PAUSE} сек перед следующей попыткой...")
            time.sleep(RETRY_PAUSE)

    raise ConnectionError(f"iiko API недоступен после {RETRY_COUNT} попыток: {url}")


def _olap(base_url: str, token: str, payload: dict) -> dict:
    """Выполнить OLAP-запрос v2."""
    url = f"{base_url}/v2/reports/olap"
    params = {"key": token}
    resp = _request("POST", url, params=params, json=payload)
    return resp.json()


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _date_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _sum_from_olap(data: dict, field: str = "DishSumInt") -> float:
    """Суммировать поле из OLAP-ответа (строки data > columnNames + data)."""
    try:
        cols = data["columnNames"]
        idx = cols.index(field)
        return sum(float(row[idx] or 0) for row in data.get("data", []))
    except (KeyError, ValueError) as e:
        logger.warning(f"Не удалось извлечь поле '{field}': {e}")
        return 0.0


def _rows_from_olap(data: dict) -> list[dict]:
    """Преобразовать OLAP-ответ в список словарей."""
    cols = data.get("columnNames", [])
    return [dict(zip(cols, row)) for row in data.get("data", [])]


# ---------------------------------------------------------------------------
# Основные запросы
# ---------------------------------------------------------------------------

def get_revenue_by_payment_type(base_url: str, token: str, report_date: date) -> dict:
    """
    Выручка по типам оплаты: нал, СБП, карта, по счёту.
    Возвращает словарь {тип_оплаты: сумма}.
    """
    payload = {
        "reportType": "SALES",
        "buildSummary": True,
        "groupByRowFields": ["PayTypes"],
        "aggregateFields": ["DishSumInt"],
        "filters": {
            "dateFrom": _date_str(report_date),
            "dateTo": _date_str(report_date),
        }
    }
    data = _olap(base_url, token, payload)
    result = {}
    for row in _rows_from_olap(data):
        pay_type = row.get("PayTypes", "Неизвестно")
        amount = float(row.get("DishSumInt", 0) or 0)
        result[pay_type] = result.get(pay_type, 0) + amount
    logger.info(f"Выручка по типам оплаты: {result}")
    return result


def get_orders_summary(base_url: str, token: str, report_date: date) -> dict:
    """
    Сводка по заказам: кол-во чеков, кол-во гостей, выручка итого, средний чек.
    """
    payload = {
        "reportType": "SALES",
        "buildSummary": True,
        "groupByRowFields": [],
        "aggregateFields": ["DishSumInt", "GuestsCount", "OrdersCount"],
        "filters": {
            "dateFrom": _date_str(report_date),
            "dateTo": _date_str(report_date),
        }
    }
    data = _olap(base_url, token, payload)
    rows = _rows_from_olap(data)
    if not rows:
        return {"orders": 0, "guests": 0, "revenue": 0.0, "avg_check": 0.0}

    row = rows[0]
    orders = int(row.get("OrdersCount", 0) or 0)
    guests = int(row.get("GuestsCount", 0) or 0)
    revenue = float(row.get("DishSumInt", 0) or 0)
    avg_check = round(revenue / orders, 2) if orders > 0 else 0.0

    result = {
        "orders": orders,
        "guests": guests,
        "revenue": revenue,
        "avg_check": avg_check,
    }
    logger.info(f"Сводка по заказам: {result}")
    return result


def get_revenue_by_category(base_url: str, token: str, report_date: date) -> dict:
    """
    Выручка Кухня / Бар (по категории блюд).
    Возвращает словарь {категория: сумма}.
    """
    payload = {
        "reportType": "SALES",
        "buildSummary": True,
        "groupByRowFields": ["DishCategory"],
        "aggregateFields": ["DishSumInt"],
        "filters": {
            "dateFrom": _date_str(report_date),
            "dateTo": _date_str(report_date),
        }
    }
    data = _olap(base_url, token, payload)
    result = {}
    for row in _rows_from_olap(data):
        cat = row.get("DishCategory", "Неизвестно")
        amount = float(row.get("DishSumInt", 0) or 0)
        result[cat] = result.get(cat, 0) + amount
    logger.info(f"Выручка по категориям: {result}")
    return result


def get_revenue_by_hour(base_url: str, token: str, report_date: date) -> dict:
    """
    Выручка и гости по часам → сводка по временным срезам.
    Срезы: Утро 9–11, День 11–17, Вечер 17–21.
    Возвращает: {утро: {revenue, guests}, день: {...}, вечер: {...}}
    """
    payload = {
        "reportType": "SALES",
        "buildSummary": True,
        "groupByRowFields": ["Hour"],
        "aggregateFields": ["DishSumInt", "GuestsCount"],
        "filters": {
            "dateFrom": _date_str(report_date),
            "dateTo": _date_str(report_date),
        }
    }
    data = _olap(base_url, token, payload)

    slots = {
        "утро":   {"hours": range(9, 11),  "revenue": 0.0, "guests": 0},
        "день":   {"hours": range(11, 17), "revenue": 0.0, "guests": 0},
        "вечер":  {"hours": range(17, 21), "revenue": 0.0, "guests": 0},
    }

    for row in _rows_from_olap(data):
        try:
            hour = int(row.get("Hour", -1))
        except (TypeError, ValueError):
            continue
        revenue = float(row.get("DishSumInt", 0) or 0)
        guests = int(row.get("GuestsCount", 0) or 0)
        for slot_name, slot in slots.items():
            if hour in slot["hours"]:
                slot["revenue"] += revenue
                slot["guests"] += guests

    result = {
        name: {"revenue": round(slot["revenue"], 2), "guests": slot["guests"]}
        for name, slot in slots.items()
    }
    logger.info(f"Временные срезы: {result}")
    return result


def get_cancellations(base_url: str, token: str, report_date: date) -> float:
    """
    Сумма отмен / удалений из заказов (reportType: DELETIONS).
    """
    payload = {
        "reportType": "DELETIONS",
        "buildSummary": True,
        "groupByRowFields": [],
        "aggregateFields": ["DishSumInt"],
        "filters": {
            "dateFrom": _date_str(report_date),
            "dateTo": _date_str(report_date),
        }
    }
    data = _olap(base_url, token, payload)
    total = _sum_from_olap(data, "DishSumInt")
    logger.info(f"Отмены: {total} руб.")
    return round(total, 2)


def get_writeoffs(base_url: str, token: str, report_date: date) -> float:
    """
    Фактические списания из склада (отдельный endpoint /inventory/writeoffs).
    Берёт по closeDate (дата проводки), не createDate.
    """
    url = f"{base_url}/inventory/writeoffs"
    params = {
        "key": token,
        "dateFrom": _date_str(report_date),
        "dateTo": _date_str(report_date),
    }
    resp = _request("GET", url, params=params)
    data = resp.json()

    total = 0.0
    # Структура ответа: список документов, каждый содержит items с суммами
    for doc in data if isinstance(data, list) else data.get("writeoffs", []):
        for item in doc.get("items", []):
            total += float(item.get("sum", 0) or 0)

    logger.info(f"Списания: {total} руб.")
    return round(total, 2)


def get_top_dishes(base_url: str, token: str, report_date: date, top_n: int = 10) -> list[dict]:
    """
    Топ-N блюд по выручке.
    Возвращает список: [{"dish": "Название", "revenue": 1234.0, "count": 5}, ...]
    """
    payload = {
        "reportType": "SALES",
        "buildSummary": True,
        "groupByRowFields": ["DishName"],
        "aggregateFields": ["DishSumInt", "DishAmountInt"],
        "filters": {
            "dateFrom": _date_str(report_date),
            "dateTo": _date_str(report_date),
        }
    }
    data = _olap(base_url, token, payload)
    rows = _rows_from_olap(data)
    dishes = [
        {
            "dish": row.get("DishName", ""),
            "revenue": float(row.get("DishSumInt", 0) or 0),
            "count": int(row.get("DishAmountInt", 0) or 0),
        }
        for row in rows
    ]
    top = sorted(dishes, key=lambda x: x["revenue"], reverse=True)[:top_n]
    logger.info(f"Топ-{top_n} блюд получены ({len(dishes)} позиций всего)")
    return top


def get_guest_groups(base_url: str, token: str, report_date: date) -> dict:
    """
    Анализ групп гостей: 1 гость / 2 гостя / 3+ гостей в одном чеке.
    Возвращает: {"1": {"orders": N, "revenue": X}, "2": {...}, "3+": {...}}
    """
    payload = {
        "reportType": "SALES",
        "buildSummary": True,
        "groupByRowFields": ["GuestsCount"],
        "aggregateFields": ["OrdersCount", "DishSumInt"],
        "filters": {
            "dateFrom": _date_str(report_date),
            "dateTo": _date_str(report_date),
        }
    }
    data = _olap(base_url, token, payload)
    result = {"1": {"orders": 0, "revenue": 0.0},
              "2": {"orders": 0, "revenue": 0.0},
              "3+": {"orders": 0, "revenue": 0.0}}

    for row in _rows_from_olap(data):
        try:
            guests = int(row.get("GuestsCount", 0) or 0)
        except (TypeError, ValueError):
            continue
        orders = int(row.get("OrdersCount", 0) or 0)
        revenue = float(row.get("DishSumInt", 0) or 0)
        key = str(guests) if guests <= 2 else "3+"
        result[key]["orders"] += orders
        result[key]["revenue"] += revenue

    logger.info(f"Анализ групп: {result}")
    return result


def get_check_distribution(base_url: str, token: str, report_date: date) -> dict:
    """
    Градация чеков по сумме.
    Возвращает: {"0-500": N, "500-1000": N, ...}
    """
    payload = {
        "reportType": "SALES",
        "buildSummary": True,
        "groupByRowFields": ["OrderSum"],
        "aggregateFields": ["OrdersCount", "DishSumInt"],
        "filters": {
            "dateFrom": _date_str(report_date),
            "dateTo": _date_str(report_date),
        }
    }
    data = _olap(base_url, token, payload)

    brackets = [
        (0, 500, "0–500"),
        (500, 1000, "500–1000"),
        (1000, 1500, "1000–1500"),
        (1500, 3000, "1500–3000"),
        (3000, 5000, "3000–5000"),
        (5000, float("inf"), "5000+"),
    ]
    result = {label: 0 for _, _, label in brackets}

    for row in _rows_from_olap(data):
        try:
            order_sum = float(row.get("OrderSum", 0) or 0)
            count = int(row.get("OrdersCount", 1) or 1)
        except (TypeError, ValueError):
            continue
        for low, high, label in brackets:
            if low <= order_sum < high:
                result[label] += count
                break

    logger.info(f"Градация чеков: {result}")
    return result


# ---------------------------------------------------------------------------
# Сбор всех данных за день (главная функция)
# ---------------------------------------------------------------------------

def collect_daily_data(base_url: str, token: str, report_date: date) -> dict:
    """
    Собрать все автоматические данные iiko за указанный день.
    Возвращает словарь со всеми полями.
    При ошибке отдельного запроса — подставляет None и продолжает.
    """
    logger.info(f"Сбор данных iiko за {_date_str(report_date)}...")
    result = {"date": _date_str(report_date), "errors": []}

    def safe(key, fn, *args):
        try:
            result[key] = fn(*args)
        except Exception as e:
            logger.error(f"Ошибка при получении '{key}': {e}")
            result[key] = None
            result["errors"].append(f"{key}: {e}")

    safe("payment_types",     get_revenue_by_payment_type, base_url, token, report_date)
    safe("orders_summary",    get_orders_summary,          base_url, token, report_date)
    safe("category_revenue",  get_revenue_by_category,     base_url, token, report_date)
    safe("hourly",            get_revenue_by_hour,         base_url, token, report_date)
    safe("cancellations",     get_cancellations,           base_url, token, report_date)
    safe("writeoffs",         get_writeoffs,               base_url, token, report_date)
    safe("top_dishes",        get_top_dishes,              base_url, token, report_date)
    safe("guest_groups",      get_guest_groups,            base_url, token, report_date)
    safe("check_distribution",get_check_distribution,     base_url, token, report_date)

    if result["errors"]:
        logger.warning(f"Данные собраны с {len(result['errors'])} ошибками: {result['errors']}")
    else:
        logger.info("Все данные iiko собраны успешно")

    return result
