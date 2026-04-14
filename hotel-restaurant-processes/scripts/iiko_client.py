"""
iiko_client.py — клиент для iikoWeb OLAP.

Авторизация: POST /api/auth/login {login, password} → JWT-токен
Данные:      POST /api/olap/init {storeIds, olapType, groupFields, dataFields, filters}
             GET  /api/olap/fetch-status/{requestId} → "SUCCESS" / "PROCESSING" / "ERROR"
             POST /api/olap/fetch/{requestId}/DATA {rowOffset, rowCount} → rawData

Переменные окружения:
    IIKO_WEB_URL      = https://kafe-monblan.iikoweb.ru
    IIKO_WEB_LOGIN    = buh
    IIKO_WEB_PASSWORD = Vjy,kfy2024
    IIKO_STORE_ID     = 82455
"""

import logging
import os
import time
from datetime import date, timedelta

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

IIKO_WEB_URL  = "https://kafe-monblan.iikoweb.ru"
TIMEOUT       = 30
SESSION_TTL   = 1100  # сек (токен живёт 1200 сек, обновляем чуть раньше)

OLAP_POLL_INTERVAL = 3    # сек между проверками статуса
OLAP_POLL_RETRIES  = 20   # макс попыток

# Реальные категории Монблан (поле DishCategory, проверено 14.04.2026)
KITCHEN_CATEGORIES = {"кухня", "десерты", "завтрак"}
BAR_CATEGORIES     = {"бар", "настойки", "пиво бутылочное", "глинтвейн"}

# Фильтры: только не удалённые позиции и заказы
FILTER_NOT_DELETED = [
    {
        "field": "DeletedWithWriteoff",
        "filterType": "value_list",
        "dateFrom": None, "dateTo": None,
        "valueMin": None, "valueMax": None,
        "valueList": ["NOT_DELETED"],
        "includeLeft": True, "includeRight": False, "inclusiveList": True,
    },
    {
        "field": "OrderDeleted",
        "filterType": "value_list",
        "dateFrom": None, "dateTo": None,
        "valueMin": None, "valueMax": None,
        "valueList": ["NOT_DELETED"],
        "includeLeft": True, "includeRight": False, "inclusiveList": True,
    },
]


def _date_filter(date_from: str, date_to: str) -> dict:
    """Фильтр по дате открытия заказа (формат YYYY-MM-DD)."""
    return {
        "field": "OpenDate.Typed",
        "filterType": "date_range",
        "dateFrom": date_from,
        "dateTo": date_to,
        "valueMin": None, "valueMax": None,
        "valueList": [],
        "includeLeft": True, "includeRight": True, "inclusiveList": True,
    }


# ---------------------------------------------------------------------------
# iikoWeb сессия
# ---------------------------------------------------------------------------

