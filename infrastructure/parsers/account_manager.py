"""
account_manager.py — Центральный менеджер аккаунтов.
Автоматически выбирает нужные ключи и подключения по имени аккаунта.

Использование:
    from account_manager import AccountManager
    am = AccountManager("alex")  # или "oleg"
    sheet = am.get_sheet("travelline")
    am.notify("Парсинг завершён ✅")
"""

import sys
import importlib.util
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials
import telegram
import asyncio
import logging
import requests
from datetime import datetime
from loguru import logger

VKMAX_API = "https://botapi.max.ru"

CONFIG_BASE = Path("/home/parser/config")
LOG_BASE    = Path("/home/parser/logs")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class AccountManager:
    def __init__(self, account: str):
        if account not in ("alex", "oleg"):
            raise ValueError(f"Аккаунт должен быть 'alex' или 'oleg', получено: {account}")

        self.account = account
        self.cfg = self._load_config()
        self._gs_client = None
        self._setup_logging()

    def _load_config(self):
        cfg_path = CONFIG_BASE / self.account / "settings.py"
        if not cfg_path.exists():
            raise FileNotFoundError(f"Конфиг не найден: {cfg_path}")
        spec = importlib.util.spec_from_file_location("settings", cfg_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _setup_logging(self):
        log_file = LOG_BASE / f"{self.account}_{datetime.now().strftime('%Y-%m-%d')}.log"
        LOG_BASE.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(log_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            rotation="1 day",
            retention="30 days",
            level="INFO",
        )
        self.log = logger

    # ── Google Sheets ──────────────────────────────────────────
    def _get_gs_client(self):
        if self._gs_client is None:
            creds = Credentials.from_service_account_file(
                self.cfg.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
            )
            self._gs_client = gspread.authorize(creds)
        return self._gs_client

    def get_sheet(self, sheet_name: str, worksheet_index: int = 0):
        """Вернуть объект листа Google Sheets по ключу из settings.py"""
        spreadsheet_id = self.cfg.SPREADSHEET_IDS.get(sheet_name)
        if not spreadsheet_id:
            raise KeyError(f"Таблица '{sheet_name}' не найдена в SPREADSHEET_IDS аккаунта {self.account}")
        gc = self._get_gs_client()
        spreadsheet = gc.open_by_key(spreadsheet_id)
        return spreadsheet.get_worksheet(worksheet_index)

    def write_dataframe(self, df, sheet_name: str, worksheet_index: int = 0, clear_first: bool = True):
        """Записать DataFrame в Google Sheets"""
        import pandas as pd
        sheet = self.get_sheet(sheet_name, worksheet_index)
        if clear_first:
            sheet.clear()
        data = [df.columns.tolist()] + df.fillna("").values.tolist()
        sheet.update("A1", data)
        self.log.info(f"[{self.account}] Записано {len(df)} строк в таблицу '{sheet_name}'")

    def append_row(self, sheet_name: str, row: list, worksheet_index: int = 0):
        """Добавить одну строку в конец таблицы"""
        sheet = self.get_sheet(sheet_name, worksheet_index)
        sheet.append_row(row)
        self.log.info(f"[{self.account}] Добавлена строка в '{sheet_name}': {row}")

    # ── Telegram Notifications ─────────────────────────────────
    def notify(self, message: str, parse_mode: str = "HTML"):
        """Отправить уведомление в Telegram нужного аккаунта"""
        token   = self.cfg.TELEGRAM_BOT_TOKEN
        chat_id = self.cfg.TELEGRAM_CHAT_ID
        if not token or not chat_id:
            self.log.warning(f"[{self.account}] Telegram не настроен — пропускаю уведомление")
            return

        async def _send():
            bot = telegram.Bot(token=token)
            await bot.send_message(chat_id=chat_id, text=message, parse_mode=parse_mode)

        try:
            asyncio.get_event_loop().run_until_complete(_send())
            self.log.info(f"[{self.account}] Telegram уведомление отправлено")
        except Exception as e:
            self.log.error(f"[{self.account}] Ошибка Telegram: {e}")

    def notify_success(self, parser_name: str, rows: int, extra: str = ""):
        msg = (
            f"✅ <b>[{self.cfg.ACCOUNT_NAME}] {parser_name}</b>\n"
            f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"Записей: {rows}\n"
            + (f"Инфо: {extra}" if extra else "")
        )
        self.notify(msg)

    def notify_error(self, parser_name: str, error: str):
        msg = (
            f"❌ <b>[{self.cfg.ACCOUNT_NAME}] {parser_name} — ОШИБКА</b>\n"
            f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"Ошибка: <code>{error[:300]}</code>"
        )
        self.notify(msg)

    def notify_status(self, text: str):
        msg = f"ℹ️ <b>[{self.cfg.ACCOUNT_NAME}]</b>\n{text}"
        self.notify(msg)

    # ── VK MAX Notifications ───────────────────────────────────
    def notify_vkmax(self, message: str):
        """Отправить уведомление через VK MAX бота"""
        token   = getattr(self.cfg, "VK_MAX_TOKEN", None)
        user_id = getattr(self.cfg, "VK_MAX_USER_ID", None)
        if not token or not user_id:
            self.log.warning(f"[{self.account}] VK MAX не настроен — пропускаю уведомление")
            return
        try:
            resp = requests.post(
                f"{VKMAX_API}/messages",
                params={"user_id": user_id},
                headers={"Authorization": token, "Content-Type": "application/json"},
                json={"text": message},
                timeout=10,
            )
            resp.raise_for_status()
            self.log.info(f"[{self.account}] VK MAX уведомление отправлено")
        except Exception as e:
            self.log.error(f"[{self.account}] Ошибка VK MAX: {e}")


def get_account_from_args() -> str:
    """Получить имя аккаунта из аргументов командной строки"""
    if len(sys.argv) < 2 or sys.argv[1] not in ("alex", "oleg"):
        print("Использование: python script.py alex|oleg")
        sys.exit(1)
    return sys.argv[1]
