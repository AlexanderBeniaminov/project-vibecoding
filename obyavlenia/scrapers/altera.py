"""
Парсер Альтера Инвест.
https://alterainvest.ru/rus/products/275/
Карточки: .al-catalog .row .col-4 .al-cart-min
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

BASE_URL = "https://alterainvest.ru"
START_URL = "https://alterainvest.ru/rus/products/275/"


class AlteraScraper(BaseScraper):
    source_name = "Альтера Инвест"

    def scrape(self) -> list[dict]:
        results = []
        page = 1
        seen_ids: set[str] = set()

        while True:
            url = START_URL if page == 1 else f"{START_URL}?page={page}"
            resp = self.get(url)
            if not resp:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select(".al-cart-min")

            if not cards:
                logger.debug("[Альтера] Нет карточек на странице {}", page)
                break

            for card in cards:
                try:
                    item = self._parse_card(card)
                    if item and item["id"] not in seen_ids:
                        seen_ids.add(item["id"])
                        results.append(item)
                except Exception as e:
                    logger.warning("[Альтера] Ошибка парсинга карточки: {}", e)

            next_link = soup.select_one(".al-pagination a[data-page]")
            if not next_link:
                break
            page += 1
            if page > 30:
                break

        logger.info("[Альтера] Найдено {} объявлений", len(results))
        return results

    def _parse_card(self, card) -> dict | None:
        # Ссылка и заголовок
        link_tag = card.select_one("a[href*='/detail/']")
        if not link_tag:
            return None

        title = link_tag.get("title") or link_tag.get_text(strip=True)
        href = link_tag.get("href", "")
        url = href if href.startswith("http") else BASE_URL + href

        m = re.search(r"/(\d+)/?$", href)
        listing_id = m.group(1) if m else ""
        if not listing_id:
            return None

        # Цена
        price_tag = card.select_one(".heading6, .al-cart-min__price")
        price_text = price_tag.get_text(strip=True) if price_tag else ""

        # Город
        city_tag = card.select_one("span.caption")
        city = city_tag.get_text(strip=True) if city_tag else "не указан"

        full_text = f"{title} {price_text}"
        area = extract_area(full_text)
        price = extract_price(price_text)

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
            "profit_month": extract_profit(full_text),
            "payback_months": extract_payback(full_text),
            "location_type": detect_location_type(full_text),
            "seller_type": detect_seller_type(full_text),
            "published_at": None,
            "priority_flag": int(priority_flag),
            "area_unknown_flag": int(area_unknown),
        }
