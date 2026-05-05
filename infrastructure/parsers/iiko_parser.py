"""
iiko_parser.py — Парсер iiko (система автоматизации ресторанов)
Запуск: python iiko_parser.py alex
        python iiko_parser.py oleg

Использует официальный iiko Server API (REST).
Забирает: выручку по сменам, топ блюд, остатки на складе.
"""

import sys
import requests
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger

sys.path.insert(0, "/home/parser")
from parsers.account_manager import AccountManager, get_account_from_args


class IikoParser:
    def __init__(self, am: AccountManager):
        self.am     = am
        self.cfg    = am.cfg
        self.base   = self.cfg.IIKO_SERVER_URL.rstrip("/")
        self.token  = None
        self.log    = am.log
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def login(self) -> bool:
        """Получить сессионный токен iiko API"""
        try:
            import hashlib
            password_hash = hashlib.sha1(
                self.cfg.IIKO_PASSWORD.encode("utf-8")
            ).hexdigest()

            url = f"{self.base}/resto/api/auth"
            resp = self.session.get(url, params={
                "login": self.cfg.IIKO_LOGIN,
                "pass":  password_hash,
            }, timeout=15)
            resp.raise_for_status()
            self.token = resp.text.strip()
            self.log.info(f"[{self.am.account}] iiko: авторизация успешна (token: {self.token[:8]}...)")
            return True
        except Exception as e:
            self.log.error(f"[{self.am.account}] iiko login error: {e}")
            return False

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """Выполнить GET-запрос к iiko API"""
        p = {"key": self.token}
        if params:
            p.update(params)
        resp = self.session.get(f"{self.base}/resto/api/{endpoint}", params=p, timeout=30)
        resp.raise_for_status()
        return resp.json() if resp.text.strip() else {}

    def get_shifts_revenue(self, date_from: str = None, date_to: str = None) -> pd.DataFrame:
        """Выручка по кассовым сменам"""
        if not date_from:
            date_from = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")

        self.log.info(f"[{self.am.account}] iiko: выручка по сменам {date_from} — {date_to}")
        try:
            data = self._get("reports/olap", {
                "report":   "SALES",
                "dateFrom": date_from,
                "dateTo":   date_to,
                "groupBy":  "cashRegisterShift",
            })
            if isinstance(data, list):
                return pd.DataFrame(data)
            if isinstance(data, dict) and "data" in data:
                return pd.DataFrame(data["data"])
            return pd.DataFrame()
        except Exception as e:
            self.log.error(f"[{self.am.account}] iiko shifts error: {e}")
            raise

    def get_top_dishes(self, date_from: str = None, date_to: str = None, top_n: int = 50) -> pd.DataFrame:
        """Топ блюд по количеству продаж"""
        if not date_from:
            date_from = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")

        self.log.info(f"[{self.am.account}] iiko: топ-{top_n} блюд {date_from} — {date_to}")
        try:
            data = self._get("reports/olap", {
                "report":   "SALES",
                "dateFrom": date_from,
                "dateTo":   date_to,
                "groupBy":  "dish",
            })
            if isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, dict) and "data" in data:
                df = pd.DataFrame(data["data"])
            else:
                return pd.DataFrame()

            if "amount" in df.columns:
                df = df.nlargest(top_n, "amount")
            return df
        except Exception as e:
            self.log.error(f"[{self.am.account}] iiko dishes error: {e}")
            raise

    def get_balance(self) -> pd.DataFrame:
        """Текущие остатки на складе"""
        self.log.info(f"[{self.am.account}] iiko: остатки на складе...")
        try:
            data = self._get("reports/balance", {
                "onDate": datetime.now().strftime("%Y-%m-%d"),
            })
            if isinstance(data, list):
                return pd.DataFrame(data)
            if isinstance(data, dict) and "data" in data:
                return pd.DataFrame(data["data"])
            return pd.DataFrame()
        except Exception as e:
            self.log.error(f"[{self.am.account}] iiko balance error: {e}")
            raise

    def run(self):
        parser_name = "iiko"
        self.log.info(f"[{self.am.account}] === Запуск {parser_name} ===")

        try:
            if not self.login():
                raise RuntimeError("Не удалось авторизоваться в iiko")

            total_rows = 0

            # Выручка по сменам → лист 0
            df_shifts = self.get_shifts_revenue()
            if not df_shifts.empty:
                df_shifts.insert(0, "Дата загрузки", datetime.now().strftime("%Y-%m-%d %H:%M"))
                self.am.write_dataframe(df_shifts, "iiko", worksheet_index=0)
                total_rows += len(df_shifts)

            # Топ блюд → лист 1
            df_dishes = self.get_top_dishes()
            if not df_dishes.empty:
                df_dishes.insert(0, "Дата загрузки", datetime.now().strftime("%Y-%m-%d %H:%M"))
                self.am.write_dataframe(df_dishes, "iiko", worksheet_index=1)
                total_rows += len(df_dishes)

            # Остатки → лист 2
            df_balance = self.get_balance()
            if not df_balance.empty:
                df_balance.insert(0, "Дата загрузки", datetime.now().strftime("%Y-%m-%d %H:%M"))
                self.am.write_dataframe(df_balance, "iiko", worksheet_index=2)
                total_rows += len(df_balance)

            self.am.notify_success(parser_name, total_rows)
            self.log.info(f"[{self.am.account}] {parser_name} завершён. Строк: {total_rows}")

        except Exception as e:
            self.log.error(f"[{self.am.account}] {parser_name} ОШИБКА: {e}")
            self.am.notify_error(parser_name, str(e))
            sys.exit(1)


if __name__ == "__main__":
    account = get_account_from_args()
    am = AccountManager(account)
    parser = IikoParser(am)
    parser.run()
