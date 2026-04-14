"""
Извлечение структурированных данных (площадь, цена, прибыль, окупаемость)
из произвольного текста объявлений на русском языке.
"""
import re
from typing import Optional


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _clean_number(s: str) -> Optional[float]:
    """'15 000 000' → 15000000.0, '1,5 млн' → 1500000.0"""
    s = s.strip().replace("\xa0", " ").replace(" ", "")

    # млн/млрд
    multiplier = 1.0
    s_lower = s.lower()
    if "млрд" in s_lower:
        multiplier = 1_000_000_000
        s = re.sub(r"млрд.*", "", s_lower).strip(",. ")
    elif "млн" in s_lower:
        multiplier = 1_000_000
        s = re.sub(r"млн.*", "", s_lower).strip(",. ")

    s = s.replace(",", ".").replace(" ", "")
    s = re.sub(r"[^\d.]", "", s)
    try:
        return float(s) * multiplier if s else None
    except ValueError:
        return None


# ─── Площадь ─────────────────────────────────────────────────────────────────

_AREA_PATTERNS = [
    # "1 200 м²", "1200 кв.м", "1 200 кв. м.", "площадь 1200"
    r"(\d[\d\s]{0,5}\d|\d+)[,.]?\d*\s*(?:м²|кв\.?\s*м\.?|sq\.?\s*m)",
    r"площадь[:\s]+(\d[\d\s]{0,5})",
    r"(\d[\d\s]{0,5})\s*(?:метр|квадрат)",
]

def extract_area(text: str) -> Optional[float]:
    """Возвращает площадь в м² или None."""
    for pattern in _AREA_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = _clean_number(m.group(1) if m.lastindex else m.group(0))
            if val and 50 < val < 100_000:  # здравый смысл
                return val
    return None


# ─── Цена ─────────────────────────────────────────────────────────────────────

_PRICE_PATTERNS = [
    r"цена[:\s]+(\d[\d\s,\.]*(?:млн|млрд|тыс)?\.?\s*(?:руб|₽|рублей)?)",
    r"стоимость[:\s]+(\d[\d\s,\.]*(?:млн|млрд|тыс)?\.?\s*(?:руб|₽|рублей)?)",
    r"продаётся за\s+(\d[\d\s,\.]*(?:млн|млрд|тыс)?\.?\s*(?:руб|₽|рублей)?)",
    r"(\d[\d\s,\.]*)\s*(?:млн|млрд)?\s*(?:руб\.|рублей|₽)",
]

def extract_price(text: str) -> Optional[float]:
    """Возвращает цену в рублях или None."""
    for pattern in _PRICE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = _clean_number(m.group(1))
            if val and 100_000 < val < 10_000_000_000:
                return val
    return None


# ─── Прибыль в месяц ─────────────────────────────────────────────────────────

_PROFIT_PATTERNS = [
    r"прибыль[:\s/]+(\d[\d\s,\.]*(?:млн|тыс)?\.?\s*(?:руб|₽|рублей)?)\s*(?:в\s*мес|/\s*мес|мес)",
    r"доход[:\s/]+(\d[\d\s,\.]*(?:млн|тыс)?\.?\s*(?:руб|₽|рублей)?)\s*(?:в\s*мес|/\s*мес|мес)",
    r"чистая\s+прибыль[:\s]+(\d[\d\s,\.]*(?:млн|тыс)?\.?\s*(?:руб|₽)?)",
    r"(\d[\d\s,\.]*(?:млн|тыс)?\.?\s*(?:руб|₽|рублей)?)\s*(?:прибыль|доход)\s*(?:в\s*мес|/\s*мес)",
]

def extract_profit(text: str) -> Optional[float]:
    """Возвращает прибыль в рублях в месяц или None."""
    for pattern in _PROFIT_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = _clean_number(m.group(1))
            if val and 1_000 < val < 1_000_000_000:
                return val
    return None


# ─── Окупаемость ─────────────────────────────────────────────────────────────

_PAYBACK_PATTERNS = [
    r"окупаемость[:\s]+(\d+\.?\d*)\s*(?:мес|лет|год|года)",
    r"окупится за\s+(\d+\.?\d*)\s*(?:мес|лет|год)",
    r"срок окупаемости[:\s]+(\d+\.?\d*)\s*(?:мес|лет|год)",
]
_PAYBACK_YEARS = re.compile(r"(?:лет|год|года)", re.IGNORECASE)

def extract_payback(text: str) -> Optional[float]:
    """Возвращает окупаемость в месяцах или None."""
    for pattern in _PAYBACK_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = _clean_number(m.group(1))
            if val is None:
                continue
            # если указано в годах — конвертируем
            context = text[m.start():m.end()]
            if _PAYBACK_YEARS.search(context):
                val = val * 12
            if 1 <= val <= 360:
                return val
    return None


# ─── Тип локации ─────────────────────────────────────────────────────────────

_TRC_KEYWORDS = ["трц", "тц", "торгов", "молл", "mall", "shopping"]
_STANDALONE_KEYWORDS = ["отдельн", "собственн", "здани", "помещени", "особняк"]

def detect_location_type(text: str) -> str:
    text_lower = text.lower()
    if any(kw in text_lower for kw in _TRC_KEYWORDS):
        return "ТРЦ"
    if any(kw in text_lower for kw in _STANDALONE_KEYWORDS):
        return "отдельное здание"
    return "не указано"


# ─── Тип продавца ─────────────────────────────────────────────────────────────

_OWNER_KEYWORDS = ["собственник", "владелец", "прямой продавец", "от владельца"]
_BROKER_KEYWORDS = ["брокер", "агент", "посредник", "агентств", "консультант"]

def detect_seller_type(text: str) -> str:
    text_lower = text.lower()
    if any(kw in text_lower for kw in _OWNER_KEYWORDS):
        return "собственник"
    if any(kw in text_lower for kw in _BROKER_KEYWORDS):
        return "брокер"
    return "не указано"
