"""
Шопинг-агент v4:
- Гарантированная база: WB + Ozon + Яндекс.Маркет всегда показываются (эти URL работают без логина/города)
- 1 вызов Perplexity без site: → ищет по всем источникам (Маркет, price.ru, otzovik и др.)
  Локация: Химки / Москва / Московская область
- Из ответа обновляем цены базы и добавляем grocery stores если Perplexity подтвердил
- Сортировка: с ценой сначала (по возрастанию), без цены — снизу
- Цена всегда «от X ₽» — честно отражает приблизительность данных
"""
import asyncio
import re
from urllib.parse import quote_plus

# Транслитерация: добавляет EN-вариант бренда для лучшего поиска в WB/Ozon
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
    """Поисковый URL магазина. WB/Ozon/Маркет получают EN-вариант."""
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


# Маппинг: как Perplexity называет магазин → наши данные
_STORE_MAP = {
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


async def search_all_stores(query: str, ai_client=None, model: str = "perplexity/sonar-pro") -> list[dict]:
    """
    Гарантированная база WB+Ozon+Маркет всегда в результатах.
    Perplexity (1 вызов, без site:) добавляет цены и grocery stores если подтвердил.
    """
    product_ru = _clean_query(query)
    product_en = _enrich(product_ru)

    # Гарантированная база — эти 3 всегда в списке
    results: dict[str, dict] = {
        "Wildberries":    {"store": "Wildberries",    "price": None, "delivery": "бесплатно",  "delivery_cost": 0,  "url": _search_url("wildberries.ru",   product_ru, product_en)},
        "Ozon":           {"store": "Ozon",           "price": None, "delivery": "от 99 ₽",    "delivery_cost": 99, "url": _search_url("ozon.ru",          product_ru, product_en)},
        "Яндекс.Маркет": {"store": "Яндекс.Маркет", "price": None, "delivery": "от 99 ₽",    "delivery_cost": 99, "url": _search_url("market.yandex.ru", product_ru, product_en)},
    }

    # Perplexity: 1 вызов без site: ограничения, локация — Химки/Москва
    try:
        resp = await ai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Найди актуальные цены на товар в интернет-магазинах "
                        "с доставкой в Химки, Москва или Московская область.\n"
                        "Для каждого магазина где товар ЕСТЬ В НАЛИЧИИ — верни строку:\n"
                        "МАГАЗИН|ЦЕНА\n"
                        "Нас интересуют только: "
                        "Wildberries, Ozon, Яндекс.Маркет, Пятёрочка, Перекрёсток, Лента, Ашан, Metro.\n"
                        "ЦЕНА — минимальная цена в рублях, только число (пример: 705).\n"
                        "Не включай магазины где написано 'Нет в наличии', 'Под заказ' или нет кнопки Купить.\n"
                        "Если нигде не найдено — верни: НЕТ\n"
                        "Только строки МАГАЗИН|ЦЕНА, никаких пояснений."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Где купить с доставкой в Химки или Москву: {product_en}? Укажи цены.",
                },
            ],
            max_tokens=300,
            temperature=0.0,
        )

        text = (resp.choices[0].message.content or "").strip()
        text = re.sub(r"\[\d+\]", "", text).strip()  # убираем сноски вида [1]

        if text and not ("НЕТ" in text.upper() and "|" not in text):
            seen = set(results.keys())  # для дедупликации grocery stores

            for line in text.splitlines():
                line = line.strip()
                if "|" not in line:
                    continue
                parts = line.split("|", 1)
                store_raw = parts[0].strip().lower()
                price_raw = re.sub(r"[^\d]", "", parts[1].strip()) if len(parts) > 1 else ""
                if not price_raw:
                    continue
                try:
                    price = float(price_raw)
                except ValueError:
                    continue
                if price <= 0:
                    continue

                # Найти магазин в маппинге
                matched = None
                for key, info in _STORE_MAP.items():
                    if key in store_raw:
                        matched = info
                        break
                if not matched:
                    continue

                name, domain, delivery, dcost = matched

                if name in results:
                    # Обновляем цену для базовых магазинов (WB/Ozon/Маркет)
                    results[name]["price"] = price
                elif name not in seen:
                    # Добавляем grocery store подтверждённый Perplexity
                    seen.add(name)
                    results[name] = {
                        "store":         name,
                        "price":         price,
                        "delivery":      delivery,
                        "delivery_cost": dcost,
                        "url":           _search_url(domain, product_ru, product_en),
                    }

    except Exception:
        pass  # Используем только базу без цен

    # Сортировка: с ценой (по возрастанию суммы с доставкой) → без цены
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
