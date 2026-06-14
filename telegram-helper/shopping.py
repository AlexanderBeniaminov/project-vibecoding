"""
Шопинг-агент: параллельный поиск цен через Perplexity с site: оператором.
7 одновременных запросов — каждый ищет товар строго на одном домене.
Прямой scraping невозможен: все магазины блокируют VPS-IP (429/403).
"""
import asyncio
import re

STORES = [
    ("Wildberries", "wildberries.ru",   "бесплатно",          0),
    ("Ozon",        "ozon.ru",          "от 99 ₽",           99),
    ("Пятёрочка",  "5ka.ru",           "бесплатно от 500 ₽", 0),
    ("Перекрёсток", "perekrestok.ru",   "бесплатно от 700 ₽", 0),
    ("Лента",       "lenta.com",        "бесплатно от 1500 ₽",0),
    ("Ашан",        "auchan.ru",        "199 ₽",            199),
    ("Metro",       "metro-cc.ru",      "299 ₽",            299),
]


async def _search_one(query: str, store_name: str, domain: str,
                      delivery: str, delivery_cost: int,
                      ai_client, model: str) -> dict | None:
    """Один Perplexity-запрос с site: для конкретного магазина."""
    try:
        resp = await ai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Ищешь товар ТОЛЬКО на сайте {domain}. "
                        f"Верни ОДНУ строку: ЦЕНА|URL\n"
                        f"Пример: 485|https://www.{domain}/catalog/12345/detail.aspx\n"
                        f"Цена — только цифры, без пробелов и символов.\n"
                        f"URL — полная прямая ссылка на конкретный товар на {domain}.\n"
                        f"Если товар не найден или нет в наличии — верни: НЕТ"
                    ),
                },
                {"role": "user", "content": f"{query} site:{domain} купить цена"},
            ],
            max_tokens=120,
            temperature=0.0,
        )
        text = (resp.choices[0].message.content or "").strip()
        text = re.sub(r'\[\d+\]', '', text).strip()  # убираем цитаты Perplexity

        if not text or text.upper().startswith("НЕТ") or "|" not in text:
            return None

        price_str, url = text.split("|", 1)
        url = url.strip()

        # Валидация цены
        price_clean = re.sub(r"[^\d.,]", "", price_str).replace(",", ".")
        if not price_clean:
            return None
        price = float(price_clean)
        if price <= 0:
            return None

        # Валидация URL — должен содержать домен магазина
        if not url.startswith("http") or domain not in url:
            return None

        return {
            "store": store_name,
            "price": price,
            "delivery": delivery,
            "delivery_cost": delivery_cost,
            "url": url,
        }
    except Exception:
        return None


async def search_all_stores(query: str, ai_client=None, model: str = "perplexity/sonar-pro") -> list[dict]:
    """Параллельный поиск во всех 7 магазинах."""
    tasks = [
        _search_one(query, name, domain, delivery, dcost, ai_client, model)
        for name, domain, delivery, dcost in STORES
    ]
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in raw if isinstance(r, dict)]


def format_results(query: str, results: list[dict]) -> str:
    """Форматирует результаты в текст для Telegram. Магазины без цены не показываем."""
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
