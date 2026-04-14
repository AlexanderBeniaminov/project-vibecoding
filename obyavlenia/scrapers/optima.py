"""
Парсер Оптима Инвест.
https://optima-invest.ru/obekty/137/
Карточки: div.card-item > a[href]
"""
import re
from bs4 import BeautifulSoup
from loguru import logger

from scrapers.base_scraper import BaseScraper
from utils.text_parser import (
    extract_area, extract_price, extract_profit, extract_payback,
    detect_location_type, detect_seller_type,
)
from utils.filters import should_include

BASE_URL = "https://optima-invest.ru"
START_URL = "https://optima-invest.ru/obekty/137/"


class OptimaScraper(BaseScraper):
    source_name = "Оптима Инвест"

    def scrape(self) -> list[dict]:
        results = []
        page = 1
        seen_ids: set[str] = set()

        while True:
            url = START_URL if page == 1 else f"{START_URL}?page={page}&SECTION_CODE=137"
            resp = self.get(url)
            if not resp:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select(".card-item")

            if not cards:
                break

            for card in cards:
                try:
                    item = self._parse_card(card)
                    if item and item["id"] not in seen_ids:
                        seen_ids.add(item["id"])
                        results.append(item)
                except Exception as e:
                    logger.warning("[Оптима] Ошибка парсинга карточки: {}", e)

            # Оптима не имеет явной пагинации — проверяем количество карточек
            if len(cards) < 12:
                break
            page += 1
            if page > 30:
                break

        logger.info("[Оптима] Найдено {} объявлений", len(results))
        return results

    def _parse_card(self, card) -> dict | None:
        link_tag = card.select_one("a[href]")
        if not link_tag:
            return None

        href = link_tag.get("href", "")
        url = href if href.startswith("http") else BASE_URL + href

        # ID из slug
        slug = href.strip("/").split("/")[-1]
        listing_id = slug if slug else ""
        if not listing_id:
            return None

        # Заголовок
        title_tag = card.select_one(".card-item__article")
        title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
        # Убираем префикс "Бизнес в продаже:"
        title = re.sub(r"^Бизнес в продаже:\s*", "", title)

        # Город и прибыль из параграфов
        paras = card.select("p.text")
        city = paras[0].get_text(strip=True) if paras else "не указан"
        profit_text = paras[1].get_text(strip=True) if len(paras) > 1 else ""

        full_text = f"{title} {profit_text}"
        area = extract_area(full_text)
        price = extract_price(full_text)
        profit = extract_profit(profit_text or full_text)

        include, priority_flag, area_unknown = should_include(title, full_text, area)
        if not include:
            return None

        return {
            "id": listing_id,
            "source": self.source_name,
            "url": url,
            "title": title,
            "city": city,
            "area_m2": area,
            "price_rub": price,
            "profit_month": profit,
            "payback_months": extract_payback(full_text),
            "location_type": detect_location_type(full_text),
            "seller_type": detect_seller_type(full_text),
            "published_at": None,
            "priority_flag": int(priority_flag),
            "area_unknown_flag": int(area_unknown),
        }
