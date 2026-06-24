"""Веб-поиск трендов ниши для Режима 0 (бот сам предлагает темы).
Паттерн идентичен telegram-assistant/tools/web.py.
"""
from ddgs import DDGS

# region=ru-ru важен: без него "HoReCa" возвращает голландские результаты
QUERIES = [
    "искусственный интеллект ресторанный бизнес автоматизация",
    "ИИ в развлекательной индустрии тренды",
    "нейросети управление бизнесом 2026",
    "горнолыжные курорты туризм Россия новости",
]


def search_niche_trends(max_results_per_query: int = 3) -> str:
    """Собирает свежие заголовки по нескольким запросам ниши.
    При сбое поиска возвращает пустую строку — вызывающий код должен
    сгенерировать идеи без контекста новостей и сообщить об этом пользователю."""
    parts = []
    for query in QUERIES:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results_per_query, region="ru-ru"))
            for r in results:
                parts.append(f"{r['title']}: {r['body']}")
        except Exception:
            continue  # один неудачный запрос не должен ронять остальные
    return "\n".join(parts)
