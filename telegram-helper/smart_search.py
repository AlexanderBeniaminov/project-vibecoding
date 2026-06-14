"""
Умный поиск через Perplexity Sonar Pro.
Для коммерческих запросов: авиабилеты, отели, товары с ценами и доставкой.
Сначала проверяет наличие нужных данных → уточняет → ищет → даёт ссылки.
"""
import re
from urllib.parse import quote_plus

# Триггер переключения на Perplexity (коммерческие запросы).
# Используем \b только в начале + [а-яёА-ЯЁ]* в конце — корень слова
# совпадает с любой падежной формой (авиабилет → авиабилеты, отель → отели и т.д.)
COMMERCIAL_RE = re.compile(
    r"\b(?:авиабилет|билет|перелёт|авиа\s|рейс|самолёт|"
    r"отел|гостиниц|забронируй|бронировать|суточн|ночёвк|"
    r"переночева|проживани|где\s+остановить|"
    r"самый\s+дешёв|самая\s+дешёвая|самое\s+дешёвое|дешевл|"
    r"купить|где\s+купить|где\s+дешевле|сколько\s+стоит|цена\s+на|"
    r"стоимость\s+доставк|с\s+доставкой\s+в|доставк[аеу]?\s+в"
    r")[а-яёА-ЯЁ]*",
    re.IGNORECASE
)

# ── Системные промпты ──────────────────────────────────────────────

_FLIGHT_SYSTEM = """Ты поисковый ассистент. Ищешь АВИАБИЛЕТЫ.

Ответ строго в таком формате — не более 3 строк:

✈️ Рейсы [откуда] → [куда], [дата вылета][если есть обратная: " / обратно [дата]"]

Типичные цены в [месяц]: от X до Y руб [туда и обратно / в одну сторону].

Правила:
- Только авиарейсы
- Если есть дата "туда" и "обратно" — цену давай суммарно за оба плеча (туда и обратно)
- Если только одна дата — цена в одну сторону
- НЕ указывай время суток (утро/вечер/до 12:00 и т.п.) — только если пользователь специально спросил
- Максимум 3 строки, без таблиц, без лишних слов
- НЕ пиши "СУЩЕСТВУЮТ", "Рекомендую", "открой ссылку" — ссылка будет добавлена автоматически
- НЕ добавляй [1][2][3]
- Пиши по-русски"""

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

_SHOPPING_SYSTEM = """Ты агент сравнения цен с доступом к интернету. Ищешь АКТУАЛЬНЫЕ ЦЕНЫ ТОЛЬКО в этих 7 магазинах: Wildberries, Ozon, Ашан, Metro Cash & Carry, Лента, Пятёрочка, Перекрёсток.
НЕ ПОКАЗЫВАЙ НИКАКИЕ ДРУГИЕ САЙТЫ.

Ответ — ДВЕ таблицы:

🛒 Оптимальная корзина — каждый товар в самом дешёвом магазине

Товар | Магазин | Цена товара | Доставка | Итого | Ссылка
Кофе Davidoff 250г | Ozon | 320 ₽ | бесплатно | 320 ₽ | https://www.ozon.ru/product/...
ИТОГО | | 320 ₽ | бесплатно | 320 ₽ |

*(если несколько товаров из одного магазина — доставка считается один раз)*

🏪 Всё в одном магазине — Ozon (дешевле всего)

Товар | Цена товара | Доставка | Итого | Ссылка
Кофе Davidoff 250г | 320 ₽ | бесплатно | 320 ₽ | https://www.ozon.ru/product/...
ИТОГО | 320 ₽ | бесплатно | 320 ₽ |

ЖЁСТКИЕ ПРАВИЛА:
- ТОЛЬКО 7 перечисленных магазинов — ни доставка-продуктов.ру, ни Яндекс.Маркет, ни любой другой
- Ссылка — ПОЛНЫЙ URL начиная с https:// на конкретную страницу товара (НЕ просто домен!)
- Если нет точной цены доставки — используй стандартные тарифы: Wildberries бесплатно, Ozon от 99₽ (бесплатно от 2499₽), Ашан 199₽, Metro 299₽, Лента бесплатно от 1500₽, Пятёрочка бесплатно от 500₽, Перекрёсток бесплатно от 700₽
- Только реальные цены с учётом акций и скидок
- Если товар не найден в магазине — не показывай этот магазин
- Доставка из одного магазина считается один раз
- Все суммы в рублях (₽), пиши по-русски"""

