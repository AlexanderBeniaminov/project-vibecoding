"""
Парсер Telegram-каналов и групп через Telethon (MTProto API).

Для работы нужно:
1. Зарегистрировать приложение на https://my.telegram.org/apps
2. Получить api_id и api_hash
3. Заполнить TELEGRAM_API_ID и TELEGRAM_API_HASH в .env
4. Добавить каналы/группы в telegram_sources.json

При первом запуске потребуется ввести номер телефона и код из SMS.
Сессия сохраняется в tg_session.session — повторный вход не нужен.
"""
import json
import asyncio
from datetime import datetime, timezone, timedelta
from loguru import logger

import config
from utils.text_parser import (
    extract_area, extract_price, extract_profit, extract_payback,
    detect_location_type, detect_seller_type,
)
from utils.filters import should_include


def _load_sources() -> dict:
    if not config.TELEGRAM_SOURCES_FILE.exists():
        return {"channels": [], "settings": {}}
    with open(config.TELEGRAM_SOURCES_FILE, encoding="utf-8") as f:
        return json.load(f)


class TelegramScraper:
    source_name = "Telegram"

    def scrape(self) -> list[dict]:
        """Синхронная обёртка для вызова из основного кода."""
        if not config.TELEGRAM_API_ID or not config.TELEGRAM_API_HASH:
            logger.warning("[Telegram] TELEGRAM_API_ID или TELEGRAM_API_HASH не заполнены в .env. Пропускаем.")
            return []

        sources = _load_sources()
        channels = sources.get("channels", [])
        if not channels:
            logger.info("[Telegram] Нет каналов в telegram_sources.json. Пропускаем.")
            return []

        try:
            return asyncio.run(self._async_scrape(channels, sources.get("settings", {})))
        except Exception as e:
            logger.error("[Telegram] Критическая ошибка: {}", e)
            return []

    async def _async_scrape(self, channels: list, settings: dict) -> list[dict]:
        try:
            from telethon import TelegramClient
            from telethon.errors import FloodWaitError, ChannelPrivateError, UsernameNotOccupiedError
        except ImportError:
            logger.error("Telethon не установлен. Запусти: pip install telethon")
            return []

        results = []
        max_messages = settings.get("max_messages_per_channel", 200)
        days_back = settings.get("days_lookback", 30)
        since_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        client = TelegramClient(
            str(config.TELEGRAM_SESSION_FILE),
            int(config.TELEGRAM_API_ID),
            config.TELEGRAM_API_HASH,
        )

        await client.start()
        logger.info("[Telegram] Подключено. Обрабатываем {} каналов.", len(channels))

        for channel_ref in channels:
            try:
                items = await self._scrape_channel(client, channel_ref, max_messages, since_date)
                results.extend(items)
                logger.info("[Telegram] {} — найдено {} объявлений", channel_ref, len(items))
                await asyncio.sleep(3)  # небольшая пауза между каналами
            except FloodWaitError as e:
                logger.warning("[Telegram] FloodWait {} сек для {}", e.seconds, channel_ref)
                await asyncio.sleep(e.seconds + 5)
            except (ChannelPrivateError, UsernameNotOccupiedError) as e:
                logger.warning("[Telegram] Нет доступа к {}: {}", channel_ref, e)
            except Exception as e:
                logger.warning("[Telegram] Ошибка при обработке {}: {}", channel_ref, e)

        await client.disconnect()
        return results

    async def _scrape_channel(self, client, channel_ref: str, max_messages: int, since_date) -> list[dict]:
        from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

        results = []
        entity = await client.get_entity(channel_ref)
        channel_name = getattr(entity, "title", str(channel_ref))
        channel_username = getattr(entity, "username", str(channel_ref))
        source_label = f"Telegram: {channel_name}"

        async for message in client.iter_messages(entity, limit=max_messages, offset_date=None):
            if not message.message:
                continue
            if message.date and message.date < since_date:
                break  # сообщения идут от новых к старым

            text = message.message.strip()
            if not text:
                continue

            # Первая строка — часто заголовок
            lines = text.split("\n")
            title = lines[0][:200].strip()
            description = "\n".join(lines[1:])

            area = extract_area(text)
            price = extract_price(text)
            include, priority_flag, area_unknown = should_include(title, text, area)
            if not include:
                continue

            # Ссылка на сообщение
            if channel_username:
                msg_url = f"https://t.me/{channel_username}/{message.id}"
            else:
                msg_url = f"https://t.me/c/{entity.id}/{message.id}"

            results.append({
                "id": f"{entity.id}_{message.id}",
                "source": source_label,
                "url": msg_url,
                "title": title,
                "city": self._extract_city(text),
                "area_m2": area,
                "price_rub": price,
                "profit_month": extract_profit(text),
                "payback_months": extract_payback(text),
                "location_type": detect_location_type(text),
                "seller_type": detect_seller_type(text),
                "published_at": message.date.isoformat() if message.date else None,
                "priority_flag": int(priority_flag),
                "area_unknown_flag": int(area_unknown),
            })

        return results

    @staticmethod
    def _extract_city(text: str) -> str:
        import re
        m = re.search(r"г\.?\s+([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)", text)
        return m.group(1) if m else "не указан"
