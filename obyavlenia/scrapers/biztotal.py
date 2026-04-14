"""
Парсер BizTotal — категория «Досуг и развлечения».
https://www.biztotal.ru/prodazha_biznesa/dosug-i-razvlecenia.html
Карточки: div.col-md-3 с ссылкой itemprop=url
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

BASE_URL = "https://www.biztotal.ru"
CATEGORY_URL = "https://www.biztotal.ru/prodazha_biznesa/dosug-i-razvlecenia.html"


class BiztotalScraper(BaseScraper):
    source_name = "BizTotal"

    def scrape(self) -> list[dict]:
        results = []
        seen_ids: set[str] = set()
        page = 1

        while True:
            url = CATEGORY_URL if page == 1 else f"{CATEGORY_URL}?page={page}"
            resp = self.get(url)
            if not resp:
                break

            soup = BeautifulSoup(resp.text, "lxml")

            # Карточки: col-md-3 содержащие ссылку с itemprop=url на объявление
            cols = soup.select(".col-md-3")
            cards = [c for c in cols if c.find("a", itemprop="url")]

            if not cards:
                break

            for card in cards:
                try:
                    item = self._parse_card(card)
                    if item and item["id"] not in seen_ids:
                        seen_ids.add(item["id"])
                        results.append(item)
                except Exception as e:
                    logger.warning("[BizTotal] Ошибка: {}", e)

            # Пагинация
            next_link = soup.select_one("a[rel='next'], .pagination a.next")
            if not next_link:
                break
            page += 1
            if page > 20:
                break

        logger.info("[BizTotal] Найдено {} объявлений", len(results))
        return results

    def _parse_card(self, card) -> dict | None:
        link_tag = card.find("a", itemprop="url")
        if not link_tag:
            return None

        href = link_tag.get("href", "")
        url = href if href.startswith("http") else BASE_URL + href

        # Заголовок из title атрибута ссылки
        title = link_tag.get("title", "").strip()
        if not title:
            title = link_tag.get_text(strip=True)

        # ID из slug в конце URL
        m = re.search(r"[_/](\d+)(?:\.html)?/?$", href)
        listing_id = m.group(1) if m else re.sub(r"[^a-zA-Z0-9]", "_", href.rstrip("/"))[-40:]

        if not listing_id or not title:
            return None

        # Дата публикации
        date_tag = card.select_one("b")
        pub_date = date_tag.get_text(strip=True) if date_tag else None

        full_text = title
        area = extract_area(full_text)
        price = extract_price(full_text)

        include, priority_flag, area_unknown = should_include(title, full_text, area)
        if not include:
            return None

        city = self._extract_city(full_text)

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
            "published_at": pub_date,
            "priority_flag": int(priority_flag),
            "area_unknown_flag": int(area_unknown),
        }

    @staticmethod
    def _extract_city(text: str) -> str:
        m = re.search(r"г\.?\s+([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)", text)
        return m.group(1) if m else "не указан"
