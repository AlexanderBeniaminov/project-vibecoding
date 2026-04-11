"""
iiko_client.py — клиент для iiko.

РЕЖИМ 1 (основной): iikoWeb OLAP
    URL: https://kafe-monblan.iikoweb.ru
    Auth: POST /api/auth/login {login, password} → JWT token + PHPSESSID cookie
    Данные: POST /api/olap/init {storeIds, reportType, ...} → requestId
            GET  /api/olap/fetch-status/{requestId} → "READY" / "PROCESSING" / "ERROR"
            POST /api/olap/fetch/{requestId}/DATA {rowOffset, rowCount} → строки

РЕЖИМ 2 (fallback): iiko Transport API OLAP
    URL: https://api-ru.iiko.services
    Auth: POST /api/1/access_token {apiLogin} → Bearer token
    Данные: POST /api/1/reports/olap — требует прав OLAP в API-логине

Переменные окружения:
    IIKO_WEB_URL      = https://kafe-monblan.iikoweb.ru  (или IIKO_API_LOGIN)
    IIKO_WEB_LOGIN    = buh
    IIKO_WEB_PASSWORD = Vjy,kfy2024
    IIKO_STORE_ID     = 82455  (внутренний ID iikoWeb, получить из /api/kpi-metric/stores)
    IIKO_API_LOGIN    = 42c9095b39264541b93ba7b0b21feb6e  (Transport API)
    IIKO_ORG_ID       = 6551e510-21d3-4ae1-8034-5eb229987543
"""

import logging
import os
import time
from datetime import date, datetime

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

IIKO_WEB_URL  = "https://kafe-monblan.iikoweb.ru"
TRANSPORT_URL = "https://api-ru.iiko.services"
TIMEOUT       = 30
RETRY_COUNT   = 3
RETRY_PAUSE   = 5

# Синонимы для обратной совместимости (используется в test_iiko.py)
BASE_URL = TRANSPORT_URL

# Временные срезы (часы, локальное время)
TIME_SLOTS = {
    "утро":  range(9, 11),
    "день":  range(11, 17),
    "вечер": range(17, 21),
}

KITCHEN_KEYWORDS = ["кухня", "kitchen", "еда", "food", "блюда", "горяч"]
BAR_KEYWORDS     = ["бар", "bar", "напитк", "drink", "beverage", "алкогол"]


# ---------------------------------------------------------------------------
# Авторизация — Transport API (iiko Cloud)
# ---------------------------------------------------------------------------

