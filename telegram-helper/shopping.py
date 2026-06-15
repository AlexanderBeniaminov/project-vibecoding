"""
Шопинг-агент v3: один запрос к Яндекс.Маркет → реальные магазины с реальными ценами.
Маркет агрегирует WB, Ozon, Перекрёсток, Ашан и другие — никаких галлюцинаций.
Показываем только магазины с подтверждённым наличием, от дешёвого к дорогому.
Прямые API магазинов недоступны с VPS (PoW/403/429) — Маркет обходит это.
"""
import asyncio
import re
from urllib.parse import quote_plus

# Маппинг: как Яндекс.Маркет называет продавца → наш магазин
STORE_MAP = {
    "wildberries":  ("Wildberries",    "wildberries.ru",   "бесплатно",           0),
    "вайлдберриз":  ("Wildberries",    "wildberries.ru",   "бесплатно",           0),
    "wb":           ("Wildberries",    "wildberries.ru",   "бесплатно",           0),
    "ozon":         ("Ozon",           "ozon.ru",          "от 99 ₽",            99),
    "озон":         ("Ozon",           "ozon.ru",          "от 99 ₽",            99),
    "яндекс":       ("Яндекс.Маркет", "market.yandex.ru", "от 99 ₽",            99),
    "market":       ("Яндекс.Маркет", "market.yandex.ru", "от 99 ₽",            99),
    "маркет":       ("Яндекс.Маркет", "market.yandex.ru", "от 99 ₽",            99),
    "пятёрочка":    ("Пятёрочка",     "5ka.ru",           "бесплатно от 500 ₽",  0),
    "пятерочка":    ("Пятёрочка",     "5ka.ru",           "бесплатно от 500 ₽",  0),
    "перекрёсток":  ("Перекрёсток",   "perekrestok.ru",   "бесплатно от 700 ₽",  0),
    "перекресток":  ("Перекрёсток",   "perekrestok.ru",   "бесплатно от 700 ₽",  0),
    "лента":        ("Лента",         "lenta.com",        "бесплатно от 1500 ₽", 0),
    "ашан":         ("Ашан",          "auchan.ru",        "199 ₽",             199),
    "metro":        ("Metro",         "metro-cc.ru",      "299 ₽",             299),
    "метро":        ("Metro",         "metro-cc.ru",      "299 ₽",             299),
}

# Транслитерация брендов: для WB/Ozon лучше искать EN-название
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


def _search_url(domain: str, q_ru: str, q_en: str) -> str:
    """Генерируем поисковый URL магазина. WB/Ozon/Маркет получают EN-вариант бренда."""
    r = quote_plus(q_ru)
    e = quote_plus(q_en)
    return {
        "wildberries.ru":   f"https://www.wildberries.ru/catalog/0/search.aspx?search={e}",
        "ozon.ru":          f"https://www.ozon.ru/search/?text={e}",
        "market.yandex.ru": f"https://market.yandex.ru/search?text={e}",
        "5ka.ru":           f"https://5ka.ru/search/?search={r}",
        "perekrestok.ru":   f"https://www.perekrestok.ru/cat/search?search={r}",
        "lenta.com":        f"https://lenta.com/search/?q={r}",
        "auchan.ru":        f"https://www.auchan.ru/catalog/search/?q={r}",
        "metro-cc.ru":      f"https://online.metro-cc.ru/search?query={r}",
    }.get(domain, f"https://www.{domain}/search?q={r}")


async def search_all_stores(query: str, ai_client=None, model: str = "perplexity/sonar-pro") -> list[dict]:
    """
    Один запрос к Яндекс.Маркет через Perplexity.
    Маркет агрегирует реальные цены из WB, Ozon и других → только подтверждённые магазины.
    """
    product_ru = _clean_query(query)
    product_en = _enrich(product_ru)

    try:
        resp = await ai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Зайди на market.yandex.ru и найди предложения по товару.\n"
                        "Маркет показывает цены из разных магазинов.\n"
                        "Для каждого магазина где товар ЕСТЬ В НАЛИЧИИ — верни строку:\n"
                        "МАГАЗИН|ЦЕНА\n"
                        "Нас интересуют только эти магазины: "
                        "Wildberries, Ozon, Яндекс, Пятёрочка, Перекрёсток, Лента, Ашан, Metro.\n"
                        "ЦЕНА — только целое число рублей без знаков (пример: 705).\n"
                        "Не включай магазины где написано 'Нет в наличии' или 'Под заказ'.\n"
                        "Если товар не найден ни в одном из этих магазинов — верни: НЕТ\n"
                        "Только строки МАГАЗИН|ЦЕНА, никаких пояснений."
                    ),
                },
                {
                    "role": "user",
                    "content": f"market.yandex.ru: {product_en}",
                },
            ],
            max_tokens=200,
            temperature=0.0,
        )

        text = (resp.choices[0].message.content or "").strip()
        text = re.sub(r"\[\d+\]", "", text).strip()

        if not text or ("НЕТ" in text.upper() and "|" not in text):
            return []

        results = []
        seen = set()

        for line in text.splitlines():
            line = line.strip()
            if "|" not in line:
                continue
            parts = line.split("|", 1)
            store_raw  = parts[0].strip().lower()
            price_raw  = re.sub(r"[^\d]", "", parts[1].strip()) if len(parts) > 1 else ""
            if not price_raw:
                continue
            try:
                price = float(price_raw)
            except ValueError:
                continue
            if price <= 0:
                continue

            matched = None
            for key, info in STORE_MAP.items():
                if key in store_raw:
                    matched = info
                    break
            if not matched:
                continue

            name, domain, delivery, dcost = matched
            if name in seen:
                continue
            seen.add(name)

            results.append({
                "store":         name,
                "price":         price,
                "delivery":      delivery,
                "delivery_cost": dcost,
                "url":           _search_url(domain, product_ru, product_en),
                "product":       product_ru,
            })

        return results

    except Exception:
        return []


def format_results(query: str, results: list[dict]) -> str:
    product    = _clean_query(query)
    product_en = _enrich(product)

    if not results:
        yandex = f"https://market.yandex.ru/search?text={quote_plus(product_en)}"
        return (
            f"❌ «{product}» не найден в магазинах.\n\n"
            f"Поискать вручную на Яндекс.Маркет:\n{yandex}"
        )

    # Сортировка: дешевле с учётом доставки
    sorted_res = sorted(results, key=lambda r: r["price"] + r["delivery_cost"])

    lines = [f"🛒 {product}\n"]

    for r in sorted_res:
        total = r["price"] + r["delivery_cost"]
        if r["delivery_cost"] == 0:
            d_str = f"доставка {r['delivery']}"
        else:
            d_str = f"доставка {r['delivery']}, итого {total:.0f} ₽"
        lines.append(f"📦 {r['store']} — {r['price']:.0f} ₽ ({d_str})")
        lines.append(r["url"])
        lines.append("")

    best       = sorted_res[0]
    best_total = best["price"] + best["delivery_cost"]
    lines.append(f"✅ Дешевле всего: {best['store']} — {best_total:.0f} ₽ с доставкой")

    return "\n".join(lines).rstrip()
