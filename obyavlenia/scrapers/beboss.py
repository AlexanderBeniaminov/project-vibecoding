"""
Парсер БИБОСС через Playwright (сайт рендерит результаты через JS).
Выбираем категорию «Развлечения и отдых» через select, затем
собираем карточки .gb-showcase__content.
"""
import re
import time
import random
from loguru import logger

from utils.text_parser import (
    extract_area, extract_price, extract_profit, extract_payback,
    detect_location_type, detect_seller_type,
)
from utils.filters import should_include

BASE_URL = "https://www.beboss.ru"
CATEGORIES = ["entertainment", "kids-business"]


class BebossScraper:
    source_name = "БИБОСС"

    def scrape(self) -> list[dict]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright не установлен")
            return []

        results = []
        seen_ids: set[str] = set()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU",
                viewport={"width": 1440, "height": 900},
            )
            page = ctx.new_page()
            try:
                for category in CATEGORIES:
                    items = self._scrape_category(page, category)
                    for item in items:
                        if item["id"] not in seen_ids:
                            seen_ids.add(item["id"])
                            results.append(item)
                    time.sleep(random.uniform(5, 10))
            finally:
                browser.close()

        logger.info("[БИБОСС] Найдено {} объявлений", len(results))
        return results

    def _scrape_category(self, page, category: str) -> list[dict]:
        results = []
        try:
            page.goto(f"{BASE_URL}/business", wait_until="commit", timeout=45000)
            time.sleep(random.uniform(5, 8))

            # Выбираем категорию через select
            page.select_option("select", value=category)
            time.sleep(random.uniform(5, 8))

            cards = page.locator(".gb-showcase__content").all()
            logger.debug("[БИБОСС] Категория '{}': {} карточек", category, len(cards))

            for card in cards:
                try:
                    item = self._parse_card(card)
                    if item:
                        results.append(item)
                except Exception as e:
                    logger.debug("[БИБОСС] Ошибка карточки: {}", e)

        except Exception as e:
            logger.warning("[БИБОСС] Ошибка категории '{}': {}", category, e)
        return results

    def _parse_card(self, card) -> dict | None:
        # Пропускаем рекламные карточки
        ad_marker = card.locator(".optional-button.for-bell")
        if ad_marker.count() and "Реклама" in (ad_marker.text_content() or ""):
            return None

        # Ссылка
        link = card.locator("a.gb-showcase__about-link")
        if not link.count():
            return None
        href = link.get_attribute("href") or ""
        url = href if href.startswith("http") else BASE_URL + href

        m = re.search(r"/business/(\d+)", href)
        listing_id = m.group(1) if m else ""
        if not listing_id:
            return None

        # Заголовок
        title = (link.text_content() or "").strip()
        if not title:
            return None

        # Цена
        price_el = card.locator(".gb-showcase__purse-text")
        price_text = (price_el.text_content() or "").strip() if price_el.count() else ""
        price = extract_price(price_text)

        # Город
        city_el = card.locator(".gb-showcase__about-city")
        city = (city_el.text_content() or "").strip() if city_el.count() else "не указан"

        full_text = f"{title} {price_text}"
        area = extract_area(full_text)

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
