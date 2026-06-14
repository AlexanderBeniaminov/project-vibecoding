"""
Шопинг-агент: параллельный поиск цен в 7 магазинах через прямые API.
WB и Пятёрочка — через публичные JSON API (надёжно).
Остальные — через внутренние REST/GraphQL эндпоинты (лучший effort).
"""
import asyncio
import re
import requests
from urllib.parse import quote_plus

_UA = (
    "Mozilla/5.0 (Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HEADS = {
    "User-Agent": _UA,
    "Accept": "application/json",
    "Accept-Language": "ru-RU,ru;q=0.9",
}
_T = 9  # таймаут запроса


# ── Wildberries ───────────────────────────────────────────────────
def _wb(query: str) -> dict | None:
    q = quote_plus(query)
    url = (
        "https://search.wb.ru/exactmatch/ru/common/v5/search"
        f"?appType=1&curr=rub&dest=-1257786&page=1"
        f"&query={q}&resultset=catalog&sort=popular&spp=30"
    )
    r = requests.get(url, headers=_HEADS, timeout=_T)
    products = r.json().get("data", {}).get("products", [])
    if not products:
        return None
    p = products[0]
    price = (p.get("salePriceU") or 0) // 100
    if not price:
        return None
    pid = p.get("id")
    return {
        "store": "Wildberries",
        "name": p.get("name", query)[:70],
        "price": price,
        "delivery": "бесплатно",
        "delivery_cost": 0,
        "url": f"https://www.wildberries.ru/catalog/{pid}/detail.aspx",
    }


# ── Ozon ─────────────────────────────────────────────────────────
def _ozon(query: str) -> dict | None:
    # Ozon не отдаёт данные без авторизованных cookies — сайт на JS
    # Возвращаем поисковую ссылку как fallback
    q = quote_plus(query)
    return {
        "store": "Ozon",
        "name": None,  # нет прямых данных
        "price": None,
        "delivery": "от 99 ₽ (бесплатно от 2499 ₽)",
        "delivery_cost": 99,
        "url": f"https://www.ozon.ru/search/?text={q}&from_global=true",
    }


# ── Пятёрочка ────────────────────────────────────────────────────
def _5ka(query: str) -> dict | None:
    q = quote_plus(query)
    r = requests.get(
        f"https://5ka.ru/api/v2/search/products/?search={q}&records_per_page=5",
        headers=_HEADS, timeout=_T,
    )
    items = r.json().get("results", [])
    if not items:
        return None
    p = items[0]
    prices = p.get("prices") or {}
    price = float(prices.get("price_promo") or prices.get("price_reg") or 0)
    if not price:
        return None
    slug = p.get("url") or ""
    return {
        "store": "Пятёрочка",
        "name": p.get("name", query)[:70],
        "price": price,
        "delivery": "бесплатно от 500 ₽",
        "delivery_cost": 0,
        "url": f"https://5ka.ru{slug}" if slug else f"https://5ka.ru/search/?search={q}",
    }


# ── Перекрёсток ───────────────────────────────────────────────────
def _perekrestok(query: str) -> dict | None:
    q = quote_plus(query)
    r = requests.get(
        f"https://www.perekrestok.ru/api/catalog/v2/search?search={q}&perPage=5",
        headers=_HEADS, timeout=_T,
    )
    data = r.json()
    items = (
        data.get("content", {}).get("products")
        or data.get("items")
        or data.get("products")
        or []
    )
    if not items:
        return None
    p = items[0]
    price = float(
        p.get("pricePurchase")
        or p.get("price")
        or (p.get("priceTag") or {}).get("price")
        or 0
    )
    if not price:
        return None
    slug = p.get("url") or p.get("slug") or ""
    return {
        "store": "Перекрёсток",
        "name": (p.get("name") or p.get("title") or query)[:70],
        "price": price,
        "delivery": "бесплатно от 700 ₽",
        "delivery_cost": 0,
        "url": f"https://www.perekrestok.ru{slug}" if slug else f"https://www.perekrestok.ru/cat/search?search={q}",
    }