def get_token(api_login: str) -> str:
    """Bearer-токен iiko Transport API. Живёт 60 мин."""
    resp = requests.post(
        f"{TRANSPORT_URL}/api/1/access_token",
        json={"apiLogin": api_login},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    token = resp.json().get("token", "")
    if not token:
        raise ValueError("Transport API вернул пустой токен")
    logger.info("Transport API: токен получен")
    return token


# ---------------------------------------------------------------------------
# Авторизация — iikoWeb (логин/пароль)
# ---------------------------------------------------------------------------

class IikoWebSession:
    """Сессия iikoWeb с JWT-токеном и PHPSESSID cookie."""

    def __init__(self, base_url: str = IIKO_WEB_URL):
        self.base_url = base_url
        self.session  = requests.Session()
        self.token    = ""

    def login(self, login: str, password: str) -> None:
        """Авторизоваться в iikoWeb. Сохраняет cookie и Bearer-токен."""
        resp = self.session.post(
            f"{self.base_url}/api/auth/login",
            json={"login": login, "password": password},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise PermissionError(f"iikoWeb login error: {data.get('errorMessage')}")
        self.token = data["token"]
        logger.info(f"iikoWeb: авторизован как {login}, store={data.get('store')}")

    def post(self, path: str, body: dict) -> dict:
        resp = self.session.post(
            f"{self.base_url}{path}",
            json=body,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def get(self, path: str) -> dict:
        resp = self.session.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# iikoWeb OLAP
# ---------------------------------------------------------------------------

OLAP_POLL_INTERVAL = 3   # сек между проверками статуса
OLAP_POLL_RETRIES  = 20  # макс попыток (~60 сек)


def _iiko_web_olap_query(
    session: IikoWebSession,
    store_id: int,
    report_type: str,
    group_rows: list,
    aggregates: list,
    filters: dict,
) -> list:
    """
    Выполнить один OLAP-запрос через iikoWeb.
    Возвращает список строк data (или пустой список при ошибке).
    """
    body = {
        "storeIds":         [store_id],
        "reportType":       report_type,
        "buildSummary":     False,
        "groupByRowFields": group_rows,
        "groupByColFields": [],
        "aggregateFields":  aggregates,
        "filters":          filters,
    }

    init = session.post("/api/olap/init", body)
    if init.get("error"):
        raise RuntimeError(f"olap/init error: {init.get('errorMessage')}")

    request_id = init.get("data", "")
    if not request_id:
        raise RuntimeError("olap/init: нет requestId в ответе")

    # Ждём READY
    for _ in range(OLAP_POLL_RETRIES):
        time.sleep(OLAP_POLL_INTERVAL)
        status_resp = session.get(f"/api/olap/fetch-status/{request_id}")
        status = status_resp.get("data", "")
        logger.debug(f"OLAP status: {status}")
        if status == "READY":
            break
        if status == "ERROR":
            logger.warning(f"OLAP ERROR для {report_type} {aggregates}")
            return []
    else:
        logger.warning(f"OLAP timeout для {report_type}")
        return []

    # Получаем данные
    fetch = session.post(
        f"/api/olap/fetch/{request_id}/DATA",
        {"rowOffset": 0, "rowCount": 10000},
    )
    if fetch.get("error"):
        logger.warning(f"olap/fetch error: {fetch.get('errorMessage')}")
        return []

    return fetch.get("data", [])


def _extract_dim(row: dict, field: str) -> str:
    """Извлечь значение dimension из строки OLAP."""
    dims = row.get("dimensionValues") or row.get("dimensions") or {}
    if isinstance(dims, dict):
        return dims.get(field, "")
    # Иногда список пар
    if isinstance(dims, list):
        for d in dims:
            if d.get("fieldId") == field or d.get("name") == field:
                return d.get("value", "")
    return str(row.get(field, ""))


def _extract_agg(row: dict, field: str) -> float:
    """Извлечь значение aggregate из строки OLAP."""
    aggs = row.get("aggregateValues") or row.get("aggregates") or {}
    if isinstance(aggs, dict):
        return float(aggs.get(field, 0) or 0)
    if isinstance(aggs, list):
        for a in aggs:
            if a.get("fieldId") == field or a.get("name") == field:
                return float(a.get("value", 0) or 0)
    return float(row.get(field, 0) or 0)


def collect_daily_data_iiko_web(
    session: IikoWebSession,
    store_id: int,
    report_date: date,
) -> dict:
    """
    Собрать данные через iikoWeb OLAP.
    store_id: внутренний integer ID iikoWeb (например, 82455).
    """
    ds = report_date.strftime("%Y-%m-%d")
    logger.info(f"[iikoWeb OLAP] Сбор данных за {ds}, store={store_id}")

    date_filter = {
        "OpenDate.Typed": {
            "filterType": "DateRange",
            "periodType":  "CUSTOM",
            "from":        ds,
            "to":          ds,
        }
    }

    result: dict = {"date": ds, "errors": []}

    # --- 1. Сводка ---
    try:
        rows = _iiko_web_olap_query(
            session, store_id, "SALES",
            group_rows=["OpenDate.Typed"],
            aggregates=["DishDiscountSumInt", "OrderCount", "GuestNum"],
            filters=date_filter,
        )
        rev, orders, guests = 0.0, 0, 0
        for row in rows:
            rev    += _extract_agg(row, "DishDiscountSumInt")
            orders += int(_extract_agg(row, "OrderCount"))
            guests += int(_extract_agg(row, "GuestNum"))
        result["orders_summary"] = {
            "revenue":   round(rev, 2),
            "orders":    orders,
            "guests":    guests,
            "avg_check": round(rev / orders, 2) if orders else 0.0,
        }
        logger.info(f"[iikoWeb OLAP] Сводка: {result['orders_summary']}")
    except Exception as e:
        logger.error(f"[iikoWeb OLAP] Сводка: {e}", exc_info=True)
        result["orders_summary"] = None
        result["errors"].append(f"orders_summary: {e}")

    # --- 2. Типы оплаты ---
    try:
        rows = _iiko_web_olap_query(
            session, store_id, "SALES",
            group_rows=["PayTypes.PayType.Name"],
            aggregates=["PayTypes.PaySum"],
            filters=date_filter,
        )
        payments = {}
        for row in rows:
            name   = _extract_dim(row, "PayTypes.PayType.Name") or "Неизвестно"
            amount = _extract_agg(row, "PayTypes.PaySum")
            payments[name] = payments.get(name, 0.0) + amount
        result["payment_types"] = payments
        logger.info(f"[iikoWeb OLAP] Оплаты: {payments}")
    except Exception as e:
        logger.error(f"[iikoWeb OLAP] Типы оплаты: {e}", exc_info=True)
        result["payment_types"] = {}
        result["errors"].append(f"payment_types: {e}")

    # --- 3. Категории (Кухня/Бар) ---
    try:
        rows = _iiko_web_olap_query(
            session, store_id, "SALES",
            group_rows=["DishCategory"],
            aggregates=["DishDiscountSumInt"],
            filters=date_filter,
        )
        cats = {"Кухня": 0.0, "Бар": 0.0, "Другое": 0.0}
        for row in rows:
            cat_name = (_extract_dim(row, "DishCategory") or "").lower()
            amount   = _extract_agg(row, "DishDiscountSumInt")
            if any(w in cat_name for w in KITCHEN_KEYWORDS):
                cats["Кухня"] += amount
            elif any(w in cat_name for w in BAR_KEYWORDS):
                cats["Бар"] += amount
            else:
                cats["Другое"] += amount
        result["category_revenue"] = cats
        logger.info(f"[iikoWeb OLAP] Категории: {cats}")
    except Exception as e:
        logger.error(f"[iikoWeb OLAP] Категории: {e}", exc_info=True)
        result["category_revenue"] = {}
        result["errors"].append(f"category_revenue: {e}")

    # --- 4. Топ блюд ---
    try:
        rows = _iiko_web_olap_query(
            session, store_id, "SALES",
            group_rows=["DishName"],
            aggregates=["DishAmountInt", "DishDiscountSumInt"],
            filters=date_filter,
        )
        dishes = []
        for row in rows:
            dishes.append({
                "dish":    _extract_dim(row, "DishName") or "Неизвестно",
                "count":   _extract_agg(row, "DishAmountInt"),
                "revenue": _extract_agg(row, "DishDiscountSumInt"),
            })
        result["top_dishes"] = sorted(dishes, key=lambda x: x["revenue"], reverse=True)[:10]
        logger.info(f"[iikoWeb OLAP] Топ-3: {[d['dish'] for d in result['top_dishes'][:3]]}")
    except Exception as e:
        logger.error(f"[iikoWeb OLAP] Топ блюд: {e}", exc_info=True)
        result["top_dishes"] = []
        result["errors"].append(f"top_dishes: {e}")

    # Temporal slots и per-order метрики через OLAP недоступны напрямую
    result["hourly"]             = None
    result["guest_groups"]       = None
    result["check_distribution"] = None
    result["cancellations"]      = None
    result["writeoffs"]          = None

    return result


# ---------------------------------------------------------------------------
# Transport API — вспомогательные функции (для test_iiko.py)
# ---------------------------------------------------------------------------

def get_payment_types_map(token: str, org_id: str) -> dict:
    resp = requests.post(
        f"{TRANSPORT_URL}/api/1/payment_types",
        json={"organizationIds": [org_id]},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return {pt["id"]: pt.get("name", pt.get("code", "?"))
            for pt in resp.json().get("paymentTypes", [])}


def get_terminal_group_ids(token: str, org_id: str) -> list:
    resp = requests.post(
        f"{TRANSPORT_URL}/api/1/terminal_groups",
        json={"organizationIds": [org_id], "includeDisabled": False},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    ids = []
    for org_entry in resp.json().get("terminalGroups", []):
        for tg in org_entry.get("items", []):
            if tg.get("id"):
                ids.append(tg["id"])
    return ids


def get_table_ids(token: str, terminal_group_ids: list) -> list:
    if not terminal_group_ids:
        return []
    resp = requests.post(
        f"{TRANSPORT_URL}/api/1/reserve/available_restaurant_sections",
        json={"terminalGroupIds": terminal_group_ids},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    ids = []
    for section in resp.json().get("restaurantSections", []):
        for table in section.get("tables", []):
            if table.get("id"):
                ids.append(table["id"])
    return ids


# ---------------------------------------------------------------------------
# Главная точка входа
# ---------------------------------------------------------------------------

def collect_daily_data(token: str, org_id: str, report_date: date) -> dict:
    """
    Собрать данные за день.

    Приоритет:
    1. iikoWeb OLAP (логин/пароль из env IIKO_WEB_LOGIN / IIKO_WEB_PASSWORD)
    2. Transport API OLAP (если выданы права в api-логине)
    3. Fallback: пустые данные с предупреждением

    Для iikoWeb нужны env-переменные:
        IIKO_WEB_LOGIN    = buh
        IIKO_WEB_PASSWORD = Vjy,kfy2024
        IIKO_STORE_ID     = 82455
    """
    ds = report_date.strftime("%Y-%m-%d")
    logger.info(f"=== Сбор данных за {ds} ===")

    web_login    = os.environ.get("IIKO_WEB_LOGIN", "")
    web_password = os.environ.get("IIKO_WEB_PASSWORD", "")
    store_id_str = os.environ.get("IIKO_STORE_ID", "82455")

    # --- Режим 1: iikoWeb OLAP ---
    if web_login and web_password:
        try:
            store_id = int(store_id_str)
            session = IikoWebSession(IIKO_WEB_URL)
            session.login(web_login, web_password)
            result = collect_daily_data_iiko_web(session, store_id, report_date)
            if result.get("errors"):
                logger.warning(f"iikoWeb OLAP: {len(result['errors'])} ошибок")
            else:
                logger.info("iikoWeb OLAP: все данные собраны")
            return result
        except Exception as e:
            logger.error(f"iikoWeb OLAP недоступен: {e}", exc_info=True)

    # --- Режим 2: Transport API OLAP ---
    logger.warning("Переключаемся на Transport API (данных нет — OLAP не выдаёт POS-заказы)")
    return {
        "date":             ds,
        "orders_summary":   {"revenue": 0, "orders": 0, "guests": 0, "avg_check": 0},
        "payment_types":    {},
        "category_revenue": {},
        "hourly":           None,
        "top_dishes":       [],
        "guest_groups":     None,
        "check_distribution": None,
        "cancellations":    None,
        "writeoffs":        None,
        "errors":           ["iikoWeb OLAP недоступен, Transport API не даёт POS-данные"],
    }
