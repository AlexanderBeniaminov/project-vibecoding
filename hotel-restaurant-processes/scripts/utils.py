"""
utils.py — вспомогательные функции.
"""

import time
import logging
import requests
from datetime import date, datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# UTC+5 для ресторана
TZ_UTC5 = timezone(timedelta(hours=5))


# ---------------------------------------------------------------------------
# Дата
# ---------------------------------------------------------------------------

def today_utc5() -> date:
    """Сегодняшняя дата в UTC+5 (часовой пояс ресторана)."""
    return datetime.now(TZ_UTC5).date()


def yesterday_utc5() -> date:
    """Вчерашняя дата в UTC+5."""
    return today_utc5() - timedelta(days=1)


def week_bounds(for_date: date = None) -> tuple[date, date]:
    """
    Вернуть (понедельник, воскресенье) для недели, в которую входит for_date.
    Если for_date — понедельник, возвращает прошедшую неделю.
    """
    if for_date is None:
        for_date = today_utc5()
    # Если сегодня понедельник — берём прошлую неделю (пн–вс)
    days_since_monday = for_date.weekday()  # 0=пн
    if days_since_monday == 0:
        days_since_monday = 7
    monday = for_date - timedelta(days=days_since_monday)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def fmt_date(d: date) -> str:
    """Формат YYYY-MM-DD для iiko API."""
    return d.strftime("%Y-%m-%d")


def fmt_date_ru(d: date) -> str:
    """Формат ДД.ММ.ГГГГ для Telegram-сообщений."""
    return d.strftime("%d.%m.%Y")


def fmt_money(value) -> str:
    """Форматировать число как деньги: 1 234 567 руб."""
    try:
        return f"{int(value):,}".replace(",", " ") + " руб."
    except (TypeError, ValueError):
        return "—"


def fmt_int(value) -> str:
    """Форматировать целое число с пробелами как разделителями."""
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

def retry(func, *args, retries: int = 3, pause: float = 5.0, label: str = "", **kwargs):
    """
    Вызвать func(*args, **kwargs) с повтором при исключении.
    retries — число попыток (включая первую).
    pause   — пауза в секундах между попытками.
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            logger.warning(
                f"[retry] {label or func.__name__}: попытка {attempt}/{retries} упала: {exc}"
            )
            if attempt < retries:
                time.sleep(pause)
    raise last_exc


# ---------------------------------------------------------------------------
# Парсинг ответа администратора
# ---------------------------------------------------------------------------

def parse_admin_reply(text: str):
    """
    Разобрать текстовый ответ администратора.

    Ожидаемый формат:
        Инкассация: 70000
        Расход: 3500
        Остаток: 26500
        Завтраки: 12
        Повара: 3/9000
        Официанты: 4/12000
        Бармены: 1/3500
        Посудомойщицы: 2/5000

    Поддерживает разные форматы разделителей (: / =).
    Возвращает None если текст не распознан.
    """
    if not text:
        return None

    result = {}
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    parsed = 0

    for line in lines:
        # Разбиваем по первому : или =
        for sep in (":", "="):
            if sep in line:
                key, _, val = line.partition(sep)
                key = key.strip().lower()
                val = val.strip()
                _parse_admin_field(key, val, result)
                parsed += 1
                break

    return result if parsed >= 3 else None


def _parse_admin_field(key: str, val: str, result: dict):
    """Разобрать одну строку ответа администратора."""
    def _num(s):
        try:
            return float(s.replace(" ", "").replace(",", "."))
        except ValueError:
            return 0

    def _staff(s):
        """Разобрать 'кол/зп' → {"кол": int, "зп": float}"""
        if "/" in s:
            parts = s.split("/", 1)
            return {"кол": int(_num(parts[0])), "зп": _num(parts[1])}
        return {"кол": int(_num(s)), "зп": 0}

    # Маппинг ключевых слов → поля result
    if any(w in key for w in ["инкасс"]):
        result["инкассация"] = _num(val)
    elif any(w in key for w in ["расход"]):
        result["расход_кассы"] = _num(val)
    elif any(w in key for w in ["остаток"]):
        result["остаток_нал"] = _num(val)
    elif any(w in key for w in ["завтрак"]):
        result["завтраки"] = int(_num(val))
    elif any(w in key for w in ["повар"]):
        result["повара"] = _staff(val)
    elif any(w in key for w in ["официант"]):
        result["официанты"] = _staff(val)
    elif any(w in key for w in ["бармен", "барман"]):
        result["бармены"] = _staff(val)
    elif any(w in key for w in ["посудомо"]):
        result["посудомойщицы"] = _staff(val)
