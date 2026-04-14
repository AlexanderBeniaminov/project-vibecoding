"""
Парсер Biz-nes.ru — категория «Развлечения для детей».
https://biz-nes.ru/business/razvlecheniya/
Карточки: div.business-card с data-атрибутами
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

BASE_URL = "https://biz-nes.ru"
CATEGORY_URLS = [
    "https://biz-nes.ru/business/razvlecheniya/",
    "https://biz-nes.ru/business/razvlecheniya/razvlechenija-dlja-detej/",
    "https://biz-nes.ru/business/razvlecheniya/sport-i-otdyh/",
    "https://biz-nes.ru/business/razvlecheniya/dosug-i-tvorchestvo/",
]


class BiznesScraper(BaseScraper):
    source_name = "Biz-nes.ru"

    def scrape(self) -> list[dict]:
        results = []
        seen_ids: set[str] = set()

        for cat_url in CATEGORY_URLS:
            resp = self.get(cat_url)
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select(".business-card")

            for card in cards:
                try:
                    item = self._parse_card(card)
                    if item and item["id"] not in seen_ids:
                        seen_ids.add(item["id"])
                        results.append(item)
                except Exception as e:
                    logger.warning("[Biz-nes] Ошибка: {}", e)

        logger.info("[Biz-nes] Найдено {} объявлений", len(results))
        return results

    def _parse_card(self, card) -> dict | None:
        # ID из data-атрибута
        listing_id = card.get("data-id", "")
        if not listing_id:
            return None

        # Ссылка и заголовок
        link_tag = card.select_one(".business-card-content a[href]")
        if not link_tag:
            return None
        href = link_tag.get("href", "")
        url = href if href.startswith("http") else BASE_URL + href
        title = link_tag.get_text(strip=True)
        if not title:
            return None

        # Данные из data-атрибутов
        city = card.get("data-city", "не указан")
        price = float(card.get("data-cost", 0) or 0) or None
        profit = float(card.get("data-profit", 0) or 0) or None
        payback = float(card.get("data-payback", 0) or 0) or None
        pub_date = card.get("data-date")

        full_text = card.get_text(" ", strip=True)
        area = extract_area(full_text)

        include, priority_flag, area_unknown = should_include(title, full_text, area)
        if not include:
            return None

        return {
            "id": str(listing_id),
            "source": self.source_name,
            "url": url,
            "title": title,
            "city": city,
            "area_m2": area,
            "price_rub": price,
            "profit_month": profit,
            "payback_months": payback,
            "location_type": detect_location_type(full_text),
            "seller_type": detect_seller_type(full_text),
            "published_at": pub_date,
            "priority_flag": int(priority_flag),
            "area_unknown_flag": int(area_unknown),
        }