# ── Лента ─────────────────────────────────────────────────────────
def _lenta(query: str) -> dict | None:
    q = quote_plus(query)
    r = requests.get(
        f"https://lenta.com/api/v1/catalog/goods?q={q}&limit=5",
        headers=_HEADS, timeout=_T,
    )
    data = r.json()
    items = data.get("items") or (data.get("data") or {}).get("items") or []
    if not items:
        return None
    p = items[0]
    price = float(p.get("currentPrice") or p.get("price") or 0)
    if not price:
        return None
    slug = p.get("url") or p.get("slug") or ""
    return {
        "store": "Лента",
        "name": (p.get("name") or p.get("title") or query)[:70],
        "price": price,
        "delivery": "бесплатно от 1500 ₽",
        "delivery_cost": 0,
        "url": f"https://lenta.com{slug}" if slug else f"https://lenta.com/search/?q={q}",
    }


# ── Ашан ─────────────────────────────────────────────────────────
def _auchan(query: str) -> dict | None:
    q = quote_plus(query)
    r = requests.get(
        f"https://www.auchan.ru/v1/api/products?search={q}&limit=5",
        headers=_HEADS, timeout=_T,
    )
    data = r.json()
    items = data.get("results") or data.get("products") or data.get("items") or []
    if not items:
        return None
    p = items[0]
    price = float(p.get("price") or p.get("currentPrice") or 0)
    if not price:
        return None
    slug = p.get("url") or ""
    return {
        "store": "Ашан",
        "name": (p.get("name") or p.get("title") or query)[:70],
        "price": price,
        "delivery": "199 ₽",
        "delivery_cost": 199,
        "url": f"https://www.auchan.ru{slug}" if slug else f"https://www.auchan.ru/s/{q}",
    }


# ── Metro ─────────────────────────────────────────────────────────
def _metro(query: str) -> dict | None:
    r = requests.post(
        "https://api.metro-cc.ru/products-api/graph",
        json={
            "query": (
                "query Search($query: String!, $limit: Int) {"
                "  search(query: $query, limit: $limit) {"
                "    products { id name url stocks { price sale_price } }"
                "  }"
                "}"
            ),
            "variables": {"query": query, "limit": 3},
        },
        headers={**_HEADS, "Content-Type": "application/json"},
        timeout=_T,
    )
    products = r.json().get("data", {}).get("search", {}).get("products") or []
    if not products:
        return None
    p = products[0]
    stocks = p.get("stocks") or [{}]
    price = float(stocks[0].get("sale_price") or stocks[0].get("price") or 0)
    if not price:
        return None
    url = p.get("url") or ""
    return {
        "store": "Metro",
        "name": (p.get("name") or query)[:70],
        "price": price,
        "delivery": "299 ₽",
        "delivery_cost": 299,
        "url": url if url.startswith("http") else f"https://online.metro-cc.ru{url}",
    }


# ── Оркестратор ───────────────────────────────────────────────────

_STORE_FNS = [_wb, _ozon, _5ka, _perekrestok, _lenta, _auchan, _metro]


async def search_all_stores(query: str) -> list[dict]:
    """Параллельный поиск по всем 7 магазинам."""
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, fn, query) for fn in _STORE_FNS]
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    results = []
    for r in raw:
        if isinstance(r, dict):
            results.append(r)
        # исключения и None просто пропускаем
    return results


# ── Форматирование ────────────────────────────────────────────────

def format_results(query: str, results: list[dict]) -> str:
    """Форматирует результаты в текст для Telegram."""
    # Разделяем: у кого есть реальная цена, у кого только ссылка (fallback)
    with_price = [r for r in results if r.get("price")]
    links_only = [r for r in results if not r.get("price")]

    if not with_price and not links_only:
        return (
            f"❌ По запросу «{query}» ничего не найдено.\n"
            "Попробуй уточнить название товара или бренд."
        )

    lines = [f"🛒 {query}\n"]

    if with_price:
        sorted_res = sorted(with_price, key=lambda r: r["price"] + r["delivery_cost"])
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

    if links_only:
        lines.append("")
        lines.append("🔍 Проверь вручную (цены не удалось получить):")
        for r in links_only:
            lines.append(f"  {r['store']}: {r['url']}")

    return "\n".join(lines)
