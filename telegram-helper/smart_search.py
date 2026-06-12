"""
Умный поиск через Perplexity Sonar Pro.
Для коммерческих запросов: авиабилеты, отели, товары с ценами и доставкой.
Сначала проверяет наличие нужных данных → уточняет → ищет → даёт ссылки.
"""
import re
from urllib.parse import quote_plus

# Триггер переключения на Perplexity (коммерческие запросы)
COMMERCIAL_RE = re.compile(
    r"\b(билет[аеийыов]?|перелёт[аов]?|авиабилет|авиа\s|рейс[аов]?|самолёт|"
    r"отел[ьяей]|гостиниц[аеы]|забронируй|бронировать|суточн|ночёвк[аеи]|"
    r"переночева|проживани[еья]|где\s+остановить|"
    r"самый\s+дешёв|самая\s+дешёвая|самое\s+дешёвое|дешевл?е\s+(всего|купить)|"
    r"стоимость\s+доставк|с\s+доставкой\s+в|доставк[аеу]\s+в\s+"
    r")\b",
    re.IGNORECASE
)

# ── Системные промпты ──────────────────────────────────────────────

_FLIGHT_SYSTEM = """Ты поисковый ассистент с доступом к интернету. Ищешь АВИАБИЛЕТЫ — не театральные, не концертные.

Ответ строго в таком формате:

**✈️ Рейсы {откуда} → {куда}, {дата}**

| Авиакомпания | Рейс | Вылет | Прилёт | Цена (эконом) |
|---|---|---|---|---|
| Победа | DP6511 | 07:15 | 10:20 | от 3 200 ₽ |

Правила:
- Показывай ТОЛЬКО авиарейсы, не поезда и не мероприятия
- Если указано время суток (утро/первая половина дня → до 12:00; вечер → после 18:00) — фильтруй соответственно
- Если конкретных рейсов с ценами нет — честно скажи об этом и дай типичный диапазон цен по историческим данным
- Источники: Авиасейлс, Яндекс.Путешествия, официальные сайты авиакомпаний
- Пиши на русском"""

_HOTEL_SYSTEM = """Ты поисковый ассистент с доступом к интернету. Ищешь ОТЕЛИ.

Ответ строго в таком формате:

**🏨 Отели в {город}, {даты}**

| Отель | Район | Цена/ночь | Рейтинг | Источник |
|---|---|---|---|---|
| ... | ... | ... ₽ | ⭐ 8.5 | Яндекс.Путешествия |

Правила:
- 3-5 вариантов от дешевле к дороже
- Цены в рублях за ночь
- Источники: Яндекс.Путешествия, Островок, Суточно.ру, Booking.com
- Пиши на русском"""

_PRODUCT_SYSTEM = """Ты поисковый ассистент с доступом к интернету. Сравниваешь ЦЕНЫ на товар.

Ответ строго в таком формате:

**🛒 Топ-5 предложений: {товар}**

| # | Магазин | Цена | Доставка | Итого | Ссылка |
|---|---|---|---|---|---|
| 1 | Озон | 89 ₽ | бесплатно | 89 ₽ | [открыть](https://ozon.ru/...) |
| 2 | Пятёрочка | 95 ₽ | 149 ₽ | 244 ₽ | [открыть](https://5ka.ru/...) |

Правила:
- Сортируй от ДЕШЕВЛЕ к ДОРОЖЕ по итоговой цене (товар + доставка)
- В колонке Ссылка — ПРЯМАЯ ссылка на страницу конкретного товара (не на главную магазина)
- Учитывай доставку в указанный город (или Москву по умолчанию)
- Пиши на русском"""

# ── Словари ────────────────────────────────────────────────────────

