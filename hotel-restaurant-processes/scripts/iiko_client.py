"""
iiko_client.py — клиент для iiko Cloud API.
Документация: https://api-ru.iiko.services
Auth: POST /api/1/access_token {apiLogin} → Bearer token
Все запросы: Authorization: Bearer {token} + organizationId в теле.
"""

import logging
import time
from datetime import date

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

BASE_URL     = "https://api-ru.iiko.services"
TIMEOUT      = 30
RETRY_COUNT  = 3
RETRY_PAUSE  = 5    # сек в тестовом режиме; в боевом — 600


# ---------------------------------------------------------------------------
# Авторизация
# ---------------------------------------------------------------------------

def get_token(api_login: str) -> str:
    """
    Получить Bearer-токен iiko Cloud.
    Токен живёт 60 минут — вызывать в начале каждого запуска.
    """
    url = f"{BASE_URL}/api/1/access_token"
    resp = _request("POST", url, json={"apiLogin": api_login})
    token = resp.json().get("token", "")
    if not token:
        raise ValueError("iiko Cloud вернул пустой токен авторизации")
    logger.info("Токен iiko Cloud получен успешно")
    return token


# ---------------------------------------------------------------------------
# Базовый запрос с retry
# ---------------------------------------------------------------------------

def _request(method: str, url: str, *, token: str = None, json=None) -> requests.Response:
    """
    HTTP-запрос с retry-логикой.
    Если передан token — добавляет Authorization: Bearer header.
    """
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            logger.debug(f"[{method}] {url} | попытка {attempt}")
            resp = requests.request(
                method, url,
                headers=headers,
                json=json,
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            logger.debug(f"[{method}] {url} → {resp.status_code}")
            return resp
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 401:
                raise   # токен протух — пробрасываем для повторной авторизации
            logger.warning(f"HTTP {resp.status_code} на попытке {attempt}: {e}")
            logger.warning(f"Тело ответа: {resp.text[:500]}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Сетевая ошибка на попытке {attempt}: {e}")

        if attempt < RETRY_COUNT:
            logger.info(f"Пауза {RETRY_PAUSE} сек перед следующей попыткой...")
            time.sleep(RETRY_PAUSE)

    raise ConnectionError(f"iiko Cloud API недоступен после {RETRY_COUNT} попыток: {url}")


# ---------------------------------------------------------------------------
# OLAP-запрос
# ---------------------------------------------------------------------------

def _olap(token: str, org_id: str, payload: dict) -> dict:
    """
    Выполнить OLAP-запрос к iiko Cloud API.
    Добавляет organizationIds в payload автоматически.
    """
    url = f"{BASE_URL}/api/1/reports/olap"
    body = {"organizationIds": [org_id], **payload}
    resp = _request("POST", url, token=token, json=body)
    return resp.json()


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _date_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _date_filter(report_date: date) -> dict:
    """Стандартный фильтр по дате для OLAP."""
    ds = _date_str(report_date)
    return {
        "OpenDate.Typed": {
            "filterType": "DateRange",
            "periodType": "CUSTOM",
            "from": ds,
            "to":   ds,
            "includeLow":  "true",
            "includeHigh": "true",
        }
    }


def _sum_from_olap(data: dict, field: str = "DishSumInt") -> float:
    """Суммировать поле из OLAP-ответа."""
    if not data.get("columnNames"):
        return 0.0
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

def get_revenue_by_payment_type(token: str, org_id: str, report_date: date) -> dict:
    """Выручка по типам оплаты: нал, СБП, карта, по счёту."""
    data = _olap(token, org_id, {
        "reportType": "SALES",
        "buildSummary": True,
        "groupByRowFields": ["PayTypes"],
        "aggregateFields": ["DishSumInt"],
        "filters": _date_filter(report_date),
    })
    result = {}
    for row in _rows_from_olap(data):
        pay_type = row.get("PayTypes", "Неизвестно")
        amount = float(row.get("DishSumInt", 0) or 0)
        result[pay_type] = result.get(pay_type, 0) + amount
    logger.info(f"Выручка по типам оплаты: {result}")
    return result


def get_orders_summary(token: str, org_id: str, report_date: date) -> dict:
    """Сводка: кол-во чеков, гостей, выручка итого, средний чек."""
    data = _olap(token, org_id, {
        "reportType": "SALES",
        "buildSummary": True,
        "groupByRowFields": [],
        "aggregateFields": ["DishSumInt", "GuestNum", "OrderNum"],
        "filters": _date_filter(report_date),
    })
    rows = _rows_from_olap(data)
    if not rows:
        return {"orders": 0, "guests": 0, "revenue": 0.0, "avg_check": 0.0}

    row = rows[0]
    orders  = int(row.get("OrderNum", 0) or 0)
    guests  = int(row.get("GuestNum", 0) or 0)
    revenue = float(row.get("DishSumInt", 0) or 0)
    avg_check = round(revenue / orders, 2) if orders > 0 else 0.0

    result = {"orders": orders, "guests": guests, "revenue": revenue, "avg_check": avg_check}
    logger.info(f"Сводка по заказам: {result}")
    return result


def get_revenue_by_category(token: str, org_id: str, report_date: date) -> dict:
    """Выручка Кухня / Бар (по категории блюд)."""
    data = _olap(token, org_id, {
        "reportType": "SALES",
        "buildSummary": True,
        "groupByRowFields": ["DishCategory"],
        "aggregateFields": ["DishSumInt"],
        "filters": _date_filter(report_date),
    })
    result = {}
    for row in _rows_from_olap(data):
        cat = row.get("DishCategory", "Неизвестно")
        amount = float(row.get("DishSumInt", 0) or 0)
        result[cat] = result.get(cat, 0) + amount
    logger.info(f"Выручка по категориям: {result}")
    return result


def get_revenue_by_hour(token: str, org_id: str, report_date: date) -> dict:
    """Выручка и гости по временным срезам (утро/день/вечер)."""
    data = _olap(token, org_id, {
        "reportType": "SALES",
        "buildSummary": True,
        "groupByRowFields": ["OpenTime"],
        "aggregateFields": ["DishSumInt", "GuestNum"],
        "filters": _date_filter(report_date),
    })

    slots = {
        "утро":  {"hours": range(9, 11),  "revenue": 0.0, "guests": 0},
        "день":  {"hours": range(11, 17), "revenue": 0.0, "guests": 0},
        "вечер": {"hours": range(17, 21), "revenue": 0.0, "guests": 0},
    }

    for row in _rows_from_olap(data):
        open_time = row.get("OpenTime", "") or ""
        try:
            hour = int(open_time.split("T")[1].split(":")[0]) if "T" in open_time else int(open_time.split(":")[0])
        except (ValueError, IndexError):
            continue
        revenue = float(row.get("DishSumInt", 0) or 0)
        guests  = int(row.get("GuestNum", 0) or 0)
        for slot_name, slot in slots.items():
            if hour in slot["hours"]:
                slot["revenue"] += revenue
                slot["guests"]  += guests

    result = {
        name: {"revenue": round(slot["revenue"], 2), "guests": slot["guests"]}
        for name, slot in slots.items()
    }
    logger.info(f"Временные срезы: {result}")
    return result


def get_cancellations(token: str, org_id: str, report_date: date) -> float:
    """Сумма отмен/удалений из заказов."""
    total = 0.0
    for deleted_val in ["DELETED_WITH_WRITEOFF", "DELETED_WITHOUT_WRITEOFF"]:
        filters = _date_filter(report_date)
        filters["DeletedWithWriteoff"] = {
            "filterType": "IncludeValues",
            "values": [deleted_val],
        }
        data = _olap(token, org_id, {
            "reportType": "SALES",
            "buildSummary": True,
            "groupByRowFields": [],
            "aggregateFields": ["DishSumInt"],
            "filters": filters,
        })
        total += _sum_from_olap(data, "DishSumInt")
    logger.info(f"Отмены: {total} руб.")
    return round(total, 2)


def get_writeoffs(token: str, org_id: str, report_date: date) -> float:
    """Фактические списания из склада."""
    url = f"{BASE_URL}/api/1/documents/writeoff"
    ds = _date_str(report_date)
    resp = _request("POST", url, token=token, json={
        "organizationIds": [org_id],
        "dateFrom": ds,
        "dateTo":   ds,
    })
    data = resp.json()

    total = 0.0
    docs = data.get("writeoffs", data.get("response", []))
    if isinstance(docs, dict):
        docs = docs.get("items", [])
    for doc in (docs if isinstance(docs, list) else []):
        for item in doc.get("items", []):
            total += float(item.get("sum", 0) or item.get("cost", 0) or 0)

    logger.info(f"Списания: {total} руб.")
    return round(total, 2)


def get_top_dishes(token: str, org_id: str, report_date: date, top_n: int = 10) -> list[dict]:
    """Топ-N блюд по выручке."""
    data = _olap(token, org_id, {
        "reportType": "SALES",
        "buildSummary": True,
        "groupByRowFields": ["DishName"],
        "aggregateFields": ["DishSumInt", "DishAmountInt"],
        "filters": _date_filter(report_date),
    })
    dishes = [
        {
            "dish": row.get("DishName", ""),
            "revenue": float(row.get("DishSumInt", 0) or 0),
            "count": int(row.get("DishAmountInt", 0) or 0),
        }
        for row in _rows_from_olap(data)
    ]
    top = sorted(dishes, key=lambda x: x["revenue"], reverse=True)[:top_n]
    logger.info(f"Топ-{top_n} блюд получены ({len(dishes)} позиций всего)")
    return top


def get_guest_groups(token: str, org_id: str, report_date: date) -> dict:
    """Анализ групп гостей: 1 / 2 / 3+ гостей в одном чеке."""
    data = _olap(token, org_id, {
        "reportType": "SALES",
        "buildSummary": True,
        "groupByRowFields": ["GuestNum"],
        "aggregateFields": ["OrderNum", "DishSumInt"],
        "filters": _date_filter(report_date),
    })
    result = {"1": {"orders": 0, "revenue": 0.0},
              "2": {"orders": 0, "revenue": 0.0},
              "3+": {"orders": 0, "revenue": 0.0}}

    for row in _rows_from_olap(data):
        try:
            guests = int(row.get("GuestNum", 0) or 0)
        except (TypeError, ValueError):
            continue
        orders  = int(row.get("OrderNum", 0) or 0)
        revenue = float(row.get("DishSumInt", 0) or 0)
        key = str(guests) if guests <= 2 else "3+"
        result[key]["orders"]  += orders
        result[key]["revenue"] += revenue

    logger.info(f"Анализ групп: {result}")
    return result


def get_check_distribution(token: str, org_id: str, report_date: date) -> dict:
    """Градация чеков по сумме."""
    data = _olap(token, org_id, {
        "reportType": "SALES",
        "buildSummary": False,
        "groupByRowFields": ["OrderNum"],
        "aggregateFields": ["DishSumInt"],
        "filters": _date_filter(report_date),
    })

    brackets = [
        (0,    500,          "0–500"),
        (500,  1000,         "500–1000"),
        (1000, 1500,         "1000–1500"),
        (1500, 3000,         "1500–3000"),
        (3000, 5000,         "3000–5000"),
        (5000, float("inf"), "5000+"),
    ]
    result = {label: 0 for _, _, label in brackets}

    for row in _rows_from_olap(data):
        try:
            order_sum = float(row.get("DishSumInt", 0) or 0)
        except (TypeError, ValueError):
            continue
        for low, high, label in brackets:
            if low <= order_sum < high:
                result[label] += 1
                break

    logger.info(f"Градация чеков: {result}")
    return result


# ---------------------------------------------------------------------------
# Сбор всех данных за день (главная функция)
# ---------------------------------------------------------------------------

def collect_daily_data(token: str, org_id: str, report_date: date) -> dict:
    """
    Собрать все данные iiko Cloud за указанный день.
    При ошибке отдельного запроса — подставляет None и продолжает.
    """
    logger.info(f"Сбор данных iiko Cloud за {_date_str(report_date)}...")
    result = {"date": _date_str(report_date), "errors": []}

    def safe(key, fn, *args):
        try:
            result[key] = fn(*args)
        except Exception as e:
            logger.error(f"Ошибка при получении '{key}': {e}")
            result[key] = None
            result["errors"].append(f"{key}: {e}")

    safe("payment_types",      get_revenue_by_payment_type, token, org_id, report_date)
    safe("orders_summary",     get_orders_summary,          token, org_id, report_date)
    safe("category_revenue",   get_revenue_by_category,     token, org_id, report_date)
    safe("hourly",             get_revenue_by_hour,         token, org_id, report_date)
    safe("cancellations",      get_cancellations,           token, org_id, report_date)
    safe("writeoffs",          get_writeoffs,               token, org_id, report_date)
    safe("top_dishes",         get_top_dishes,              token, org_id, report_date)
    safe("guest_groups",       get_guest_groups,            token, org_id, report_date)
    safe("check_distribution", get_check_distribution,      token, org_id, report_date)

    if result["errors"]:
        logger.warning(f"Данные собраны с {len(result['errors'])} ошибками: {result['errors']}")
    else:
        logger.info("Все данные iiko Cloud собраны успешно")

    return result
