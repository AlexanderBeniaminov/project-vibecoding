"""
Базовый класс парсера: ротация User-Agent, задержки, retry при 403/429, логирование.
"""
import time
import random
from abc import ABC, abstractmethod
from typing import Optional
from loguru import logger

import requests
from fake_useragent import UserAgent

import config

_ua = UserAgent()


class BaseScraper(ABC):
    """Наследуй этот класс для каждой площадки."""

    source_name: str = "unknown"   # переопредели в подклассе

    def __init__(self):
        self.session = requests.Session()
        self._update_headers()

    def _update_headers(self) -> None:
        self.session.headers.update({
            "User-Agent": _ua.random,
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """GET с retry и случайной задержкой. Возвращает Response или None."""
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                self._random_request_delay()
                self._update_headers()
                resp = self.session.get(url, timeout=30, **kwargs)

                if resp.status_code in (403, 429):
                    logger.warning(
                        "[{}] HTTP {} на {}. Пауза {} сек. (попытка {}/{})",
                        self.source_name, resp.status_code, url,
                        config.RETRY_PAUSE, attempt, config.MAX_RETRIES
                    )
                    time.sleep(config.RETRY_PAUSE)
                    continue

                resp.raise_for_status()
                return resp

            except requests.RequestException as e:
                logger.warning("[{}] Ошибка запроса (попытка {}/{}): {}", self.source_name, attempt, config.MAX_RETRIES, e)
                if attempt < config.MAX_RETRIES:
                    time.sleep(10 * attempt)

        logger.error("[{}] Не удалось получить: {}", self.source_name, url)
        return None

    def _random_request_delay(self) -> None:
        delay = random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)
        time.sleep(delay)

    @staticmethod
    def site_delay() -> None:
        """Задержка между площадками."""
        delay = random.uniform(config.SITE_DELAY_MIN, config.SITE_DELAY_MAX)
        logger.debug("Задержка между площадками: {:.1f} сек", delay)
        time.sleep(delay)

    @abstractmethod
    def scrape(self) -> list[dict]:
        """
        Парсит площадку и возвращает список словарей с полями:
        id, url, source, title, city, area_m2, price_rub, profit_month,
        payback_months, location_type, seller_type, published_at
        """
        ...
