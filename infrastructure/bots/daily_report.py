"""
daily_report.py — Ежедневный отчёт в VK MAX из Google Sheets (ЕжеДневно)
Запуск: python daily_report.py alex
Запускается через cron каждое утро в 09:00 МСК.
"""

import sys
from datetime import datetime, timedelta

sys.path.insert(0, "/home/parser")
from parsers.account_manager import AccountManager, get_account_from_args

# Строки с нужными метриками (номер строки в листе, начиная с 1)
METRICS = {
    "Выручка итого":  3,
    "Кухня":          7,
    "Бар":            8,
    "Средний чек":    5,
    "Гости":          6,
    "Завтраки":       25,
}


def build_report(am: AccountManager) -> str:
    yesterday = datetime.now() - timedelta(days=1)
    date_str  = yesterday.strftime("%Y-%m-%d")
    label     = yesterday.strftime("%d.%m.%Y (%A)")

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        creds = Credentials.from_service_account_file(
            am.cfg.GOOGLE_SERVICE_ACCOUNT_JSON,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(am.cfg.SPREADSHEET_IDS["iiko"])
        ws = sh.worksheet("ЕжеДневно")

        # Строка 1 — все даты; ищем колонку для вчера
        dates = ws.row_values(1)
        try:
            col_idx = dates.index(date_str) + 1  # 1-based
        except ValueError:
            return f"Отчёт за {label}\nДанные за вчера ещё не загружены в таблицу."

        # Читаем нужные метрики по номерам строк
        lines = [f"Отчёт ресторана за {label}", ""]
        for name, row_num in METRICS.items():
            cell = ws.cell(row_num, col_idx).value or "—"
            lines.append(f"{name}: {cell}")

        return "\n".join(lines)

    except Exception as e:
        return f"Ошибка при формировании отчёта:\n{e}"


if __name__ == "__main__":
    account = get_account_from_args()
    am = AccountManager(account)
    report = build_report(am)
    am.notify_vkmax(report)
    am.log.info(f"[{account}] Ежедневный отчёт отправлен")
    print(report)
