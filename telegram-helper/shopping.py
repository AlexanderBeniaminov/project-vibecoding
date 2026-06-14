"""
Шопинг-агент: параллельный поиск цен через Perplexity.
Цену берём из Perplexity (text-only, 30 токенов — быстро).
Ссылку генерируем сами → всегда рабочая страница поиска магазина.
Прямые API магазинов недоступны с VPS (PoW/429/403).
"""
import asyncio
import re
from urllib.parse import quote_plus

STORES = [
    ("Wildberries", "wildberries.ru",   "бесплатно",           0),
    ("Ozon",        "ozon.ru",          "от 99 ₽",            99),
    ("Пятёрочка",  "5ka.ru",           "бесплатно от 500 ₽",  0),
    ("Перекрёсток", "perekrestok.ru",   "бесплатно от 700 ₽",  0),
    ("Лента",       "lenta.com",        "бесплатно от 1500 ₽", 0),
    ("Ашан",        "auchan.ru",        "199 ₽",             199),
    ("Metro",       "metro-cc.ru",      "299 ₽",             299),
]

# Рабочие поисковые URL для каждого домена (генерируем сами — всегда работают)
def _search_url(domain: str, query: str) -> str:
    q = quote_plus(query)
    return {
        "wildberries.ru": f"https://www.wildberries.ru/catalog/0/search.aspx?search={q}",
        "ozon.ru":        f"https://www.ozon.ru/search/?text={q}",
        "5ka.ru":         f"https://5ka.ru/search/?search={q}",
        "perekrestok.ru": f"https://www.perekrestok.ru/cat/search?search={q}",
        "lenta.com":      f"https://lenta.com/search/?q={q}",
        "auchan.ru":      f"https://www.auchan.ru/s/{q}",
        "metro-cc.ru":    f"https://online.metro-cc.ru/search?query={q}",
    }.get(domain, f"https://www.{domain}/search?q={q}")


# Таблица транслитерации брендов: кириллица → латиница
_TRANSLIT = {
    "давыдофф": "davidoff", "давидофф": "davidoff",
    "нескафе":  "nescafe",  "якобс":    "jacobs",
    "лавацца":  "lavazza",  "тефаль":   "tefal",
}

def _enrich(query: str) -> str:
    """Добавляет латинский вариант бренда если найдена кириллическая форма."""
    q_lower = query.lower()
    for ru, en in _TRANSLIT.items():
        if ru in q_lower and en not in q_lower:
            return f"{query} {en}"
    return query


async def _get_price(query: str, domain: str, ai_client, model: str) -> float | None:
    """Запрашивает у Perplexity ТОЛЬКО цену на конкретном домене."""
    enriched = _enrich(query)
    try:
        resp = await ai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Найди актуальную цену товара на {domain}.\n"
                        f"Верни ТОЛЬКО одно число — цену в рублях (например: 705).\n"
                        f"Только если товар ЕСТЬ В НАЛИЧИИ (кнопка 'Купить' активна).\n"
                        f"Если не найдено или нет в наличии — верни: НЕТ"
                    ),
                },
                {
                    "role": "user",
                    "content": f"{enriched} site:{domain} цена в наличии купить",
                },
            ],
            max_tokens=30,
            temperature=0.0,
        )
        text = (resp.choices[0].message.content or "").strip()
        text = re.sub(r'\[\d+\]', '', text).strip()

        if not text or "НЕТ" in text.upper():
            return None

        # Извлекаем число из ответа
        nums = re.findall(r'[\d\s]+[.,]?\d*', text)
        if not nums:
            return None
        price_str = nums[0].replace(" ", "").replace(",", ".")
        price = float(price_str)
        return price if price > 0 else None
    except Exception:
        return None


async def search_all_stores(query: str, ai_client=None, model: str = "perplexity/sonar-pro") -> list[dict]:
    """Параллельный поиск цен во всех 7 магазинах."""
    async def _one(name, domain, delivery, dcost):
        price = await _get_price(query, domain, ai_client, model)
        if price is None:
            return None
        return {
            "store": name,
            "price": price,
            "delivery": delivery,
            "delivery_cost": dcost,
            "url": _search_url(domain, query),  # всегда рабочая ссылка
        }

    tasks = [_one(name, domain, delivery, dcost) for name, domain, delivery, dcost in STORES]
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in raw if isinstance(r, dict)]


def format_results(query: str, results: list[dict]) -> str:
    """Форматирует результаты в текст для Telegram."""
    found = [r for r in results if r.get("price")]

    if not found:
        return (
            f"❌ По запросу «{query}» ничего не найдено в 7 магазинах.\n"
            "Попробуй уточнить название или бренд."
        )

    sorted_res = sorted(found, key=lambda r: r["price"] + r["delivery_cost"])

    lines = [f"🛒 {query}\n"]
    for r in sorted_res:
        total = r["price"] + r["delivery_cost"]
        if r["delivery_cost"] == 0:
            d_str = f"доставка {r['delivery']}"
        else:
            d_str = f"доставка {r['delivery']}, итого {total:.0f} ₽"
        lines.append(f"📦 {r['store']} — {r['price']:.0f} ₽ ({d_str})")
        lines.append(r["url"])
        lines.append("")

    best = sorted_res[0]
    best_total = best["price"] + best["delivery_cost"]
    lines.append(f"✅ Дешевле всего: {best['store']} — {best_total:.0f} ₽ с доставкой")

    return "\n".join(lines)
