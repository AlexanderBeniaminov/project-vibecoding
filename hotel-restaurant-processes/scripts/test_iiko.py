"""
test_iiko.py — быстрый тест подключения к iiko API.
Запуск: python test_iiko.py

Перед запуском задать переменные окружения:
  export IIKO_LOGIN=user
  export IIKO_PASSWORD=user#test
или передать напрямую:
  IIKO_LOGIN=user IIKO_PASSWORD='user#test' python test_iiko.py
"""

import logging
import os
import sys
from datetime import date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Добавить папку scripts в путь, если запускается из другой директории
sys.path.insert(0, os.path.dirname(__file__))

from iiko_client import (
    collect_daily_data,
    get_orders_summary,
    get_revenue_by_payment_type,
    get_token,
)
from config import IIKO_BASE_URL, IIKO_LOGIN, IIKO_PASSWORD


def main():
    if not IIKO_LOGIN or not IIKO_PASSWORD:
        print("❌ Не заданы IIKO_LOGIN и IIKO_PASSWORD")
        print("   Запусти: IIKO_LOGIN=user IIKO_PASSWORD='user#test' python test_iiko.py")
        sys.exit(1)

    print(f"\n{'='*50}")
    print(f"Тест подключения к iiko API")
    print(f"URL: {IIKO_BASE_URL}")
    print(f"Логин: {IIKO_LOGIN}")
    print(f"{'='*50}\n")

    # 1. Авторизация
    print("1. Авторизация...")
    token = get_token(IIKO_BASE_URL, IIKO_LOGIN, IIKO_PASSWORD)
    print(f"   ✅ Токен получен: {token[:20]}...\n")

    # 2. Тест за вчера
    yesterday = date.today() - timedelta(days=1)
    print(f"2. Сводка по заказам за {yesterday}...")
    summary = get_orders_summary(IIKO_BASE_URL, token, yesterday)
    print(f"   Чеков: {summary['orders']}")
    print(f"   Гостей: {summary['guests']}")
    print(f"   Выручка: {summary['revenue']} руб.")
    print(f"   Средний чек: {summary['avg_check']} руб.\n")

    # 3. Выручка по типам оплаты
    print(f"3. Выручка по типам оплаты за {yesterday}...")
    payments = get_revenue_by_payment_type(IIKO_BASE_URL, token, yesterday)
    for pay_type, amount in payments.items():
        print(f"   {pay_type}: {amount} руб.")
    print()

    # 4. Полный сбор данных
    print(f"4. Полный сбор всех данных за {yesterday}...")
    data = collect_daily_data(IIKO_BASE_URL, token, yesterday)

    if data["errors"]:
        print(f"   ⚠️ Ошибки ({len(data['errors'])}):")
        for err in data["errors"]:
            print(f"      - {err}")
    else:
        print("   ✅ Все данные получены без ошибок")

    print(f"\n{'='*50}")
    print("Тест завершён успешно")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
