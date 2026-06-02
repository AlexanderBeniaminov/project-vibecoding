"""
monthly_collect.py — сбор ежемесячных метрик из iikoWeb OLAP.

Запускается командой:
    python3 scripts/main.py monthly 2026-04   # за апрель 2026
    python3 scripts/main.py monthly           # за прошлый месяц

Структура возвращаемого словаря соответствует 100 строкам листа «ЕжеМесячный».

3 OLAP-запроса на месяц:
  Q1 — OpenDate.Typed × HourClose          → итого, по дням, по слотам
  Q2 — DishCategory × DishName             → кухня/бар, блюда, себестоимость
  Q3 — OrderNum                             → размер группы, градация чеков
"""

import calendar
import logging
import os
import time
from datetime import date, timedelta
from typing import Optional

from iiko_client import (
    IikoWebSession,
    FILTER_NOT_DELETED,
    KITCHEN_CATEGORIES,
    BAR_CATEGORIES,
    _date_filter,
    _olap_query,
    _dish_name_is_kitchen,
)

logger = logging.getLogger(__name__)

OLAP_PAUSE = 15   # сек между запросами (защита от bandwidth quota)

# Часовые слоты (HourClose)
SLOT_MORNING = (9, 11)   # [9, 11)
SLOT_DAY     = (11, 17)  # [11, 17)
SLOT_EVENING = (17, 23)  # [17, 23)

# Порядок дней недели (weekday() → 0=пн, 6=вс)
WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _make_session() -> IikoWebSession:
    url      = os.environ.get("IIKO_WEB_URL")      or "https://kafe-monblan.iikoweb.ru"
    login    = os.environ.get("IIKO_WEB_LOGIN")    or "buh"
    password = os.environ.get("IIKO_WEB_PASSWORD") or "Vjy,kfy2024"
    store_id = int(os.environ.get("IIKO_STORE_ID") or "82455")
    sess = IikoWebSession(url, login, password, store_id)
    sess._login()
    return sess


def _slot(hour: int) -> Optional[str]:
    if SLOT_MORNING[0] <= hour < SLOT_MORNING[1]:
        return "morning"
    if SLOT_DAY[0]     <= hour < SLOT_DAY[1]:
        return "day"
    if SLOT_EVENING[0] <= hour < SLOT_EVENING[1]:
        return "evening"
    return None


def _safe(val, default=0):
    """Безопасно вернуть число или дефолт."""
    if val is None or val == "":
        return default
    try:
        return type(default)(val)
    except (ValueError, TypeError):
        return default


def _pct(num, den):
    return round(num / den, 10) if den else 0.0


