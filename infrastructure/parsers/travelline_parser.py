"""
travelline_parser.py — Парсер Travelline (channel manager / PMS для отелей)
Запуск: python travelline_parser.py alex
        python travelline_parser.py oleg

Что делает:
- Авторизуется в Travelline
- Забирает отчёты: брони, загрузка, выручка, статистика каналов
- Записывает в Google Sheets нужного аккаунта
- Отправляет уведомление в Telegram
"""

import sys
import time
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import pandas as pd
from loguru import logger

sys.path.insert(0, "/home/parser")
from parsers.account_manager import AccountManager, get_account_from_args


class TravellineParser:
    BASE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def __init__(self, am: AccountManager):
        self.am  = am
        self.cfg = am.cfg
        self.session = requests.Session()
        self.session.headers.update(self.BASE_HEADERS)
        self.log = am.log

    def login(self) -> bool:
        """Авторизация в Travelline"""
        try:
            self.log.info(f"[{self.am.account}] Travelline: авторизация...")
            resp = self.session.get(self.cfg.TRAVELLINE_URL, timeout=15)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            # Ищем CSRF-токен (у Travelline обычно в meta или скрытом поле)
            csrf = None
            meta = soup.find("meta", {"name": "csrf-token"})
            if meta:
                csrf = meta.get("content")
            else:
                inp = soup.find("input", {"name": "_token"}) or \
                      soup.find("input", {"name": "csrf_token"})
                if inp:
                    csrf = inp.get("value")

            login_data = {
                "login":    self.cfg.TRAVELLINE_LOGIN,
                "password": self.cfg.TRAVELLINE_PASSWORD,
            }
            if csrf:
                login_data["_token"] = csrf

            login_url = self.cfg.TRAVELLINE_URL.rstrip("/") + "/login"
            resp = self.session.post(login_url, data=login_data, timeout=15)

            if "logout" in resp.text.lower() or resp.status_code == 200:
                self.log.info(f"[{self.am.account}] Travelline: авторизация успешна")
                return True

            self.log.error(f"[{self.am.account}] Travelline: ошибка авторизации (статус {resp.status_code})")
            return False

        except Exception as e:
            self.log.error(f"[{self.am.account}] Travelline login error: {e}")
            return False

    def get_bookings(self, date_from: str = None, date_to: str = None) -> pd.DataFrame:
        """
        Получить список броней.
        date_from/date_to в формате YYYY-MM-DD
        По умолчанию — за вчера.
        """
        if not date_from:
            date_from = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")

        self.log.info(f"[{self.am.account}] Travelline: получение броней {date_from} — {date_to}")

        try:
            # ── АДАПТИРУЙ URL ПОД СВОЙ TRAVELLINE ────────────────────────
            # Пример: GET /report/bookings?from=YYYY-MM-DD&to=YYYY-MM-DD
            url = f"{self.cfg.TRAVELLINE_URL.rstrip('/')}/report/bookings"
            params = {
                "dateFrom": date_from,
                "dateTo":   date_to,
                "format":   "json",  # если API возвращает JSON
            }
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()

            # Если ответ JSON:
            try:
                data = resp.json()
                df = pd.json_normalize(data)
                self.log.info(f"[{self.am.account}] Travelline: получено {len(df)} броней (JSON)")
                return df
            except ValueError:
                pass

            # Если ответ HTML — парсим таблицу:
            soup = BeautifulSoup(resp.text, "lxml")
            table = soup.find("table")
            if table:
                df = pd.read_html(str(table))[0]
                self.log.info(f"[{self.am.account}] Travelline: получено {len(df)} броней (HTML)")
                return df

            self.log.warning(f"[{self.am.account}] Travelline: данные не найдены, проверь URL")
            return pd.DataFrame()

        except Exception as e:
            self.log.error(f"[{self.am.account}] Travelline bookings error: {e}")
            raise

    def get_revenue(self, date_from: str = None, date_to: str = None) -> pd.DataFrame:
        """Получить отчёт по выручке"""
        if not date_from:
            date_from = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")

        try:
            url = f"{self.cfg.TRAVELLINE_URL.rstrip('/')}/report/revenue"
            params = {"dateFrom": date_from, "dateTo": date_to}
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            try:
                return pd.json_normalize(resp.json())
            except ValueError:
                soup = BeautifulSoup(resp.text, "lxml")
                table = soup.find("table")
                return pd.read_html(str(table))[0] if table else pd.DataFrame()
        except Exception as e:
            self.log.error(f"[{self.am.account}] Travelline revenue error: {e}")
            raise

    def get_occupancy(self, date_from: str = None, date_to: str = None) -> pd.DataFrame:
        """Получить отчёт по загрузке"""
        if not date_from:
            date_from = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")

        try:
            url = f"{self.cfg.TRAVELLINE_URL.rstrip('/')}/report/occupancy"
            params = {"dateFrom": date_from, "dateTo": date_to}
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            try:
                return pd.json_normalize(resp.json())
            except ValueError:
                soup = BeautifulSoup(resp.text, "lxml")
                table = soup.find("table")
                return pd.read_html(str(table))[0] if table else pd.DataFrame()
        except Exception as e:
            self.log.error(f"[{self.am.account}] Travelline occupancy error: {e}")
            raise

    def run(self):
        """Основной цикл: авторизация → сбор данных → запись в Sheets → уведомление"""
        parser_name = "Travelline"
        self.log.info(f"[{self.am.account}] === Запуск {parser_name} ===")

        try:
            if not self.login():
                raise RuntimeError("Не удалось авторизоваться в Travelline")

            total_rows = 0

            # Брони
            df_bookings = self.get_bookings()
            if not df_bookings.empty:
                df_bookings.insert(0, "Дата загрузки", datetime.now().strftime("%Y-%m-%d %H:%M"))
                self.am.write_dataframe(df_bookings, "travelline", worksheet_index=0)
                total_rows += len(df_bookings)

            # Выручка
            df_revenue = self.get_revenue()
            if not df_revenue.empty:
                df_revenue.insert(0, "Дата загрузки", datetime.now().strftime("%Y-%m-%d %H:%M"))
                self.am.write_dataframe(df_revenue, "travelline", worksheet_index=1)
                total_rows += len(df_revenue)

            # Загрузка
            df_occ = self.get_occupancy()
            if not df_occ.empty:
                df_occ.insert(0, "Дата загрузки", datetime.now().strftime("%Y-%m-%d %H:%M"))
                self.am.write_dataframe(df_occ, "travelline", worksheet_index=2)
                total_rows += len(df_occ)

            self.am.notify_success(parser_name, total_rows)
            self.log.info(f"[{self.am.account}] {parser_name} завершён. Строк: {total_rows}")

        except Exception as e:
            self.log.error(f"[{self.am.account}] {parser_name} ОШИБКА: {e}")
            self.am.notify_error(parser_name, str(e))
            sys.exit(1)


if __name__ == "__main__":
    account = get_account_from_args()
    am = AccountManager(account)
    parser = TravellineParser(am)
    parser.run()
