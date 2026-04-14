"""
Парсер Авито — использует Playwright из-за JS-рендеринга и антибот защиты.
При первом запуске открывает браузер НЕ в headless режиме чтобы пройти капчу вручную.
Сессия (cookies) сохраняется в avito_session.json и переиспользуется.
"""
import json
import time
import random
from pathlib import Path
from loguru import logger

from utils.text_parser import (
    extract_area, extract_price, extract_profit, extract_payback,
    detect_location_type, detect_seller_type,
)
from utils.filters import should_include
import config

SESSION_FILE = config.BASE_DIR / "avito_session.json"
BASE_URL = "https://www.avito.ru"
SEARCH_URL = "https://www.avito.ru/rossiya/gotoviy_biznes?q=развлечения+дети"

# Дополнительные поисковые запросы для разных направлений
SEARCH_QUERIES = [
    "https://www.avito.ru/rossiya/gotoviy_biznes?q=детский+развлекательный+центр",
    "https://www.avito.ru/rossiya/gotoviy_biznes?q=батутный+парк",
    "https://www.avito.ru/rossiya/gotoviy_biznes?q=семейный+парк+развлечений",
    "https://www.avito.ru/rossiya/gotoviy_biznes?q=игровой+центр",
]


class AvitoScraper:
    source_name = "Авито"

    def scrape(self) -> list[dict]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright не установлен. Запусти: pip install playwright && playwright install chromium")
            return []

        results = []
        seen_ids: set[str] = set()

        with sync_playwright() as p:
            browser, context = self._get_browser_context(p)
            try:
                for search_url in SEARCH_QUERIES:
                    try:
                        items = self._scrape_search(context, search_url)
                        for item in items:
                            if item["id"] not in seen_ids:
                                seen_ids.add(item["id"])
                                results.append(item)
                    except Exception as e:
                        logger.warning("[Авито] Ошибка при обходе {}: {}", search_url, e)
                    time.sleep(random.uniform(15, 30))

                # Сохраняем сессию
                context.storage_state(path=str(SESSION_FILE))
            finally:
                browser.close()

        logger.info("[Авито] Найдено {} объявлений", len(results))
        return results

    def _get_browser_context(self, p):
        """Запускает браузер в headless режиме, сохраняет сессию."""
        browser = p.chromium.launch(headless=True)
        context_args = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "viewport": {"width": 1366, "height": 768},
            "locale": "ru-RU",
        }
        if SESSION_FILE.exists():
            context_args["storage_state"] = str(SESSION_FILE)

        context = browser.new_context(**context_args)

        if not SESSION_FILE.exists():
            logger.info("[Авито] Первый запуск — прогреваем сессию...")
            page = context.new_page()
            page.goto("https://www.avito.ru", wait_until="domcontentloaded", timeout=30000)
            time.sleep(5)
            context.storage_state(path=str(SESSION_FILE))
            page.close()

        return browser, context

    def _scrape_search(self, context, url: str) -> list[dict]:
        results = []
        page = context.new_page()
        try:
            for page_num in range(1, 6):  # макс 5 страниц
                page_url = url if page_num == 1 else f"{url}&p={page_num}"
                page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(3, 7))

                # Проверка на капчу/блокировку
                if "captcha" in page.url or "blocked" in page.content().lower()[:500]:
                    logger.warning("[Авито] Обнаружена капча на странице {}", page_num)
                    break

                items = page.query_selector_all("[data-marker='item'], .iva-item-root, [data-item-id]")
                if not items:
                    break

                for elem in items:
                    try:
                        item = self._parse_element(page, elem)
                        if item:
                            results.append(item)
                    except Exception as e:
                        logger.debug("[Авито] Ошибка элемента: {}", e)

                time.sleep(random.uniform(4, 10))

                # Проверка следующей страницы
                next_btn = page.query_selector("[data-marker='pagination-button/next']")
                if not next_btn:
                    break
        finally:
            page.close()
        return results

    def _parse_element(self, page, elem) -> dict | None:
        # ID объявления
        listing_id = (
            elem.get_attribute("data-item-id") or
            elem.get_attribute("id") or
            ""
        )
        if not listing_id:
            return None

        # Заголовок
        title_elem = elem.query_selector("[itemprop='name'], .iva-item-title, h3")
        title = title_elem.inner_text().strip() if title_elem else ""
        if not title:
            return None

        # Ссылка
        link_elem = elem.query_selector("a[href*='/avito.ru/'], a[data-marker='item-title']")
        href = link_elem.get_attribute("href") if link_elem else ""
        url = (BASE_URL + href) if href and not href.startswith("http") else href

        # Цена
        price_elem = elem.query_selector("[data-marker='item-price'], .price-text, .iva-item-price")
        price_text = price_elem.inner_text() if price_elem else ""
        price = extract_price(price_text) if price_text else None

        # Описание (короткое из листинга)
        desc_elem = elem.query_selector(".iva-item-description, [data-marker='item-description']")
        description = desc_elem.inner_text().strip() if desc_elem else ""

        full_text = f"{title} {description} {price_text}"
        area = extract_area(full_text)

        include, priority_flag, area_unknown = should_include(title, full_text, area)
        if not include:
            return None

        # Местоположение
        geo_elem = elem.query_selector("[data-marker='item-location'], .geo-address")
        city = geo_elem.inner_text().strip() if geo_elem else "не указан"

        # Дата
        date_elem = elem.query_selector("[data-marker='item-date'], .date-text")
        pub_date = date_elem.get_attribute("datetime") or (date_elem.inner_text().strip() if date_elem else None)

        return {
            "id": str(listing_id),
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
