"""
Шопинг-агент v5:
- Гарантированная база: WB + Ozon + Яндекс.Маркет всегда (без логина/города)
- 1 Perplexity-вызов с НАТУРАЛЬНЫМ промптом (без жёсткого формата → не возвращает НЕТ)
- Парсер свободного текста → извлекает магазин + минимальную цену из любого ответа
- Локация: Химки / Москва / Московская область
- Сортировка: с ценой ↑, без цены — снизу
"""
import asyncio
import re
from urllib.parse import quote_plus

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


# Шаблоны для распознавания магазинов в свободном тексте
_STORE_PATTERNS = [
    ("Wildberries",    r"wildberries|вайлдберриз|\bwb\b",      "wildberries.ru",   "бесплатно",           0),
    ("Ozon",           r"\bozon\b|озон",                        "ozon.ru",          "от 99 ₽",            99),
    ("Яндекс.Маркет", r"яндекс[.\s]маркет|яндекс-маркет|\bмаркет\b", "market.yandex.ru", "от 99 ₽",   99),
    ("Пятёрочка",     r"пятёрочка|пятерочка",                  "5ka.ru",           "бесплатно от 500 ₽",  0),
    ("Перекрёсток",   r"перекрёсток|перекресток",              "perekrestok.ru",   "бесплатно от 700 ₽",  0),
    ("Лента",         r"\bлента\b",                             "lenta.com",        "бесплатно от 1500 ₽", 0),
    ("Ашан",          r"\bашан\b",                              "auchan.ru",        "199 ₽",             199),
    ("Metro",         r"\bmetro\b|\bметро\b",                   "metro-cc.ru",      "299 ₽",             299),
]

# Фразы, указывающие на отсутствие товара в строке
_UNAVAILABLE_RE = re.compile(
    r"нет в наличии|не нахожу|не найден|недоступен|нет данных|"
    r"sold out|нет на сайте|не продаётся|не продается|отсутствует",
    re.IGNORECASE,
)

# Цена: число (возможно с пробелами-разделителями тысяч) перед ₽ или руб
_PRICE_RE = re.compile(r"(\d[\d\s]{0,6}\d|\d)\s*(?:₽|руб\.?)", re.IGNORECASE)


def _parse_prices(text: str) -> dict[str, float]:
    """
    Извлекает цены из свободного текста Perplexity.
    Обрабатывает строки вида: 'Ozon — 1 405 ₽', 'Wildberries: ~705 руб' и т.п.
    Если в строке магазина написано 'нет в наличии' — пропускаем.
    """
    # Убираем сноски вида [1], [12]
    text = re.sub(r"\[\d+\]", "", text)

    prices: dict[str, float] = {}

    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue

        # Определяем магазин для этой строки
        matched_name = None
        for name, pattern, *_ in _STORE_PATTERNS:
            if re.search(pattern, line_clean, re.IGNORECASE):
                matched_name = name
                break
        if not matched_name:
            continue

        # Если строка говорит о недоступности — пропускаем
        if _UNAVAILABLE_RE.search(line_clean):
            continue

        # Ищем цену в строке
        found = _PRICE_RE.findall(line_clean)
        if not found:
            continue

        nums = []
        for p in found:
            try:
                nums.append(float(p.replace(" ", "").replace(" ", "")))
            except ValueError:
                pass

        if nums and matched_name not in prices:
            prices[matched_name] = min(nums)  # берём минимальную цену из строки

    return prices


async def search_all_stores(query: str, ai_client=None, model: str = "perplexity/sonar-pro") -> list[dict]:
    """
    Гарантированная база WB+Ozon+Маркет + Perplexity с натуральным промптом.
    """
    product_ru = _clean_query(query)
    product_en = _enrich(product_ru)

    # 1. Гарантированная база — всегда в результатах, даже без цен
    results: dict[str, dict] = {
        "Wildberries":    {"store": "Wildberries",    "price": None, "delivery": "бесплатно", "delivery_cost": 0,  "url": _search_url("wildberries.ru",   product_ru, product_en)},
        "Ozon":           {"store": "Ozon",           "price": None, "delivery": "от 99 ₽",   "delivery_cost": 99, "url": _search_url("ozon.ru",          product_ru, product_en)},
        "Яндекс.Маркет": {"store": "Яндекс.Маркет", "price": None, "delivery": "от 99 ₽",   "delivery_cost": 99, "url": _search_url("market.yandex.ru", product_ru, product_en)},
    }

    # 2. Perplexity с натуральным промптом (без жёсткого формата → не возвращает НЕТ)
    try:
        resp = await ai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты помощник по поиску цен в российских интернет-магазинах. "
                        "Ищи товары с доставкой в Химки или Москву. "
                        "Отвечай кратко: для каждого магазина — название и цена в рублях. "
                        "Если в магазине нет или нет в наличии — так и напиши. "
                        "Интересуют: Wildberries, Ozon, Яндекс.Маркет, "
                        "Пятёрочка, Перекрёсток, Лента, Ашан, Metro."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Сколько стоит {product_en} в Wildberries, Ozon и Яндекс.Маркет?",
                },
            ],
            max_tokens=400,
            temperature=0.0,
        )

        text = resp.choices[0].message.content or ""
        prices = _parse_prices(text)

        seen = set(results.keys())
        for name, price in prices.items():
            if name in results:
                # Обновляем цену базового магазина
                results[name]["price"] = price
            elif name not in seen:
                # Добавляем grocery store — только если Perplexity подтвердил цену
                for store_name, pattern, domain, delivery, dcost in _STORE_PATTERNS:
                    if store_name == name:
                        seen.add(name)
                        results[name] = {
                            "store":         name,
                            "price":         price,
                            "delivery":      delivery,
                            "delivery_cost": dcost,
                            "url":           _search_url(domain, product_ru, product_en),
                        }
                        break

    except Exception:
        pass  # Используем базу без цен

    # 3. Сортировка: с ценой (по возрастанию с учётом доставки) → без цены
    def sort_key(r: dict):
        if r["price"] is None:
            return (1, 0)
        return (0, r["price"] + r["delivery_cost"])

    return sorted(results.values(), key=sort_key)


def format_results(query: str, results: list[dict]) -> str:
    product    = _clean_query(query)
    product_en = _enrich(product)

    if not results:
        yandex = f"https://market.yandex.ru/search?text={quote_plus(product_en)}"
        return f"❌ «{product}» — не смог найти.\n\nПопробуй на Яндекс.Маркет:\n{yandex}"

    lines = [f"🛒 {product}\n"]

    priced = [r for r in results if r["price"] is not None]

    for r in results:
        if r["price"] is not None:
            total = r["price"] + r["delivery_cost"]
            if r["delivery_cost"] == 0:
                d_str = f"доставка {r['delivery']}"
            else:
                d_str = f"доставка {r['delivery']}, итого от {total:.0f} ₽"
            lines.append(f"📦 {r['store']} — от {r['price']:.0f} ₽ ({d_str})")
        else:
            lines.append(f"📦 {r['store']} — уточни цену по ссылке ({r['delivery']})")
        lines.append(r["url"])
        lines.append("")

    if priced:
        best       = min(priced, key=lambda r: r["price"] + r["delivery_cost"])
        best_total = best["price"] + best["delivery_cost"]
        lines.append(f"✅ Дешевле всего: {best['store']} — от {best_total:.0f} ₽ с доставкой")

    return "\n".join(lines).rstrip()