_IATA = {
    "москва": "MOW", "московские": "MOW",
    "шереметьево": "SVO", "домодедово": "DME", "внуково": "VKO",
    "санкт-петербург": "LED", "питер": "LED", "петербург": "LED",
    "пермь": "PEE",
    "казань": "KZN",
    "екатеринбург": "SVX",
    "новосибирск": "OVB",
    "сочи": "AER",
    "краснодар": "KRR",
    "ростов-на-дону": "ROV", "ростов": "ROV",
    "уфа": "UFA",
    "самара": "KUF",
    "нижний новгород": "GOJ", "нижний": "GOJ",
    "красноярск": "KJA",
    "иркутск": "IKT",
    "владивосток": "VVO",
    "хабаровск": "KHV",
    "тюмень": "TJM",
    "челябинск": "CEK",
    "омск": "OMS",
    "волгоград": "VOG",
    "астрахань": "ASF",
    "мурманск": "MMK",
    "архангельск": "ARH",
    "калининград": "KGD",
    "минеральные воды": "MRV",
    "анапа": "AAQ",
    "сыктывкар": "SCW",
    "нижневартовск": "NJC",
    "сургут": "SGC",
    # СНГ
    "баку": "GYD",
    "ереван": "EVN",
    "тбилиси": "TBS",
    "алматы": "ALA",
    "ташкент": "TAS",
    "минск": "MSQ",
    "астана": "NQZ",
    "бишкек": "FRU",
    "душанбе": "DYU",
}

_MONTHS = {
    "января": "01", "февраля": "02", "марта": "03", "апреля": "04",
    "мая": "05", "июня": "06", "июля": "07", "августа": "08",
    "сентября": "09", "октября": "10", "ноября": "11", "декабря": "12",
}

_FOOD_KW = [
    "молоко", "хлеб", "сыр", "масло", "кефир", "йогурт", "мясо", "рыба",
    "овощи", "фрукты", "продукт", "напиток", "сок", "вода", "пиво",
    "вино", "колбас", "творог", "ряженка", "parmalat", "пармалат", "пармолат",
    "яйц", "курица", "гречка", "рис", "макарон",
]


# ── Вспомогательные функции ────────────────────────────────────────

def _find_cities(text: str) -> list[str]:
    """IATA-коды городов из текста, в порядке появления."""
    q = text.lower()
    hits: list[tuple[int, str]] = []
    seen: set[str] = set()
    for city, code in sorted(_IATA.items(), key=lambda x: -len(x[0])):
        if city in q and code not in seen:
            hits.append((q.find(city), code))
            seen.add(code)
    hits.sort()
    return [c for _, c in hits]


def _find_dates(text: str) -> list[tuple[str, str]]:
    """Все даты вида '22 июня' → [(DDMM, YYYY-MM-DD), ...]."""
    pat = re.compile(
        r"(\d{1,2})\s+(" + "|".join(_MONTHS.keys()) + r")",
        re.IGNORECASE,
    )
    results = []
    for m in pat.finditer(text):
        day = m.group(1).zfill(2)
        month = _MONTHS[m.group(2).lower()]
        results.append((f"{day}{month}", f"2026-{month}-{day}"))
    return results


def detect_type(text: str) -> str:
    """Тип запроса: 'flights' | 'hotels' | 'products'."""
    q = text.lower()
    if any(w in q for w in ["билет", "рейс", "авиа", "самолёт", "перелёт", "авиабилет"]):
        return "flights"
    if any(w in q for w in ["отель", "гостиниц", "забронир", "суточ", "ночёвк",
                             "переночев", "проживан", "где остановить"]):
        return "hotels"
    return "products"


def get_clarification(query: str, kind: str) -> str | None:
    """
    Если для поиска не хватает ключевых данных — возвращает уточняющий вопрос.
    Иначе возвращает None (можно искать сразу).
    """
    cities = _find_cities(query)
    dates = _find_dates(query)

    if kind == "flights":
        if len(cities) == 0:
            return "✈️ Куда летите? И откуда? (например: «из Москвы в Пермь»)"
        if len(cities) == 1:
            # Есть только один город — непонятно откуда или куда
            # Проверяем контекст: если есть "в [город]" — откуда не указано
            return f"✈️ Откуда вылетаете? (Москва, Шереметьево, другой город)"
        # Есть оба города — дата опциональна, можно искать
        return None

    if kind == "hotels":
        if len(cities) == 0:
            return "🏨 В каком городе ищем отель?"
        # Даты желательны, но не блокируют поиск
        return None

    # products — достаточно самого запроса
    return None


# ── Генерация ссылок ───────────────────────────────────────────────

