"""
diagnose_categories.py — диагностика категорий iiko для конкретных дат.

Запуск:
  python3 scripts/diagnose_categories.py 2026-04-01 2026-04-02 2026-04-04
"""

import logging
import os
import sys

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, os.path.dirname(__file__))

from iiko_client import IikoWebSession, IIKO_WEB_URL, _olap_query, _date_filter, FILTER_NOT_DELETED

DATES = sys.argv[1:] or ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-04"]

session = IikoWebSession(
    IIKO_WEB_URL,
    os.environ.get("IIKO_WEB_LOGIN") or "buh",
    os.environ.get("IIKO_WEB_PASSWORD") or "Vjy,kfy2024",
    int(os.environ.get("IIKO_STORE_ID") or "82455"),
)
session._login()
print(f"✅ Авторизован\n")

for ds in DATES:
    df = [_date_filter(ds, ds)] + FILTER_NOT_DELETED
    print(f"{'='*60}")
    print(f"  {ds}")
    print(f"{'='*60}")

    # 1. Сводка (выручка / чеки / гости)
    rows = _olap_query(session, "SALES",
        group_fields=["OpenDate.Typed"],
        data_fields=["DishDiscountSumInt", "UniqOrderId.OrdersCount", "GuestNum"],
        filters=df)
    rev = sum(r.get("DishDiscountSumInt") or 0 for r in rows)
    chk = sum(r.get("UniqOrderId.OrdersCount") or 0 for r in rows)
    gst = sum(r.get("GuestNum") or 0 for r in rows)
    print(f"  Выручка: {int(rev):,}  Чеков: {int(chk)}  Гостей: {int(gst)}")
    print()

    # 2. DishCategory — поле отображения
    rows2 = _olap_query(session, "SALES",
        group_fields=["DishCategory"],
        data_fields=["DishDiscountSumInt"],
        filters=df)
    rows2_sorted = sorted(rows2, key=lambda r: r.get("DishDiscountSumInt") or 0, reverse=True)
    print(f"  DishCategory (отображение):")
    for r in rows2_sorted:
        cat = r.get("DishCategory") or "(пусто)"
        amt = r.get("DishDiscountSumInt") or 0
        pct = amt / rev * 100 if rev else 0
        print(f"    {cat:<30} {int(amt):>8,} руб.  ({pct:.1f}%)")
    print()

    # 3. DishCategory.Accounting — бухгалтерская категория
    try:
        rows3 = _olap_query(session, "SALES",
            group_fields=["DishCategory.Accounting"],
            data_fields=["DishDiscountSumInt"],
            filters=df)
        rows3_sorted = sorted(rows3, key=lambda r: r.get("DishDiscountSumInt") or 0, reverse=True)
        print(f"  DishCategory.Accounting (бухгалтерия):")
        for r in rows3_sorted:
            cat = r.get("DishCategory.Accounting") or "(пусто)"
            amt = r.get("DishDiscountSumInt") or 0
            pct = amt / rev * 100 if rev else 0
            print(f"    {cat:<30} {int(amt):>8,} руб.  ({pct:.1f}%)")
    except Exception as e:
        print(f"  DishCategory.Accounting: ошибка — {e}")
    print()
