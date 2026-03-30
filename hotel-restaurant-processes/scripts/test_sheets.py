"""
test_sheets.py — быстрая проверка подключения к Google Sheets.
Запускать из папки hotel-restaurant-processes/:
  python3 scripts/test_sheets.py
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Путь к credentials.json — можно переопределить через env GOOGLE_CREDENTIALS_PATH
CREDENTIALS_PATH = os.environ.get(
    "GOOGLE_CREDENTIALS_PATH",
    os.path.join(os.path.dirname(__file__), "credentials.json")
)

SPREADSHEET_ID = "1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI"

def main():
    try:
        from sheets_writer import get_service, setup_spreadsheet, write_daily_row
    except ImportError as e:
        print(f"\n❌ Не удалось импортировать sheets_writer: {e}")
        print("Установите зависимости: pip3 install google-auth google-api-python-client")
        sys.exit(1)

    # 1. Подключение
    print("\n1️⃣  Подключение к Google Sheets API...")
    try:
        service = get_service(credentials_path=CREDENTIALS_PATH)
        print("   ✅ Сервис создан")
    except Exception as e:
        print(f"   ❌ Ошибка подключения: {e}")
        sys.exit(1)

    # 2. Создание структуры (листы + заголовки)
    print("\n2️⃣  Проверка структуры таблицы (листы + заголовки)...")
    try:
        setup_spreadsheet(service, SPREADSHEET_ID)
        print("   ✅ Структура таблицы готова")
    except Exception as e:
        print(f"   ❌ Ошибка структуры: {e}")
        sys.exit(1)

    # 3. Тестовая строка
    print("\n3️⃣  Запись тестовой строки в лист «Ежедневно»...")
    test_data = {
        "date": "2026-01-01",
        "orders_summary": {"revenue": 99999, "orders": 42, "guests": 85, "avg_check": 2380},
        "payment_types": {"Наличные": 30000, "СБП": 40000, "Банковская карта": 29999},
        "category_revenue": {"Кухня": 65000, "Бар": 34999},
        "hourly": {
            "утро":  {"revenue": 10000, "guests": 15},
            "день":  {"revenue": 40000, "guests": 45},
            "вечер": {"revenue": 49999, "guests": 25},
        },
        "cancellations": 1200,
        "writeoffs": 500,
        "manual": {
            "инкассация": 70000,
            "расход_кассы": 3500,
            "остаток_нал": 26500,
            "завтраки": 12,
            "повара":    {"кол": 3, "зп": 9000},
            "официанты": {"кол": 4, "зп": 12000},
            "бармены":   {"кол": 1, "зп": 3500},
            "посудомойщицы": {"кол": 2, "зп": 5000},
        },
    }
    try:
        write_daily_row(service, SPREADSHEET_ID, test_data)
        print("   ✅ Тестовая строка записана")
    except Exception as e:
        print(f"   ❌ Ошибка записи: {e}")
        sys.exit(1)

    print("\n✅ Все проверки пройдены. Google Sheets работает корректно.")
    print(f"   Таблица: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")

if __name__ == "__main__":
    main()
