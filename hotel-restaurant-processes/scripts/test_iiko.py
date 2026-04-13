"""
test_iiko.py — тест подключения к iikoWeb OLAP.

Запуск из папки hotel-restaurant-processes/:
  IIKO_WEB_LOGIN=buh IIKO_WEB_PASSWORD=Vjy,kfy2024 IIKO_STORE_ID=82455 \
    python scripts/test_iiko.py

Тест проверяет дату yesterday и yesterday-365 (чтобы найти данные).
"""

import logging
import os
import sys
from datetime import date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

sys.path.insert(0, os.path.dirname(__file__))

from iiko_client import IikoWebSession, IIKO_WEB_URL, collect_daily_data_iiko_web, _olap_query


def main():
    web_login    = os.environ.get("IIKO_WEB_LOGIN",    "")
    web_password = os.environ.get("IIKO_WEB_PASSWORD", "")
    store_id     = int(os.environ.get("IIKO_STORE_ID", "82455"))

    sep = "=" * 55
    print(f"\n{sep}")
    print("  Тест iikoWeb OLAP")
    print(f"  URL: {IIKO_WEB_URL}")
    print(f"{sep}\n")

    if not web_login or not web_password:
        print("❌ Задай переменные: IIKO_WEB_LOGIN и IIKO_WEB_PASSWORD")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 1. Авторизация
    # ------------------------------------------------------------------
    print("1. Авторизация в iikoWeb...")
    try:
        session = IikoWebSession(IIKO_WEB_URL, web_login, web_password, store_id)
        session._login()
        print(f"   ✅ Авторизован: {web_login} (store={store_id})\n")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. Проверка OLAP — ищем дату с данными
    # ------------------------------------------------------------------
    print("2. Поиск даты с данными (последние 30 дней)...")
    found_date = None
    for days_ago in range(1, 31):
        check_date = date.today() - timedelta(days=days_ago)
        ds = check_date.strftime("%Y-%m-%d")
        try:
            from iiko_client import _date_filter, FILTER_NOT_DELETED
            rows = _olap_query(
                session, "SALES",
                group_fields=["OpenDate.Typed"],
                data_fields=["DishDiscountSumInt", "UniqOrderId.OrdersCount"],
                filters=[_date_filter(ds, ds)] + FILTER_NOT_DELETED,
            )
            if rows and any(r.get("UniqOrderId.OrdersCount", 0) for r in rows):
                rev = sum(r.get("DishDiscountSumInt", 0) or 0 for r in rows)
                trn = sum(r.get("UniqOrderId.OrdersCount", 0) or 0 for r in rows)
                print(f"   ✅ Найдены данные: {ds} → {int(rev)} руб., {int(trn)} чеков\n")
                found_date = check_date
                break
            else:
                print(f"   — {ds}: нет данных")
        except Exception as e:
            print(f"   ⚠️  {ds}: {e}")

    if not found_date:
        print("   ⚠️  За последние 30 дней данных нет (ресторан не работал?)\n")
        found_date = date.today() - timedelta(days=1)

    # ------------------------------------------------------------------
    # 3. Полный сбор данных за найденную дату
    # ------------------------------------------------------------------
    print(f"3. Полный сбор данных за {found_date}...")
    try:
        data = collect_daily_data_iiko_web(session, found_date)

        summary = data.get("orders_summary") or {}
        print(f"   Выручка:  {summary.get('revenue', '—')} руб.")
        print(f"   Чеков:    {summary.get('orders', '—')}")
        print(f"   Гостей:   {summary.get('guests', '—')}")
        print(f"   Ср. чек:  {summary.get('avg_check', '—')} руб.")

        payments = data.get("payment_types") or {}
        if payments:
            print("   Оплата:")
            for name, amount in payments.items():
                print(f"     {name}: {int(amount)} руб.")

        cats = data.get("category_revenue") or {}
        if cats:
            print("   Категории:")
            for cat, amount in cats.items():
                print(f"     {cat}: {int(amount)} руб.")

        top = data.get("top_dishes") or []
        if top:
            print("   Топ-3 блюд:")
            for d in top[:3]:
                print(f"     {d['dish']}: {int(d['revenue'])} руб. ({int(d['count'])} шт.)")

        if data.get("cancellations") is not None:
            print(f"   Отмены: {data['cancellations']} руб.")

        errors = data.get("errors", [])
        if errors:
            print(f"\n   ⚠️  Ошибок при сборе: {len(errors)}")
            for err in errors:
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
