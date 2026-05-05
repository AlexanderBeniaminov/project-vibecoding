"""
telegram_monitor.py — Мониторинг Telegram каналов и чатов
Запуск: python telegram_monitor.py alex
        python telegram_monitor.py oleg

Что делает:
- Подключается к Telegram через Telethon (user API, не bot API)
- Читает последние сообщения из заданных каналов/чатов
- Фильтрует по ключевым словам
- Сохраняет в Google Sheets + уведомляет в Telegram-бот

ВАЖНО: Первый запуск потребует ввода кода из SMS — это нормально.
После первого запуска сессия сохранится и код больше не нужен.
"""

import sys
import asyncio
from datetime import datetime, timedelta, timezone
import pandas as pd
from loguru import logger
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, MessageMediaPhoto, MessageMediaDocument

sys.path.insert(0, "/home/parser")
from parsers.account_manager import AccountManager, get_account_from_args

SESSION_DIR = "/home/parser/config"


class TelegramMonitor:
    def __init__(self, am: AccountManager):
        self.am   = am
        self.cfg  = am.cfg
        self.log  = am.log

        session_path = f"{SESSION_DIR}/{am.account}/tg_session"
        self.client = TelegramClient(
            session_path,
            self.cfg.TELEGRAM_API_ID,
            self.cfg.TELEGRAM_API_HASH,
        )

    async def _get_messages(
        self,
        channel_id,
        hours_back: int = 3,
        limit: int = 200,
    ) -> list[dict]:
        """Получить сообщения из канала/чата за последние N часов"""
        since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        messages = []

        async for msg in self.client.iter_messages(
            channel_id,
            limit=limit,
            offset_date=datetime.now(timezone.utc),
            reverse=False,
        ):
            if msg.date < since:
                break
            if not msg.text:
                continue

            text = msg.text or ""
            keywords = getattr(self.cfg, "MONITOR_KEYWORDS", [])
            matched_kw = [kw for kw in keywords if kw.lower() in text.lower()]

            has_media = isinstance(msg.media, (MessageMediaPhoto, MessageMediaDocument))

            messages.append({
                "дата":            msg.date.strftime("%Y-%m-%d %H:%M:%S"),
                "канал":           str(channel_id),
                "id_сообщения":    msg.id,
                "текст":           text[:2000],
                "просмотры":       msg.views or 0,
                "реакции":         self._count_reactions(msg),
                "пересылки":       msg.forwards or 0,
                "ответы":          msg.replies.replies if msg.replies else 0,
                "есть_медиа":      "да" if has_media else "нет",
                "ключевые_слова":  ", ".join(matched_kw) if matched_kw else "",
                "совпадение_кв":   "да" if matched_kw else "нет",
            })

        return messages

    def _count_reactions(self, msg) -> int:
        try:
            if msg.reactions and msg.reactions.results:
                return sum(r.count for r in msg.reactions.results)
        except Exception:
            pass
        return 0

    async def run_async(self):
        parser_name = "Telegram Monitor"
        self.log.info(f"[{self.am.account}] === Запуск {parser_name} ===")

        channels   = getattr(self.cfg, "MONITORED_CHANNELS", [])
        keywords   = getattr(self.cfg, "MONITOR_KEYWORDS", [])

        if not channels:
            self.log.warning(f"[{self.am.account}] MONITORED_CHANNELS пуст — добавь каналы в settings.py")
            return

        await self.client.start(phone=self.cfg.TELEGRAM_PHONE)
        self.log.info(f"[{self.am.account}] Telegram клиент подключён")

        all_messages = []
        keyword_hits = []

        for ch in channels:
            try:
                self.log.info(f"[{self.am.account}] Читаю канал: {ch}")
                msgs = await self._get_messages(ch, hours_back=3)
                all_messages.extend(msgs)

                # Сообщения с совпадением ключевых слов
                hits = [m for m in msgs if m["совпадение_кв"] == "да"]
                keyword_hits.extend(hits)

                self.log.info(f"[{self.am.account}] {ch}: {len(msgs)} сообщений, {len(hits)} совпадений")
            except Exception as e:
                self.log.error(f"[{self.am.account}] Ошибка канала {ch}: {e}")

        await self.client.disconnect()

        if not all_messages:
            self.log.info(f"[{self.am.account}] Новых сообщений нет")
            return

        # Записываем все сообщения в Sheets (добавляем строки, не перезаписываем)
        df = pd.DataFrame(all_messages)
        sheet = self.am.get_sheet("reports", worksheet_index=0)
        for row in df.values.tolist():
            sheet.append_row(row)

        self.log.info(f"[{self.am.account}] Записано {len(df)} сообщений в Google Sheets")

        # Уведомление о совпадениях ключевых слов
        if keyword_hits:
            hits_text = "\n".join([
                f"• {h['канал']} | {h['дата'][:16]}\n  {h['текст'][:200]}..."
                for h in keyword_hits[:5]
            ])
            self.am.notify(
                f"🔍 <b>[{self.am.cfg.ACCOUNT_NAME}] Telegram: найдены совпадения</b>\n"
                f"Ключевые слова: <code>{', '.join(keywords)}</code>\n"
                f"Всего совпадений: {len(keyword_hits)}\n\n"
                f"{hits_text}"
            )

        # Итоговое уведомление
        self.am.notify_success(
            parser_name,
            len(all_messages),
            f"Совпадений по ключевым словам: {len(keyword_hits)}"
        )

    def run(self):
        asyncio.run(self.run_async())


if __name__ == "__main__":
    account = get_account_from_args()
    am = AccountManager(account)
    monitor = TelegramMonitor(am)
    monitor.run()