class IikoWebSession:
    """Сессия iikoWeb: логин → JWT токен + auto-refresh."""

    def __init__(
        self,
        base_url: str,
        login: str,
        password: str,
        store_id: int,
    ) -> None:
        self.base_url  = base_url.rstrip("/")
        self.login_str = login
        self.password  = password
        self.store_id  = store_id
        self._session  = requests.Session()
        self._token    = ""
        self._token_ts = 0.0

    def _ensure_token(self) -> None:
        if time.time() - self._token_ts > SESSION_TTL:
            self._login()

    def _login(self) -> None:
        resp = self._session.post(
            f"{self.base_url}/api/auth/login",
            json={"login": self.login_str, "password": self.password},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise PermissionError(f"iikoWeb login: {data.get('errorMessage')}")
        self._token    = data["token"]
        self._token_ts = time.time()
        logger.info(f"iikoWeb: авторизован как {self.login_str} (store={self.store_id})")

    def post(self, path: str, body: dict) -> dict:
        self._ensure_token()
        resp = self._session.post(
            f"{self.base_url}{path}",
            json=body,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def get(self, path: str) -> dict:
        self._ensure_token()
        resp = self._session.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# OLAP запрос
# ---------------------------------------------------------------------------

def _olap_query(
    session: IikoWebSession,
    olap_type: str,
    group_fields: list[str],
    data_fields: list[str],
    filters: list[dict],
) -> list[dict]:
    """
    Выполнить OLAP-запрос. Возвращает rawData (список dict) или [].
    olap_type: "SALES" | "TRANSACTIONS"
    """
    body = {
        "storeIds":    [session.store_id],
        "olapType":    olap_type,
        "groupFields": group_fields,
        "dataFields":  data_fields,
        "filters":     filters,
    }

    init = session.post("/api/olap/init", body)
    if init.get("error"):
        raise RuntimeError(f"olap/init: {init.get('errorMessage')}")

    req_id = init.get("data", "")
    if not req_id:
        raise RuntimeError("olap/init: нет requestId")

    # Ждём SUCCESS
    for attempt in range(OLAP_POLL_RETRIES):
        time.sleep(OLAP_POLL_INTERVAL)
        status_resp = session.get(f"/api/olap/fetch-status/{req_id}")
        status = status_resp.get("data", "")
        logger.debug(f"OLAP [{olap_type}] статус: {status} (попытка {attempt+1})")
        if status in ("SUCCESS", "READY"):
            break
        if status == "ERROR":
            logger.warning(f"OLAP [{olap_type}] вернул ERROR. groupFields={group_fields}")
            return []
    else:
        logger.warning(f"OLAP [{olap_type}] timeout")
        return []

    fetch = session.post(
        f"/api/olap/fetch/{req_id}/DATA",
        {"rowOffset": 0, "rowCount": 10000},
    )
    if fetch.get("error"):
        logger.warning(f"olap/fetch error: {fetch.get('errorMessage')}")
        return []

    return fetch.get("result", {}).get("rawData", [])


# ---------------------------------------------------------------------------
# Сбор данных за день
# ---------------------------------------------------------------------------

def collect_daily_data_iiko_web(
    session: IikoWebSession,
    report_date: date,
) -> dict:
    """
    Собрать данные через iikoWeb OLAP.
    Возвращает dict со всеми показателями дня.
    """
    ds = report_date.strftime("%Y-%m-%d")
    logger.info(f"[iikoWeb OLAP] Сбор за {ds}, store={session.store_id}")

    df = [_date_filter(ds, ds)] + FILTER_NOT_DELETED
    result: dict = {"date": ds, "errors": []}

    # --- 1. Сводка ---
    try:
        rows = _olap_query(
            session, "SALES",
            group_fields=["OpenDate.Typed"],
            data_fields=["DishDiscountSumInt", "UniqOrderId.OrdersCount", "GuestNum", "DishDiscountSumInt.average"],
            filters=df,
        )
        rev = orders = guests = 0
        avg_check = 0.0
        for row in rows:
            rev     += row.get("DishDiscountSumInt", 0) or 0
            orders  += row.get("UniqOrderId.OrdersCount", 0) or 0
            guests  += row.get("GuestNum", 0) or 0
        avg_check = round(rev / orders, 2) if orders else 0.0
        result["orders_summary"] = {
            "revenue":   round(rev, 2),
            "orders":    int(orders),
            "guests":    int(guests),
            "avg_check": avg_check,
        }
        logger.info(f"[OLAP] Сводка: {result['orders_summary']}")
    except Exception as e:
        logger.error(f"[OLAP] Сводка: {e}", exc_info=True)
        result["orders_summary"] = None
        result["errors"].append(f"orders_summary: {e}")

    # --- 2. Типы оплаты ---
    try:
        rows = _olap_query(
            session, "SALES",
            group_fields=["PayTypes.Combo"],
            data_fields=["DishDiscountSumInt"],
            filters=df,
        )
        payments: dict = {}
        for row in rows:
            name   = row.get("PayTypes.Combo") or "Неизвестно"
            amount = row.get("DishDiscountSumInt") or 0
            payments[name] = payments.get(name, 0.0) + amount
        result["payment_types"] = payments
        logger.info(f"[OLAP] Оплаты: {payments}")
    except Exception as e:
        logger.error(f"[OLAP] Типы оплаты: {e}", exc_info=True)
        result["payment_types"] = {}
        result["errors"].append(f"payment_types: {e}")

    # --- 3. Категории (Кухня / Бар) ---
    # Используем DishCategory (не DishCategory.Accounting — она всегда "Товар")
    try:
        rows = _olap_query(
            session, "SALES",
            group_fields=["DishCategory"],
            data_fields=["DishDiscountSumInt"],
            filters=df,
        )
        cats: dict = {"Кухня": 0.0, "Бар": 0.0, "Другое": 0.0}
        for row in rows:
            cat_name = (row.get("DishCategory") or "").strip().lower()
            amount   = row.get("DishDiscountSumInt") or 0
            if cat_name in KITCHEN_CATEGORIES:
                cats["Кухня"] += amount
            elif cat_name in BAR_CATEGORIES:
                cats["Бар"] += amount
            else:
                cats["Другое"] += amount
        result["category_revenue"] = cats
        logger.info(f"[OLAP] Категории: {cats}")
    except Exception as e:
        logger.error(f"[OLAP] Категории: {e}", exc_info=True)
        result["category_revenue"] = {}
        result["errors"].append(f"category_revenue: {e}")

    # --- 4. Топ блюд ---
    try:
        rows = _olap_query(
            session, "SALES",
            group_fields=["DishName"],
            data_fields=["DishAmountInt", "DishDiscountSumInt"],
            filters=df,
        )
        dishes = [
            {
                "dish":    row.get("DishName") or "Неизвестно",
                "count":   row.get("DishAmountInt") or 0,
                "revenue": row.get("DishDiscountSumInt") or 0,
            }
            for row in rows
        ]
        result["top_dishes"] = sorted(dishes, key=lambda x: x["revenue"], reverse=True)[:10]
        logger.info(f"[OLAP] Топ-3: {[d['dish'] for d in result['top_dishes'][:3]]}")
    except Exception as e:
        logger.error(f"[OLAP] Топ блюд: {e}", exc_info=True)
        result["top_dishes"] = []
        result["errors"].append(f"top_dishes: {e}")

    # --- 5. Отмены ---
    try:
        cancel_filters = [_date_filter(ds, ds)] + [{
            "field": "OrderDeleted",
            "filterType": "value_list",
            "dateFrom": None, "dateTo": None,
            "valueMin": None, "valueMax": None,
            "valueList": ["DELETED"],
            "includeLeft": True, "includeRight": False, "inclusiveList": True,
        }]
        rows = _olap_query(
            session, "SALES",
            group_fields=["OpenDate.Typed"],
            data_fields=["DishDiscountSumInt", "UniqOrderId.OrdersCount"],
            filters=cancel_filters,
        )
        cancel_rev = sum(r.get("DishDiscountSumInt") or 0 for r in rows)
        result["cancellations"] = round(cancel_rev, 2)
    except Exception as e:
        logger.warning(f"[OLAP] Отмены: {e}")
        result["cancellations"] = None
        result["errors"].append(f"cancellations: {e}")

    # --- 5. Временные срезы по часам (утро 9-11, день 11-17, вечер 17-21) ---
    try:
        rows = _olap_query(
            session, "SALES",
            group_fields=["HourClose"],
            data_fields=["DishDiscountSumInt", "GuestNum"],
            filters=df,
        )
        slots = {
            "утро":  {"revenue": 0.0, "guests": 0},
            "день":  {"revenue": 0.0, "guests": 0},
            "вечер": {"revenue": 0.0, "guests": 0},
        }
        for row in rows:
            hour    = int(row.get("HourClose") or 0)
            revenue = row.get("DishDiscountSumInt") or 0
            guests  = row.get("GuestNum") or 0
            if 9 <= hour < 11:
                slots["утро"]["revenue"]  += revenue
                slots["утро"]["guests"]   += guests
            elif 11 <= hour < 17:
                slots["день"]["revenue"]  += revenue
                slots["день"]["guests"]   += guests
            elif 17 <= hour < 21:
                slots["вечер"]["revenue"] += revenue
                slots["вечер"]["guests"]  += guests
        result["hourly"] = slots
        logger.info(f"[OLAP] Срезы: утро={slots['утро']['revenue']} день={slots['день']['revenue']} вечер={slots['вечер']['revenue']}")
    except Exception as e:
        logger.error(f"[OLAP] Временные срезы: {e}", exc_info=True)
        result["hourly"] = None
        result["errors"].append(f"hourly: {e}")

    result["guest_groups"]       = None
    result["check_distribution"] = None
    result["writeoffs"]          = None   # TRANSACTIONS недоступен для пользователя buh

    return result


# ---------------------------------------------------------------------------
# Главная точка входа
# ---------------------------------------------------------------------------

def collect_daily_data(report_date: date) -> dict:
    """
    Создаёт сессию из env-переменных и собирает данные за день.
    """
    web_url      = os.environ.get("IIKO_WEB_URL",      IIKO_WEB_URL)
    web_login    = os.environ.get("IIKO_WEB_LOGIN",    "")
    web_password = os.environ.get("IIKO_WEB_PASSWORD", "")
    store_id     = int(os.environ.get("IIKO_STORE_ID", "82455"))

    if not web_login or not web_password:
        raise EnvironmentError("Необходимы IIKO_WEB_LOGIN и IIKO_WEB_PASSWORD")

    session = IikoWebSession(web_url, web_login, web_password, store_id)
    session._login()
    return collect_daily_data_iiko_web(session, report_date)


# ---------------------------------------------------------------------------
# Обратная совместимость (для test_iiko.py)
# ---------------------------------------------------------------------------

BASE_URL = IIKO_WEB_URL


def get_token(api_login: str) -> str:
    """Stub: возвращает пустую строку — Transport API не используется."""
    logger.warning("get_token() не используется — данные берутся из iikoWeb OLAP")
    return ""


def get_payment_types_map(token: str, org_id: str) -> dict:
    return {}


def get_terminal_group_ids(token: str, org_id: str) -> list:
    return []


def get_table_ids(token: str, terminal_group_ids: list) -> list:
    return []