def build_deep_links(query: str, kind: str | None = None) -> list[dict]:
    """Прямые ссылки по типу запроса."""
    if kind is None:
        kind = detect_type(query)
    q_enc = quote_plus(query)
    links: list[dict] = []

    if kind == "flights":
        cities = _find_cities(query)
        dates = _find_dates(query)
        if len(cities) >= 2 and dates:
            o, d = cities[0], cities[1]
            d1 = dates[0][0]
            back = dates[1][0] if len(dates) >= 2 else ""
            links.append({
                "name": "✈️ Авиасейлс",
                "url": f"https://www.aviasales.ru/search/{o}{d1}{d}{back}1",
            })
        else:
            links.append({"name": "✈️ Авиасейлс", "url": "https://www.aviasales.ru"})
        links.append({"name": "🚂 Яндекс.Путешествия", "url": "https://travel.yandex.ru/avia/"})

    elif kind == "hotels":
        q_l = query.lower()
        city_name = next(
            (c for c in sorted(_IATA, key=lambda x: -len(x)) if c in q_l and len(c) > 3),
            None,
        )
        m_range = re.search(
            r"с\s+(\d{1,2})\s+(" + "|".join(_MONTHS.keys()) + r")\s+(?:по|до)\s+(\d{1,2})\s+(" + "|".join(_MONTHS.keys()) + r")",
            query, re.IGNORECASE,
        )
        checkin = checkout = ""
        if m_range:
            d1 = m_range.group(1).zfill(2)
            m1 = _MONTHS[m_range.group(2).lower()]
            d2 = m_range.group(3).zfill(2)
            m2 = _MONTHS[m_range.group(4).lower()]
            checkin = f"2026-{m1}-{d1}"
            checkout = f"2026-{m2}-{d2}"

        cn = quote_plus(city_name or "")
        ci = f"&checkin={checkin}&checkout={checkout}" if checkin else ""
        ci_sutochno = f"/{checkin}/{checkout}" if checkin else ""
        city_slug = city_name.replace(" ", "-") if city_name else ""

        links += [
            {"name": "🏨 Яндекс.Путешествия", "url": f"https://travel.yandex.ru/hotels/{cn}/{ci}"},
            {"name": "🏨 Островок",            "url": f"https://ostrovok.ru/hotel/{cn}/{ci}"},
            {"name": "🏠 Суточно.ру",          "url": f"https://sutochno.ru/{city_slug}{ci_sutochno}"},
            {"name": "🌐 Booking.com",         "url": f"https://www.booking.com/searchresults.html?ss={cn}{ci}"},
        ]

    else:  # products
        is_food = any(w in query.lower() for w in _FOOD_KW)
        links.append({"name": "📊 Viberis",         "url": f"https://www.viberis.ru/search/?q={q_enc}"})
        links.append({"name": "🛒 Яндекс.Маркет",  "url": f"https://market.yandex.ru/search?text={q_enc}"})
        links.append({"name": "📦 Ozon",            "url": f"https://www.ozon.ru/search/?text={q_enc}"})
        if is_food:
            links.append({"name": "🛒 Перекрёсток", "url": f"https://www.perekrestok.ru/cat/search?search={q_enc}"})
            links.append({"name": "🛒 Лента",        "url": f"https://lenta.com/search/?q={q_enc}"})
            links.append({"name": "🛒 Ашан",         "url": f"https://www.auchan.ru/s/{q_enc}"})
            links.append({"name": "🛒 Пятёрочка",   "url": f"https://5ka.ru/search/{q_enc}/"})
        else:
            links.append({"name": "📦 Wildberries",     "url": f"https://www.wildberries.ru/catalog/0/search.aspx?search={q_enc}"})
            links.append({"name": "🛒 СберМегаМаркет", "url": f"https://megamarket.ru/search/?q={q_enc}"})

    return links


# ── Основная функция ───────────────────────────────────────────────

async def smart_search_and_answer(
    query: str,
    ai_client,
    search_model: str,
    kind: str | None = None,
) -> str:
    """Perplexity Sonar Pro → структурированный ответ + прямые ссылки."""
    if kind is None:
        kind = detect_type(query)

    system_prompt = {
        "flights": _FLIGHT_SYSTEM,
        "hotels":  _HOTEL_SYSTEM,
        "products": _PRODUCT_SYSTEM,
    }.get(kind, _PRODUCT_SYSTEM)

    try:
        resp = await ai_client.chat.completions.create(
            model=search_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            max_tokens=1500,
            temperature=0.1,
        )
        answer = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        answer = f"⚠️ Ошибка поиска: {e}"

    links = build_deep_links(query, kind)
    if links:
        link_lines = ["", "🔗 *Проверить напрямую:*"]
        for lnk in links:
            link_lines.append(f"[{lnk['name']}]({lnk['url']})")
        answer += "\n" + "\n".join(link_lines)

    return answer
