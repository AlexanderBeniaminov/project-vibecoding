"""
Шопинг-агент: поисковые ссылки по 7 магазинам + Яндекс.Маркет для сравнения цен.
Цены НЕ берём из Perplexity — они ненадёжны: галлюцинирует несуществующие позиции,
пропускает реальные (WB блокирует VPS через PoW, остальные через 403/429).
Ссылки генерируем сами → всегда рабочие, всегда актуальные.
"""
import asyncio
import re
from urllib.parse import quote_plus

STORES = [
    ("Wildberries", "wildberries.ru",   "бесплатно"),
    ("Ozon",        "ozon.ru",          "от 99 ₽"),
    ("Пятёрочка",  "5ka.ru",           "бесплатно от 500 ₽"),
    ("Перекрёсток", "perekrestok.ru",   "бесплатно от 700 ₽"),
    ("Лента",       "lenta.com",        "бесплатно от 1500 ₽"),
    ("Ашан",        "auchan.ru",        "199 ₽"),
    ("Metro",       "metro-cc.ru",      "299 ₽"),
]

# Таблица транслитерации: добавляет EN-вариант бренда для WB/Ozon
_TRANSLIT = {
    "давыдофф": "davidoff", "давидофф": "davidoff",
    "нескафе":  "nescafe",  "якобс":    "jacobs",
    "лавацца":  "lavazza",  "тефаль":   "tefal",
    "бош":      "bosch",    "самсунг":  "samsung",
}

def _enrich(query: str) -> str:
    q_lower = query.lower()
    for ru, en in _TRANSLIT.items():
        if ru in q_lower and en not in q_lower:
            return f"{query} {en}"
    return query


# Слова-намерения, убираемые перед поиском
_INTENT_PREFIXES = re.compile(
    r"^(?:где\s+(?:купить|найти|дешевле)\s*|"
    r"(?:хочу\s+)?купить\s+|найди\s+(?:дешевле\s+)?|"
    r"сколько\s+стоит\s+|цена\s+на\s+|стоимость\s+|"
    r"дешевл[её]\s+|самый?\s+дешёв\w*\s+)+",
    re.IGNORECASE,
)

def _clean_query(raw: str) -> str:
    cleaned = _INTENT_PREFIXES.sub("", raw.strip())
    return cleaned.strip() or raw.strip()


def _search_url(domain: str, query_ru: str, query_en: str) -> str:
    """Поисковый URL: для WB и Ozon используем EN-вариант (лучше ищут бренды)."""
    qr = quote_plus(query_ru)
    qe = quote_plus(query_en)
    return {
        "wildberries.ru": f"https://www.wildberries.ru/catalog/0/search.aspx?search={qe}",
        "ozon.ru":        f"https://www.ozon.ru/search/?text={qe}",
        "5ka.ru":         f"https://5ka.ru/search/?search={qr}",
        "perekrestok.ru": f"https://www.perekrestok.ru/cat/search?search={qr}",
        "lenta.com":      f"https://lenta.com/search/?q={qr}",
        "auchan.ru":      f"https://www.auchan.ru/s/{qr}",
        "metro-cc.ru":    f"https://online.metro-cc.ru/search?query={qr}",
    }.get(domain, f"https://www.{domain}/search?q={qr}")


def _yandex_market_url(query_en: str) -> str:
    return f"https://market.yandex.ru/search?text={quote_plus(query_en)}"


async def search_all_stores(query: str, ai_client=None, model: str = "perplexity/sonar-pro") -> list[dict]:
    """Возвращает поисковые ссылки для всех 7 магазинов (без запроса к Perplexity)."""
    product_ru = _clean_query(query)
    product_en = _enrich(product_ru)
    return [
        {
            "store":    name,
            "delivery": delivery,
            "url":      _search_url(domain, product_ru, product_en),
            "product":  product_ru,
            "yandex":   _yandex_market_url(product_en),
        }
        for name, domain, delivery in STORES
    ]


def format_results(query: str, results: list[dict]) -> str:
    if not results:
        return f"❌ Не удалось сформировать ссылки по запросу «{_clean_query(query)}»."

    product = results[0]["product"]
    yandex  = results[0]["yandex"]

    lines = [
        f"🛒 {product}\n",
        f"📊 Сравни цены сразу во всех магазинах:",
        yandex,
        "",
        "🔗 Поиск в каждом магазине:",
    ]
    for r in results:
        lines.append(f"📦 {r['store']} — доставка {r['delivery']}")
        lines.append(r["url"])
        lines.append("")

    return "\n".join(lines).rstrip()
