"""
Умный поиск через Perplexity Sonar Pro.
Для коммерческих запросов: авиабилеты, отели, товары с ценами и доставкой.
"""
import re
from urllib.parse import quote_plus

# Коммерческие запросы — триггер переключения на Perplexity
COMMERCIAL_RE = re.compile(
    r"\b(билет[аеийыов]?|перелёт[аов]?|авиабилет|авиа\s|рейс[аов]?|самолёт|"
    r"отел[ьяей]|гостиниц[аеы]|забронируй|бронировать|суточн|ночёвк[аеи]|"
    r"переночева|проживани[еья]|где\s+остановить|"
    r"самый\s+дешёв|самая\s+дешёвая|самое\s+дешёвое|дешевл?е\s+(всего|купить)|"
    r"стоимость\s+доставк|с\s+доставкой\s+в|доставк[аеу]\s+в\s+"
    r")\b",
    re.IGNORECASE
)

# Системный промпт для Perplexity Sonar Pro
_SEARCH_SYSTEM = """Ты поисковый ассистент с доступом к актуальному интернету. Ищи РЕАЛЬНЫЕ данные.

Для авиабилетов: найди 3-5 вариантов рейсов с точным временем вылета/прилёта, авиакомпанией, ценой в рублях. Отдельно прямые рейсы и с пересадками.
Для отелей: найди 3-5 вариантов с ценой за ночь в рублях, рейтингом, расположением (район/удалённость от центра). Источники: Яндекс.Путешествия, Островок, Суточно.ру, Booking.com.
Для продуктов и товаров: сравни цены в магазинах и маркетплейсах (Озон, Вайлдберрис, Яндекс.Маркет). Для продуктов питания — также Перекрёсток, Лента, Ашан, Пятёрочка. Учти стоимость доставки в указанный город.

Отвечай по-русски, структурированно, кратко. Для каждого варианта — источник."""

# IATA коды городов
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


def _find_cities(text: str) -> list[str]:
    """Возвращает IATA-коды городов из текста в порядке появления."""
    q = text.lower()
    hits = []
    seen: set[str] = set()
    for city, code in sorted(_IATA.items(), key=lambda x: -len(x[0])):
        if city in q and code not in seen:
            hits.append((q.find(city), code))
            seen.add(code)
    hits.sort()
    return [c for _, c in hits]


def _find_dates(text: str) -> list[tuple[str, str]]:
    """Ищет все даты вида '22 июня' → [(DDMM, YYYY-MM-DD), ...]."""
    pattern = re.compile(
        r"(\d{1,2})\s+(" + "|".join(_MONTHS.keys()) + r")",
        re.IGNORECASE
    )
    results = []
    for m in pattern.finditer(text):
        day = m.group(1).zfill(2)
        month = _MONTHS[m.group(2).lower()]
        results.append((f"{day}{month}", f"2026-{month}-{day}"))
    return results


def _detect_type(text: str) -> str:
    """Тип запроса: flights | hotels | products."""
    q = text.lower()
    if any(w in q for w in ["билет", "рейс", "авиа", "самолёт", "перелёт", "авиабилет"]):
        return "flights"
    if any(w in q for w in ["отель", "гостиниц", "забронир", "суточ", "ночёвк", "переночев", "проживан", "где остановить"]):
        return "hotels"
    return "products"


def _is_food(text: str) -> bool:
    kw = ["молоко", "хлеб", "сыр", "масло", "кефир", "йогурт", "мясо", "рыба",
          "овощи", "фрукты", "продукт", "напиток", "сок", "вода", "пиво",
          "вино", "колбас", "творог", "ряженка", "parmалат", "parmalat"]
    q = text.lower()
    return any(w in q for w in kw)


def build_deep_links(query: str) -> list[dict]:
    """Генерирует прямые ссылки для ручной проверки по типу запроса."""
    kind = _detect_type(query)
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
            None
        )
        # Даты "с X по Y"
        m_range = re.search(
            r"с\s+(\d{1,2})\s+(" + "|".join(_MONTHS.keys()) + r")\s+(?:по|до)\s+(\d{1,2})\s+(" + "|".join(_MONTHS.keys()) + r")",
            query, re.IGNORECASE
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
        is_food = _is_food(query)
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


async def smart_search_and_answer(query: str, ai_client, search_model: str) -> str:
    """Отправляет запрос в Perplexity Sonar Pro, добавляет прямые ссылки."""
    try:
        resp = await ai_client.chat.completions.create(
            model=search_model,
            messages=[
                {"role": "system", "content": _SEARCH_SYSTEM},
                {"role": "user", "content": query},
            ],
            max_tokens=1200,
            temperature=0.2,
        )
        answer = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        answer = f"⚠️ Ошибка поиска: {e}"

    links = build_deep_links(query)
    if links:
        link_lines = ["", "🔗 *Проверить напрямую:*"]
        for lnk in links:
            link_lines.append(f"[{lnk['name']}]({lnk['url']})")
        answer += "\n" + "\n".join(link_lines)

    return answer
