"""
universal_parser.py — Универсальный шаблон для любого сайта
Запуск: python universal_parser.py alex
        python universal_parser.py oleg

Возможности:
- Ротация User-Agent
- Задержки между запросами (антибот-защита)
- Retry при ошибках сети
- Playwright для JS-сайтов (если requests не помогает)
- Сохранение в CSV + Google Sheets

Как адаптировать:
1. Задай TARGET_URL
2. Напиши parse_page() под конкретный сайт
3. Запусти
"""

import sys
import time
import random
import csv
import requests
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import pandas as pd

sys.path.insert(0, "/home/parser")
from parsers.account_manager import AccountManager, get_account_from_args

DATA_DIR = Path("/home/parser/data")
DATA_DIR.mkdir(exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.2; rv:121.0) Gecko/20100101 Firefox/121.0",
]


class UniversalParser:
    # ── НАСТРОЙ ЭТИ ПАРАМЕТРЫ ────────────────────────────────────
    TARGET_URL    = "https://example.com/catalog"   # ← заменить
    SHEET_NAME    = "reports"                        # ← ключ из SPREADSHEET_IDS
    OUTPUT_CSV    = "universal_parse_result.csv"     # имя CSV-файла
    DELAY_MIN     = 2.0   # минимальная задержка между страницами (сек)
    DELAY_MAX     = 5.0   # максимальная задержка
    MAX_PAGES     = 50    # максимум страниц пагинации
    USE_PLAYWRIGHT = False  # True — если сайт на JS (загружается браузером)
    # ─────────────────────────────────────────────────────────────

    def __init__(self, am: AccountManager):
        self.am      = am
        self.cfg     = am.cfg
        self.log     = am.log
        self.session = requests.Session()
        self._rotate_headers()

    def _rotate_headers(self):
        self.session.headers.update({
            "User-Agent":      random.choice(USER_AGENTS),
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Connection":      "keep-alive",
            "DNT":             "1",
        })

    def _random_delay(self):
        delay = random.uniform(self.DELAY_MIN, self.DELAY_MAX)
        self.log.debug(f"Задержка {delay:.1f}с")
        time.sleep(delay)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=30),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def _get_page(self, url: str, params: dict = None) -> BeautifulSoup:
        """Загрузить страницу с retry и ротацией заголовков"""
        self._rotate_headers()
        resp = self.session.get(url, params=params, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def _get_page_playwright(self, url: str) -> BeautifulSoup:
        """Загрузить JS-страницу через Playwright (headless Chromium)"""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=random.choice(USER_AGENTS))
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            html = page.content()
            browser.close()
        return BeautifulSoup(html, "lxml")

    def fetch_page(self, url: str, params: dict = None) -> BeautifulSoup:
        if self.USE_PLAYWRIGHT:
            return self._get_page_playwright(url)
        return self._get_page(url, params)

    def get_next_page_url(self, soup: BeautifulSoup, current_page: int) -> str | None:
        """
        Логика пагинации — адаптируй под конкретный сайт.

        Вариант 1: кнопка «Следующая»
            next_btn = soup.find("a", {"class": "next"})
            return next_btn["href"] if next_btn else None

        Вариант 2: параметр ?page=N в URL
            return f"{self.TARGET_URL}?page={current_page + 1}"

        Вариант 3: бесконечная прокрутка (используй Playwright + scroll)
        """
        # ── АДАПТИРУЙ ЭТУ ФУНКЦИЮ ────────────────────────────────
        next_btn = soup.find("a", string=lambda t: t and ("Далее" in t or ">" in t or "next" in t.lower()))
        if next_btn and next_btn.get("href"):
            href = next_btn["href"]
            if href.startswith("http"):
                return href
            from urllib.parse import urljoin
            return urljoin(self.TARGET_URL, href)
        return None

    def parse_page(self, soup: BeautifulSoup) -> list[dict]:
        """
        Парсинг одной страницы — адаптируй под конкретный сайт.

        Пример для интернет-магазина:
            items = soup.select(".product-card")
            result = []
            for item in items:
                result.append({
                    "название": item.select_one(".product-title").text.strip(),
                    "цена":     item.select_one(".price").text.strip(),
                    "ссылка":   item.select_one("a")["href"],
                })
            return result

        Пример для новостного сайта:
            articles = soup.select("article.news-item")
            return [{
                "заголовок": a.select_one("h2").text.strip(),
                "дата":      a.select_one("time")["datetime"],
                "текст":     a.select_one("p").text.strip(),
            } for a in articles]
        """
        # ── ЗАМЕНИ ЭТО СВОИМ КОДОМ ───────────────────────────────
        items = soup.select("div.item, li.item, article, .card")
        result = []
        for item in items:
            title_el = item.find(["h1", "h2", "h3", "h4"])
            result.append({
                "заголовок": title_el.text.strip() if title_el else "",
                "текст":     item.text.strip()[:500],
                "дата":      datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
        return result

    def run(self, sheet_name: str = None):
        parser_name = "Universal Parser"
        self.log.info(f"[{self.am.account}] === Запуск {parser_name} ({self.TARGET_URL}) ===")

        all_data = []
        url      = self.TARGET_URL
        page_num = 1

        try:
            while url and page_num <= self.MAX_PAGES:
                self.log.info(f"[{self.am.account}] Страница {page_num}: {url}")
                soup = self.fetch_page(url)
                page_data = self.parse_page(soup)

                if not page_data:
                    self.log.info(f"[{self.am.account}] Страница {page_num}: данных нет, останавливаюсь")
                    break

                all_data.extend(page_data)
                self.log.info(f"[{self.am.account}] Страница {page_num}: получено {len(page_data)} записей")

                url = self.get_next_page_url(soup, page_num)
                page_num += 1

                if url:
                    self._random_delay()

            if not all_data:
                self.log.warning(f"[{self.am.account}] Данных не получено")
                return

            df = pd.DataFrame(all_data)
            df.insert(0, "Дата загрузки", datetime.now().strftime("%Y-%m-%d %H:%M"))

            # Сохраняем в CSV
            csv_path = DATA_DIR / f"{self.am.account}_{self.OUTPUT_CSV}"
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            self.log.info(f"[{self.am.account}] CSV сохранён: {csv_path}")

            # Записываем в Google Sheets
            target_sheet = sheet_name or self.SHEET_NAME
            self.am.write_dataframe(df, target_sheet)

            self.am.notify_success(parser_name, len(df), f"Страниц: {page_num-1}")
            self.log.info(f"[{self.am.account}] {parser_name} завершён. Всего: {len(df)} строк")

        except Exception as e:
            self.log.error(f"[{self.am.account}] {parser_name} ОШИБКА: {e}")
            self.am.notify_error(parser_name, str(e))
            sys.exit(1)


if __name__ == "__main__":
    account = get_account_from_args()
    am = AccountManager(account)
    parser = UniversalParser(am)
    parser.run()