def collect_monthly_data(year: int, month: int) -> dict:
    """
    Собрать все метрики за календарный месяц из iiko OLAP.
    Возвращает dict с ключами, соответствующими строкам листа «ЕжеМесячный».
    """
    days_in_month = calendar.monthrange(year, month)[1]
    d_from = date(year, month, 1)
    d_to   = date(year, month, days_in_month)
    ds_from = d_from.isoformat()
    ds_to   = d_to.isoformat()
    logger.info(f"[monthly] Сбор за {year}-{month:02d} ({ds_from} – {ds_to})")

    from config import get_capacity
    capacity = get_capacity(d_from)
    tables   = capacity["tables"]
    seats    = capacity["seats"]

    sess = _make_session()
    filters = [_date_filter(ds_from, ds_to)] + FILTER_NOT_DELETED

    # =========================================================
    # Q1: выручка/гости/чеки по дате и часу
    # =========================================================
    logger.info("[monthly] Q1: дата × час...")
    rows_q1 = _olap_query(
        sess, "SALES",
        group_fields=["OpenDate.Typed", "HourClose"],
        data_fields=["DishDiscountSumInt", "GuestNum", "UniqOrderId.OrdersCount"],
        filters=filters,
    )
    time.sleep(OLAP_PAUSE)

    # =========================================================
    # Q2: выручка/блюда по категории и названию
    # =========================================================
    logger.info("[monthly] Q2: категория × блюдо...")
    rows_q2_with_cost = _olap_query(
        sess, "SALES",
        group_fields=["DishCategory", "DishName"],
        data_fields=["DishDiscountSumInt", "DishAmountInt", "DishCostInt"],
        filters=filters,
    )
    if not rows_q2_with_cost:
        # DishCostInt может не быть в лицензии — повторяем без него
        logger.info("[monthly] Q2: DishCostInt недоступен, повтор без себестоимости...")
        rows_q2 = _olap_query(
            sess, "SALES",
            group_fields=["DishCategory", "DishName"],
            data_fields=["DishDiscountSumInt", "DishAmountInt"],
            filters=filters,
        )
        has_cost = False
    else:
        rows_q2   = rows_q2_with_cost
        has_cost  = True
    time.sleep(OLAP_PAUSE)

    # =========================================================
    # Q3: данные на уровне заказа (OrderNum)
    # =========================================================
    logger.info("[monthly] Q3: заказы...")
    rows_q3 = _olap_query(
        sess, "SALES",
        group_fields=["OrderNum"],
        data_fields=["DishDiscountSumInt", "GuestNum"],
        filters=filters,
    )

    logger.info(f"[monthly] Строк: Q1={len(rows_q1)}, Q2={len(rows_q2)}, Q3={len(rows_q3)}")

    # =========================================================
    # Агрегация Q1 → итоги и срезы
    # =========================================================
    rev_total = guests_total = checks_total = 0.0
    rev_slot   = {"morning": 0.0, "day": 0.0, "evening": 0.0}
    guest_slot = {"morning": 0,   "day": 0,   "evening": 0}
    check_slot = {"morning": 0,   "day": 0,   "evening": 0}

    # дни → выручка за день (для среднего по дню недели)
    daily_rev: dict[str, float] = {}

    for row in rows_q1:
        rev    = _safe(row.get("DishDiscountSumInt"), 0.0)
        guests = _safe(row.get("GuestNum"),           0)
        checks = _safe(row.get("UniqOrderId.OrdersCount"), 0)
        hour   = int(_safe(row.get("HourClose"), -1))
        day_str = str(row.get("OpenDate.Typed") or "")[:10]

        rev_total    += rev
        guests_total += guests
        checks_total += checks

        slot = _slot(hour)
        if slot:
            rev_slot[slot]   += rev
            guest_slot[slot] += guests
            check_slot[slot] += checks

        if day_str:
            daily_rev[day_str] = daily_rev.get(day_str, 0.0) + rev

    avg_check     = round(rev_total / checks_total, 2) if checks_total else 0.0

    # Суммарная выручка по дням недели (sum, не average)
    weekday_sums = {k: 0.0 for k in WEEKDAY_KEYS}
    for ds, rev in daily_rev.items():
        try:
            wd = date.fromisoformat(ds).weekday()  # 0=пн, 6=вс
            weekday_sums[WEEKDAY_KEYS[wd]] += rev
        except ValueError:
            pass
    sat_sum = weekday_sums["sat"]
    weekday_rel = {
        k: round(weekday_sums[k] / sat_sum, 10) if sat_sum else 0.0
        for k in WEEKDAY_KEYS
    }
    weekday_rel["sat"] = 1.0

    # =========================================================
    # Агрегация Q2 → кухня/бар + себестоимость
    # =========================================================
    rev_kitchen = rev_bar = 0.0
    cost_kitchen = cost_bar = 0.0
    dishes_kitchen = 0

    for row in rows_q2:
        cat_name  = (row.get("DishCategory") or "").strip().lower()
        dish_name = (row.get("DishName")     or "").strip().lower()
        rev       = _safe(row.get("DishDiscountSumInt"), 0.0)
        dishes    = int(_safe(row.get("DishAmountInt"), 0))
        cost      = _safe(row.get("DishCostInt"),      0.0) if has_cost else 0.0

        if cat_name in KITCHEN_CATEGORIES:
            is_kitchen = True
        elif not cat_name:
            is_kitchen = _dish_name_is_kitchen(dish_name)
        else:
            is_kitchen = False  # всё остальное → бар

        if is_kitchen:
            rev_kitchen  += rev
            cost_kitchen += cost
            dishes_kitchen += dishes
        else:
            rev_bar  += rev
            cost_bar += cost

    # Себестоимость и маржа (если DishCostInt доступен)
    if has_cost and (cost_kitchen + cost_bar) > 0:
        cost_total     = cost_kitchen + cost_bar
        margin_total   = rev_total  - cost_total
        margin_kitchen = rev_kitchen - cost_kitchen
        margin_bar     = rev_bar    - cost_bar
        foodcost_total   = _pct(cost_total,   rev_total)
        foodcost_kitchen = _pct(cost_kitchen, rev_kitchen)
        foodcost_bar     = _pct(cost_bar,     rev_bar)
        markup_total   = round(rev_total   / cost_total   - 1, 10) if cost_total   else 0.0
        markup_kitchen = round(rev_kitchen / cost_kitchen - 1, 10) if cost_kitchen else 0.0
        markup_bar     = round(rev_bar     / cost_bar     - 1, 10) if cost_bar     else 0.0
        margin_total_pct   = _pct(margin_total,   rev_total)
        margin_kitchen_pct = _pct(margin_kitchen, rev_kitchen)
        margin_bar_pct     = _pct(margin_bar,     rev_bar)
    else:
        (margin_total, margin_kitchen, margin_bar,
         margin_total_pct, margin_kitchen_pct, margin_bar_pct,
         foodcost_total, foodcost_kitchen, foodcost_bar,
         markup_total, markup_kitchen, markup_bar) = ("",) * 12

    # =========================================================
    # Агрегация Q3 → группы гостей + градация чеков
    # =========================================================
    rev_g1 = rev_g2 = rev_g3 = 0.0
    cnt_g1 = cnt_g2 = cnt_g3 = 0

    brackets = {"0_500": 0.0, "500_1000": 0.0, "1000_1500": 0.0,
                "1500_3000": 0.0, "3000_5000": 0.0, "5000_plus": 0.0}
    total_orders = len(rows_q3)

    for row in rows_q3:
        rev    = _safe(row.get("DishDiscountSumInt"), 0.0)
        guests = int(_safe(row.get("GuestNum"), 0))

        if guests == 1:
            rev_g1 += rev; cnt_g1 += 1
        elif guests == 2:
            rev_g2 += rev; cnt_g2 += 1
        else:
            rev_g3 += rev; cnt_g3 += 1

        if   rev <=  500: brackets["0_500"]    += rev
        elif rev <= 1000: brackets["500_1000"] += rev
        elif rev <= 1500: brackets["1000_1500"] += rev
        elif rev <= 3000: brackets["1500_3000"] += rev
        elif rev <= 5000: brackets["3000_5000"] += rev
        else:             brackets["5000_plus"] += rev

    rev_g_total = rev_g1 + rev_g2 + rev_g3  # ≈ rev_total

    # =========================================================
    # Производные метрики
    # =========================================================
    rev_morning = rev_slot["morning"]
    rev_day     = rev_slot["day"]
    rev_evening = rev_slot["evening"]

    guests_morning = guest_slot["morning"]
    guests_day     = guest_slot["day"]
    guests_evening = guest_slot["evening"]

    checks_morning = check_slot["morning"]
    checks_day     = check_slot["day"]
    checks_evening = check_slot["evening"]

    avg_per_guest        = round(rev_total   / guests_total,   2) if guests_total   else 0.0
    avg_per_guest_morn   = round(rev_morning / guests_morning, 2) if guests_morning else 0.0
    avg_per_guest_day    = round(rev_day     / guests_day,     2) if guests_day     else 0.0
    avg_per_guest_eve    = round(rev_evening / guests_evening, 2) if guests_evening else 0.0
    avg_per_guest_kitch  = round(rev_kitchen / guests_total,   2) if guests_total   else 0.0
    avg_per_guest_bar    = round(rev_bar     / guests_total,   2) if guests_total   else 0.0
    avg_check_per_dish   = round(rev_kitchen / dishes_kitchen, 2) if dishes_kitchen else 0.0
    avg_dishes_per_guest = round(dishes_kitchen / guests_total, 4) if guests_total  else 0.0

    # Оборачиваемость (столы по чекам, места по гостям, по дням месяца)
    def _turn(numerator, denominator, days):
        return round(numerator / denominator / days, 10) if denominator and days else 0.0

    turn_table      = _turn(checks_total,  tables, days_in_month)
    turn_table_morn = _turn(checks_morning, tables, days_in_month)
    turn_table_day  = _turn(checks_day,     tables, days_in_month)
    turn_table_eve  = _turn(checks_evening, tables, days_in_month)
    turn_seat       = _turn(guests_total,   seats,  days_in_month)
    turn_seat_morn  = _turn(guests_morning, seats,  days_in_month)
    turn_seat_day   = _turn(guests_day,     seats,  days_in_month)
    turn_seat_eve   = _turn(guests_evening, seats,  days_in_month)

    logger.info(
        f"[monthly] {year}-{month:02d}: выручка={int(rev_total)}, "
        f"чеков={int(checks_total)}, гостей={int(guests_total)}, "
        f"кухня={int(rev_kitchen)}, бар={int(rev_bar)}"
    )

    return {
        "year": year,
        "month": month,
        "date": f"{year}-{month:02d}",        # YYYY-MM (без числа)

        # Строки 3–7: выручка итого и по категориям
        "revenue_total":         round(rev_total, 2),
        "revenue_kitchen":       round(rev_kitchen, 2),
        "revenue_kitchen_pct":   _pct(rev_kitchen, rev_total),
        "revenue_bar":           round(rev_bar, 2),
        "revenue_bar_pct":       _pct(rev_bar, rev_total),

        # Строки 9–14: выручка по временным срезам
        "revenue_morning":       round(rev_morning, 2),
        "revenue_morning_pct":   _pct(rev_morning, rev_total),
        "revenue_day":           round(rev_day, 2),
        "revenue_day_pct":       _pct(rev_day, rev_total),
        "revenue_evening":       round(rev_evening, 2),
        "revenue_evening_pct":   _pct(rev_evening, rev_total),

        # Строки 16–29: средняя выручка по дням недели и относительно субботы
        "weekday_mon":      weekday_sums["mon"],
        "weekday_mon_pct":  weekday_rel["mon"],
        "weekday_tue":      weekday_sums["tue"],
        "weekday_tue_pct":  weekday_rel["tue"],
        "weekday_wed":      weekday_sums["wed"],
        "weekday_wed_pct":  weekday_rel["wed"],
        "weekday_thu":      weekday_sums["thu"],
        "weekday_thu_pct":  weekday_rel["thu"],
        "weekday_fri":      weekday_sums["fri"],
        "weekday_fri_pct":  weekday_rel["fri"],
        "weekday_sat":      weekday_sums["sat"],
        "weekday_sat_pct":  weekday_rel["sat"],
        "weekday_sun":      weekday_sums["sun"],
        "weekday_sun_pct":  weekday_rel["sun"],

        # Строки 30–41: маржа, наценка, фудкост (пусто если себестоимость недоступна)
        "margin_total":         margin_total,
        "margin_pct":           margin_total_pct if margin_total != "" else "",
        "margin_kitchen":       margin_kitchen,
        "margin_kitchen_pct":   margin_kitchen_pct if margin_kitchen != "" else "",
        "margin_bar":           margin_bar,
        "margin_bar_pct":       margin_bar_pct if margin_bar != "" else "",
        "markup_total":         markup_total,
        "markup_kitchen":       markup_kitchen,
        "markup_bar":           markup_bar,
        "foodcost_total":       foodcost_total,
        "foodcost_kitchen":     foodcost_kitchen,
        "foodcost_bar":         foodcost_bar,

        # Строки 42–48: гости итого и по слотам
        "guests_total":         int(guests_total),
        "guests_morning":       guests_morning,
        "guests_morning_pct":   _pct(guests_morning, guests_total),
        "guests_day":           guests_day,
        "guests_day_pct":       _pct(guests_day, guests_total),
        "guests_evening":       guests_evening,
        "guests_evening_pct":   _pct(guests_evening, guests_total),

        # Строки 49–52: средний чек на гостя
        "avg_check_per_guest":         avg_per_guest,
        "avg_check_per_guest_morning": avg_per_guest_morn,
        "avg_check_per_guest_day":     avg_per_guest_day,
        "avg_check_per_guest_evening": avg_per_guest_eve,

        # Строки 53–56: чеки итого и по слотам
        "checks_total":   int(checks_total),
        "checks_morning": checks_morning,
        "checks_day":     checks_day,
        "checks_evening": checks_evening,

        # Строки 57–62: блюда и производные
        "dishes_kitchen":        dishes_kitchen,
        "avg_check":             avg_check,
        "avg_check_per_dish":    avg_check_per_dish,
        "avg_per_guest_kitchen": avg_per_guest_kitch,
        "avg_per_guest_bar":     avg_per_guest_bar,
        "avg_dishes_per_guest":  avg_dishes_per_guest,

        # Строки 63–70: оборачиваемость
        "turnover_table":         turn_table,
        "turnover_table_morning": turn_table_morn,
        "turnover_table_day":     turn_table_day,
        "turnover_table_evening": turn_table_eve,
        "turnover_seat":          turn_seat,
        "turnover_seat_morning":  turn_seat_morn,
        "turnover_seat_day":      turn_seat_day,
        "turnover_seat_evening":  turn_seat_eve,

        # Строки 72–84: вклад групп гостей
        "revenue_1guest":    round(rev_g1, 2),
        "revenue_1guest_pct": _pct(rev_g1, rev_g_total),
        "revenue_2guests":   round(rev_g2, 2),
        "revenue_2guests_pct": _pct(rev_g2, rev_g_total),
        "revenue_3plus":     round(rev_g3, 2),
        "revenue_3plus_pct": _pct(rev_g3, rev_g_total),
        "group_loyalty":     "",   # расчёт не определён
        "checks_1guest":     cnt_g1,
        "checks_1guest_pct": _pct(cnt_g1, total_orders),
        "checks_2guests":    cnt_g2,
        "checks_2guests_pct": _pct(cnt_g2, total_orders),
        "checks_3plus":      cnt_g3,
        "checks_3plus_pct":  _pct(cnt_g3, total_orders),

        # Строки 86–97: градация чеков по сумме
        "bracket_0_500":         round(brackets["0_500"],     2),
        "bracket_0_500_pct":     _pct(brackets["0_500"],     rev_g_total),
        "bracket_500_1000":      round(brackets["500_1000"],  2),
        "bracket_500_1000_pct":  _pct(brackets["500_1000"],  rev_g_total),
        "bracket_1000_1500":     round(brackets["1000_1500"], 2),
        "bracket_1000_1500_pct": _pct(brackets["1000_1500"], rev_g_total),
        "bracket_1500_3000":     round(brackets["1500_3000"], 2),
        "bracket_1500_3000_pct": _pct(brackets["1500_3000"], rev_g_total),
        "bracket_3000_5000":     round(brackets["3000_5000"], 2),
        "bracket_3000_5000_pct": _pct(brackets["3000_5000"], rev_g_total),
        "bracket_5000_plus":     round(brackets["5000_plus"], 2),
        "bracket_5000_plus_pct": _pct(brackets["5000_plus"],  rev_g_total),

        # Строки 98–100: константы
        "tables":        tables,
        "seats":         seats,
        "days_in_month": days_in_month,
    }
