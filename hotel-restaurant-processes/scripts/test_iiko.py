"""
test_iiko.py — быстрый тест подключения к iiko Cloud API.

Запуск из папки hotel-restaurant-processes/:
  IIKO_API_LOGIN=ВАШ_КЛЮЧ IIKO_ORG_ID=UUID python scripts/test_iiko.py

Или без IIKO_ORG_ID — тест сам получит список организаций:
  IIKO_API_LOGIN=ВАШ_КЛЮЧ python scripts/test_iiko.py
"""

import json
import logging
import os
import sys

from datetime import date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

sys.path.insert(0, os.path.dirname(__file__))

import requests
from iiko_client import (
    BASE_URL,
    collect_daily_data,
    collect_daily_data_iiko_web,
    get_payment_types_map,
    get_table_ids,
    get_terminal_group_ids,
    get_token,
    IikoWebSession,
    IIKO_WEB_URL,
)


def get_organizations(token: str) -> list[dict]:
    """Получить список организаций для API-логина."""
    resp = requests.post(
        f"{BASE_URL}/api/1/organizations",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"returnAdditionalInfo": True},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("organizations", [])


def main():
    api_login = os.environ.get("IIKO_API_LOGIN", "")
    org_id    = os.environ.get("IIKO_ORG_ID", "")

    if not api_login:
        print("❌ Не задан IIKO_API_LOGIN")
        print("   Запусти: IIKO_API_LOGIN=ВАШ_КЛЮЧ python scripts/test_iiko.py")
        sys.exit(1)

    sep = "=" * 55
    print(f"\n{sep}")
    print("  Тест подключения к iiko Cloud API")
    print(f"  Base URL: {BASE_URL}")
    print(f"{sep}\n")

    # -----------------------------------------------------------------------
    # 1. Авторизация
    # -----------------------------------------------------------------------
    print("1. Авторизация...")
    try:
        token = get_token(api_login)
        print(f"   ✅ Токен получен: {token[:20]}...\n")
    except Exception as e:
        print(f"   ❌ Ошибка авторизации: {e}")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # 2. Список организаций
    # -----------------------------------------------------------------------
    print("2. Список организаций...")
    try:
        orgs = get_organizations(token)
        for org in orgs:
            marker = " ← выбрана" if org.get("id") == org_id else ""
            print(f"   • {org.get('name', '?')} | id={org.get('id', '?')}{marker}")
        print()

        if not org_id and orgs:
            org_id = orgs[0]["id"]
            print(f"   ℹ️  IIKO_ORG_ID не задан — используем первую: {org_id}\n")
            print(f"   Добавьте в GitHub Secrets: IIKO_ORG_ID = {org_id}\n")
    except Exception as e:
        print(f"   ❌ Ошибка получения организаций: {e}\n")
        if not org_id:
            print("   Задайте IIKO_ORG_ID вручную и повторите.")
            sys.exit(1)

    if not org_id:
        print("   ❌ Нет организаций, доступных для этого API-логина")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # 3. Типы оплаты
    # -----------------------------------------------------------------------
    print("3. Типы оплаты...")
    try:
        pay_map = get_payment_types_map(token, org_id)
        for pid, name in list(pay_map.items())[:5]:
            print(f"   • {name} (id={pid[:8]}...)")
        print(f"   Итого типов: {len(pay_map)}\n")
    except Exception as e:
        print(f"   ⚠️  Ошибка: {e}\n")

    # -----------------------------------------------------------------------
    # 4. Терминальные группы → столы
    # -----------------------------------------------------------------------
    print("4. Терминальные группы...")
    try:
        tg_ids = get_terminal_group_ids(token, org_id)
        print(f"   Найдено терминальных групп: {len(tg_ids)}")
        for tid in tg_ids:
            print(f"   • {tid}")
        print()
    except Exception as e:
        print(f"   ⚠️  Ошибка: {e}\n")
        tg_ids = []

    print("5. Столы ресторана...")
    try:
        table_ids = get_table_ids(token, tg_ids)
        print(f"   Найдено столов: {len(table_ids)}")
        if table_ids:
            print(f"   Первые 3: {table_ids[:3]}")
        print()
    except Exception as e:
        print(f"   ⚠️  Ошибка: {e}\n")

    # -----------------------------------------------------------------------
    # 6. Проверка iikoWeb OLAP
    # -----------------------------------------------------------------------
    web_login = os.environ.get("IIKO_WEB_LOGIN", "")
    web_pass  = os.environ.get("IIKO_WEB_PASSWORD", "")
    store_id  = int(os.environ.get("IIKO_STORE_ID", "82455"))

    print("6. Проверка iikoWeb OLAP...")
    web_session = None
    if web_login and web_pass:
        try:
            web_session = IikoWebSession(IIKO_WEB_URL)
            web_session.login(web_login, web_pass)
            print(f"   ✅ iikoWeb авторизация успешна (store={store_id})\n")
        except Exception as e:
            print(f"   ❌ iikoWeb авторизация не удалась: {e}\n")
            web_session = None
    else:
        print("   ⚠️  IIKO_WEB_LOGIN / IIKO_WEB_PASSWORD не заданы\n")

    # -----------------------------------------------------------------------
    # 7. Сбор данных за вчера
    # -----------------------------------------------------------------------
    yesterday = date.today() - timedelta(days=1)
    print(f"7. Полный сбор данных за {yesterday}...")
    try:
        if web_session:
            data = collect_daily_data_iiko_web(web_session, store_id, yesterday)
        else:
            data = collect_daily_data(token, org_id, yesterday)

        summary = data.get("orders_summary") or {}
        print(f"   Чеков:      {summary.get('orders', '—')}")
        print(f"   Гостей:     {summary.get('guests', '—')}")
        print(f"   Выручка:    {summary.get('revenue', '—')} руб.")
        print(f"   Ср. чек:    {summary.get('avg_check', '—')} руб.")

        payments = data.get("payment_types") or {}
        if payments:
            print("   Оплата:")
            for name, amount in payments.items():
                print(f"     {name}: {amount} руб.")

        cats = data.get("category_revenue") or {}
        if cats:
            print("   Категории:")
            for cat, amount in cats.items():
                print(f"     {cat}: {amount} руб.")

        if data.get("errors"):
            print(f"\n   ⚠️  Ошибок при сборе: {len(data['errors'])}")
            for err in data["errors"]:
                print(f"      - {err}")
        else:
            print("\n   ✅ Все данные собраны без ошибок")

    except Exception as e:
        print(f"   ❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

    print(f"\n{sep}")
    print("  Тест завершён")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