# ── Словари ────────────────────────────────────────────────────────

_IATA = {
    # Москва — все падежи
    "москва": "MOW", "москвы": "MOW", "москву": "MOW", "москве": "MOW", "москвой": "MOW",
    "московск": "MOW",
    "шереметьево": "SVO", "домодедово": "DME", "внуково": "VKO",
    # Питер — все падежи
    "санкт-петербург": "LED", "санкт-петербурга": "LED", "санкт-петербурге": "LED",
    "петербург": "LED", "петербурга": "LED", "петербурге": "LED",
    "питер": "LED", "питера": "LED", "питере": "LED",
    # Пермь — все падежи
    "пермь": "PEE", "перми": "PEE", "пермью": "PEE",
    # Казань
    "казань": "KZN", "казани": "KZN",
    # Екатеринбург
    "екатеринбург": "SVX", "екатеринбурга": "SVX", "екатеринбурге": "SVX",
    "екат": "SVX",
    "новосибирск": "OVB", "новосибирска": "OVB", "новосибирске": "OVB",
    "сочи": "AER",
    "краснодар": "KRR", "краснодара": "KRR", "краснодаре": "KRR",
    "ростов-на-дону": "ROV", "ростов": "ROV", "ростова": "ROV", "ростове": "ROV",
    "уфа": "UFA", "уфы": "UFA", "уфу": "UFA", "уфе": "UFA",
    "самара": "KUF", "самары": "KUF", "самару": "KUF", "самаре": "KUF",
    "нижний новгород": "GOJ", "нижнего новгорода": "GOJ", "нижнем новгороде": "GOJ",
    "нижний": "GOJ",
    "красноярск": "KJA", "красноярска": "KJA", "красноярске": "KJA",
    "иркутск": "IKT", "иркутска": "IKT", "иркутске": "IKT",
    "владивосток": "VVO", "владивостока": "VVO", "владивостоке": "VVO",
    "хабаровск": "KHV", "хабаровска": "KHV", "хабаровске": "KHV",
    "тюмень": "TJM", "тюмени": "TJM",
    "челябинск": "CEK", "челябинска": "CEK", "челябинске": "CEK",
    "омск": "OMS", "омска": "OMS", "омске": "OMS",
    "волгоград": "VOG", "волгограда": "VOG", "волгограде": "VOG",
    "астрахань": "ASF", "астрахани": "ASF",
    "мурманск": "MMK", "мурманска": "MMK", "мурманске": "MMK",
    "архангельск": "ARH", "архангельска": "ARH", "архангельске": "ARH",
    "калининград": "KGD", "калининграда": "KGD", "калининграде": "KGD",
    "минеральные воды": "MRV", "минеральных вод": "MRV",
    "анапа": "AAQ", "анапы": "AAQ", "анапе": "AAQ",
    "сыктывкар": "SCW", "сыктывкара": "SCW", "сыктывкаре": "SCW",
    "нижневартовск": "NJC", "нижневартовска": "NJC", "нижневартовске": "NJC",
    "сургут": "SGC", "сургута": "SGC", "сургуте": "SGC",
    # СНГ
    "баку": "GYD",
    "ереван": "EVN", "еревана": "EVN", "ереване": "EVN",
    "тбилиси": "TBS",
    "алматы": "ALA",
    "ташкент": "TAS", "ташкента": "TAS", "ташкенте": "TAS",
    "минск": "MSQ", "минска": "MSQ", "минске": "MSQ",
    "астана": "NQZ", "астаны": "NQZ", "астане": "NQZ",
    "бишкек": "FRU", "бишкека": "FRU", "бишкеке": "FRU",
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


def _find_origin_dest(query: str) -> tuple:
    """
    Определяет откуда (origin) и куда (dest) по предлогам.
    'из/от [город]' → origin, 'в/до/во [город]' → dest.
    Возвращает (origin_code, dest_code) — любой может быть None.
    """
    q = query.lower()
    origin = dest = None
    seen: set[str] = set()

    for city, code in sorted(_IATA.items(), key=lambda x: -len(x[0])):
        pos = q.find(city)
        if pos < 0 or code in seen:
            continue
        seen.add(code)
        # 10 символов перед городом — ищем предлог
        prefix = q[max(0, pos - 10):pos]
        if re.search(r'\b(из|от)\s*$', prefix.rstrip()):
            if origin is None:
                origin = code
        elif re.search(r'\b(в|во|до)\s*$', prefix.rstrip()):
            if dest is None:
                dest = code

    # Если предлоги не нашли — берём все города и назначаем по позиции
    # В русском языке "найди билеты В Пермь из Москвы": Пермь первая → dest
    if origin is None and dest is None:
        cities = _find_cities(query)
        if len(cities) >= 2:
            dest, origin = cities[0], cities[1]
        elif len(cities) == 1:
            dest = cities[0]
    elif origin is None:
        # dest известен, ищем другой город как origin
        for c in _find_cities(query):
            if c != dest:
                origin = c
                break
    elif dest is None:
        for c in _find_cities(query):
            if c != origin:
                dest = c
                break

    # Если origin так и не определён — по умолчанию Москва
    if origin is None and dest is not None:
        origin = "MOW"

    return origin, dest


def _find_dates(text: str) -> list[tuple[str, str]]:
    """
    Находит даты в запросе → [(DDMM, YYYY-MM-DD), ...].
    Понимает диапазоны: 'с 3 по 10 января' → [('0301',...), ('1001',...)].
    """
    month_re = "|".join(_MONTHS.keys())
    results = []
    matched_spans: list[tuple[int, int]] = []

    # Диапазон: "с 3 по 10 января" или "3-10 января"
    for m in re.finditer(
        r"(\d{1,2})\s*(?:по|-)\s*(\d{1,2})\s+(" + month_re + r")",
        text, re.IGNORECASE,
    ):
        month = _MONTHS[m.group(3).lower()]
        d1 = m.group(1).zfill(2)
        d2 = m.group(2).zfill(2)
        results.append((f"{d1}{month}", f"2026-{month}-{d1}"))
        results.append((f"{d2}{month}", f"2026-{month}-{d2}"))
        matched_spans.append(m.span())

    # Одиночная дата: "22 июня" (не перекрывающаяся с диапазоном)
    for m in re.finditer(r"(\d{1,2})\s+(" + month_re + r")", text, re.IGNORECASE):
        if any(s <= m.start() <= e for s, e in matched_spans):
            continue
        month = _MONTHS[m.group(2).lower()]
        day = m.group(1).zfill(2)
        results.append((f"{day}{month}", f"2026-{month}-{day}"))

    return results


def detect_type(text: str) -> str:
    """Тип запроса: 'flights' | 'hotels' | 'products'. Ищет корни слов."""
    q = text.lower()
    if any(w in q for w in ["билет", "рейс", "авиа", "самолёт", "перелёт", "авиабилет"]):
        return "flights"
    if any(w in q for w in ["отел", "гостиниц", "забронир", "суточ", "ночёвк",
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
            return "✈️ Куда летите? (например: «в Баку», «в Пермь»)"
        # Если хотя бы одно направление известно — Москва по умолчанию, не спрашиваем
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
        origin, dest = _find_origin_dest(query)
        dates = _find_dates(query)
        if origin and dest and dates:
            d1 = dates[0][0]
            back = dates[1][0] if len(dates) >= 2 else ""
            links.append({
                "name": "✈️ Авиасейлс",
                "url": f"https://www.aviasales.ru/search/{origin}{d1}{dest}{back}1",
            })
        elif dest and dates:
            d1 = dates[0][0]
            links.append({
                "name": "✈️ Авиасейлс",
                "url": f"https://www.aviasales.ru/search/MOW{d1}{dest}1",
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
        ci_path  = f"?checkin={checkin}&checkout={checkout}" if checkin else ""  # для path-URL
        ci_param = f"&checkin={checkin}&checkout={checkout}" if checkin else ""  # для query-URL
        ci_sutochno = f"/{checkin}/{checkout}" if checkin else ""
        city_slug = city_name.replace(" ", "-") if city_name else ""

        links += [
            {"name": "🏨 Яндекс.Путешествия", "url": f"https://travel.yandex.ru/hotels/{cn}/{ci_path}"},
            {"name": "🏨 Островок",            "url": f"https://ostrovok.ru/hotel/{cn}/{ci_path}"},
            {"name": "🏠 Суточно.ру",          "url": f"https://sutochno.ru/{city_slug}{ci_sutochno}"},
            {"name": "🌐 Booking.com",         "url": f"https://www.booking.com/searchresults.html?ss={cn}{ci_param}"},
        ]

    else:  # products / shopping
        links.append({"name": "📦 Wildberries",    "url": f"https://www.wildberries.ru/catalog/0/search.aspx?search={q_enc}"})
        links.append({"name": "📦 Ozon",           "url": f"https://www.ozon.ru/search/?text={q_enc}"})
        links.append({"name": "🛒 Ашан",           "url": f"https://www.auchan.ru/s/{q_enc}"})
        links.append({"name": "🛒 Metro",          "url": f"https://online.metro-cc.ru/search?query={q_enc}"})
        links.append({"name": "🛒 Лента",          "url": f"https://lenta.com/search/?q={q_enc}"})
        links.append({"name": "🛒 Пятёрочка",     "url": f"https://5ka.ru/search/{q_enc}/"})
        links.append({"name": "🛒 Перекрёсток",   "url": f"https://www.perekrestok.ru/cat/search?search={q_enc}"})

    return links


# ── Основная функция ───────────────────────────────────────────────

async def smart_search_and_answer(
    query: str,
    ai_client,
    search_model: str,
    kind: str | None = None,
) -> tuple:
    """
    Perplexity Sonar Pro → (answer_text, links).
    links — список {'name': ..., 'url': ...} для inline-кнопок в Telegram.
    """
    if kind is None:
        kind = detect_type(query)

    system_prompt = {
        "flights":  _FLIGHT_SYSTEM,
        "hotels":   _HOTEL_SYSTEM,
        "products": _SHOPPING_SYSTEM,
    }.get(kind, _SHOPPING_SYSTEM)

    # Для рейсов: если origin не указан явно — добавляем "из Москвы" в запрос к Perplexity
    user_query = query
    if kind == "flights":
        origin_check, _ = _find_origin_dest(query)
        if origin_check == "MOW" and "москв" not in query.lower() and "шереметьев" not in query.lower():
            user_query = query + " из Москвы"

    try:
        resp = await ai_client.chat.completions.create(
            model=search_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
            max_tokens=1500 if kind == "products" else 600,
            temperature=0.1,
        )
        answer = (resp.choices[0].message.content or "").strip()
        # Убираем цитаты Perplexity [1][2] — они ломают Telegram Markdown
        answer = re.sub(r'\[\d+\]', '', answer).strip()
    except Exception as e:
        answer = f"⚠️ Ошибка поиска: {e}"

    links = build_deep_links(query, kind)

    # Для авиабилетов — Aviasales URL сразу в тексте
    if kind == "flights":
        origin, dest = _find_origin_dest(query)
        dates = _find_dates(query)
        if dest and dates:
            d1 = dates[0][0]
            back = dates[1][0] if len(dates) >= 2 else ""
            avia_url = f"https://www.aviasales.ru/search/{origin}{d1}{dest}{back}1"
            answer += f"\n\n✈️ Открыть на Авиасейлс:\n{avia_url}"

    return answer, links
