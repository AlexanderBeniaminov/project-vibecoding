"""
config.py — константы проекта.
Секреты (ключи, токены) — только через переменные окружения, не здесь.
"""

import os
from datetime import date

# ---------------------------------------------------------------------------
# iiko API
# ---------------------------------------------------------------------------

IIKO_BASE_URL = os.environ.get("IIKO_BASE_URL", "https://593-760-434.iiko.it/resto/api")
IIKO_LOGIN    = os.environ.get("IIKO_LOGIN", "")
IIKO_PASSWORD = os.environ.get("IIKO_PASSWORD", "")

# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------

SHEETS_ID = os.environ.get("GOOGLE_SHEETS_ID", "")
# JSON-содержимое сервисного аккаунта одной строкой
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# Имена листов
SHEET_DAILY   = "Ежедневно"
SHEET_WEEKLY  = "Еженедельно"
SHEET_DASHBOARD = "Дашборд"

# ---------------------------------------------------------------------------
# MAX мессенджер (основной канал уведомлений)
# ---------------------------------------------------------------------------

MAX_BOT_TOKEN      = os.environ.get("MAX_BOT_TOKEN", "")
MAX_OWNER_USER_ID  = os.environ.get("MAX_OWNER_USER_ID", "")   # собственник
MAX_ADMIN_USER_ID  = os.environ.get("MAX_ADMIN_USER_ID", "")   # администратор
MAX_DEV_USER_ID    = os.environ.get("MAX_DEV_USER_ID", "")     # разработчик

# ---------------------------------------------------------------------------
# Ресторан
# ---------------------------------------------------------------------------

RESTAURANT_NAME = "Монблан"
TIMEZONE = "Asia/Yekaterinburg"  # UTC+5 (реальный ресторан)

# Вместимость зала — меняется в зависимости от даты
CAPACITY_CHANGE_DATE = date(2025, 12, 15)

def get_capacity(report_date: date) -> dict:
    """
    Вернуть вместимость зала на указанную дату.
    До 15.12.2025: 14 столов, 58 мест.
    С 15.12.2025: 15 столов, 90 мест.
    """
    if report_date < CAPACITY_CHANGE_DATE:
        return {"tables": 14, "seats": 58}
    return {"tables": 15, "seats": 90}

# Временные срезы (часы, локальное время)
TIME_SLOTS = {
    "утро":  (9, 11),   # 09:00–11:00
    "день":  (11, 17),  # 11:00–17:00
    "вечер": (17, 21),  # 17:00–21:00
}

# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

RETRY_COUNT = 3
RETRY_PAUSE_SEC = 600   # 10 минут (боевой режим)
REQUEST_TIMEOUT = 30
