"""
main.py — точка входа.

Использование:
  python3 scripts/main.py collect             # сбор iiko → Sheets за вчера (23:30)
  python3 scripts/main.py collect 2026-04-13  # сбор за конкретную дату
  python3 scripts/main.py report              # чтение Sheets → отчёт в MAX (10:00)
  python3 scripts/main.py report 2026-04-13   # отчёт за конкретную дату
  python3 scripts/main.py weekly              # агрегация за прошлую неделю

Алгоритм:
  23:30 — collect: iiko OLAP → Google Sheets (авто-данные)
  до 10:00 — администратор вручную заполняет ручные данные в Google Sheets
  10:00 — report: читает Sheets (авто + ручной ввод) → отправляет отчёт собственнику
"""

import argparse
import logging
import os
import sys
from datetime import date, datetime

# Логирование — в stdout и в файл
os.makedirs("logs", exist_ok=True)

_log_date = datetime.now().strftime("%Y-%m-%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(f"logs/report_{_log_date}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Импорты после настройки логирования
# ---------------------------------------------------------------------------
from typing import Optional

from config import (
    SHEETS_ID, GOOGLE_SERVICE_ACCOUNT_JSON,
    MAX_BOT_TOKEN, MAX_OWNER_USER_ID,
    MAX_DEV_USER_ID,
    RESTAURANT_NAME, get_capacity,
)
from iiko_client import collect_daily_data
from max_bot import MaxBot, send_or_log
from sheets_writer import (
    get_service, setup_spreadsheet,
    write_daily_row, write_weekly_row, read_daily_row,
    delete_columns_before_date,
)
from utils import yesterday_utc5, fmt_date, week_bounds, fmt_date_ru, fmt_money, fmt_int


# ---------------------------------------------------------------------------
# Инициализация клиентов
# ---------------------------------------------------------------------------

def _get_sheets_service():
    """Подключиться к Google Sheets API."""
    if GOOGLE_SERVICE_ACCOUNT_JSON:
        return get_service(credentials_json=GOOGLE_SERVICE_ACCOUNT_JSON)
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    return get_service(credentials_path=creds_path)


def _make_bot() -> Optional[MaxBot]:
    """Создать MaxBot или вернуть None если токен не настроен."""
    if not MAX_BOT_TOKEN:
        logger.warning("MAX_BOT_TOKEN не задан — уведомления отключены")
        return None
    try:
        return MaxBot(MAX_BOT_TOKEN)
    except Exception as e:
        logger.error(f"Ошибка инициализации MaxBot: {e}")
        return None


def _alert_dev(bot: Optional[MaxBot], message: str):
    """Отправить алерт разработчику при критической ошибке."""
    dev_id = MAX_DEV_USER_ID or MAX_OWNER_USER_ID
    send_or_log(bot, dev_id, f"🔴 {RESTAURANT_NAME}: {message}", label="alert_dev")


SHEETS_URL = f"https://docs.google.com/spreadsheets/d/{SHEETS_ID}/edit"


# ---------------------------------------------------------------------------
# collect — шаг 1: iiko → Google Sheets (запускается в 23:30)
# ---------------------------------------------------------------------------

def daily_collect(report_date: date):
    """
    Собрать авто-данные из iiko и записать в Google Sheets.
    Без взаимодействия с MAX — только данные.
    """
    logger.info(f"=== СТАРТ collect за {report_date} ===")
    bot = _make_bot()

    # 1. Собрать данные iiko
    logger.info("Шаг 1: сбор данных через iikoWeb OLAP...")
    try:
        data = collect_daily_data(report_date)
        logger.info("Данные iiko собраны успешно")
    except Exception as e:
        logger.error(f"Критическая ошибка iiko: {e}", exc_info=True)
        _alert_dev(bot, f"Ошибка сбора данных iiko за {report_date}: {e}")
        sys.exit(1)

    # 2. Записать в Google Sheets
    logger.info("Шаг 2: запись в Google Sheets...")
    try:
        service = _get_sheets_service()
        setup_spreadsheet(service, SHEETS_ID)
        write_daily_row(service, SHEETS_ID, data)
        logger.info("Данные записаны в Google Sheets")
    except Exception as e:
        logger.error(f"Ошибка Google Sheets: {e}", exc_info=True)
        _alert_dev(bot, f"Ошибка записи в Sheets за {report_date}: {e}")
        sys.exit(1)

    logger.info(f"=== ФИНИШ collect за {report_date} ===")


# ---------------------------------------------------------------------------
# report — шаг 2: читает Sheets → отправляет отчёт в MAX (запускается в 10:00)
# ---------------------------------------------------------------------------

def daily_report(report_date: date):
    """
    Прочитать Google Sheets (авто-данные + ручной ввод администратора)
    и отправить итоговый отчёт собственнику в MAX.
    Если ручной ввод не заполнен — отчёт всё равно отправляется.
    """
    logger.info(f"=== СТАРТ report за {report_date} ===")
    bot = _make_bot()

    # Читаем все данные из Sheets
    logger.info("Чтение данных из Google Sheets...")
    try:
        service = _get_sheets_service()
        sheet_data = read_daily_row(service, SHEETS_ID, str(report_date))
        logger.info(f"Прочитано метрик: {len(sheet_data)}")
    except Exception as e:
        logger.error(f"Ошибка чтения из Sheets: {e}", exc_info=True)
        _alert_dev(bot, f"Ошибка чтения отчёта из Sheets за {report_date}: {e}")
        sys.exit(1)

    # Формируем и отправляем отчёт
    try:
        report_text = _build_owner_report(sheet_data, report_date)
        send_or_log(bot, MAX_OWNER_USER_ID, report_text, label="owner_daily_report")
        logger.info("Отчёт отправлен собственнику")
    except Exception as e:
        logger.error(f"Ошибка отправки отчёта: {e}", exc_info=True)
        _alert_dev(bot, f"Ошибка отправки отчёта за {report_date}: {e}")

    logger.info(f"=== ФИНИШ report за {report_date} ===")


# ---------------------------------------------------------------------------
# weekly — еженедельный дайджест
# ---------------------------------------------------------------------------

def weekly(for_date: date = None):
    monday, sunday = week_bounds(for_date)
    week_num = monday.isocalendar()[1]
    logger.info(f"=== СТАРТ weekly неделя {week_num} ({monday}–{sunday}) ===")
    bot = _make_bot()

    # 1. Читаем данные из листа «Ежедневно» и агрегируем
    logger.info("Шаг 1: чтение и агрегация данных из Google Sheets...")
    try:
        service = _get_sheets_service()
        weekly_data = _aggregate_weekly(service, monday, sunday, week_num)
        logger.info("Агрегация выполнена")
    except Exception as e:
        logger.error(f"Ошибка агрегации: {e}", exc_info=True)
        _alert_dev(bot, f"Ошибка агрегации за неделю {week_num}: {e}")
        sys.exit(1)

    # 2. Записать в лист «Еженедельно»
    logger.info("Шаг 2: запись в лист «Еженедельно»...")
    try:
        write_weekly_row(service, SHEETS_ID, weekly_data)
        logger.info("Еженедельные данные записаны")
    except Exception as e:
        logger.error(f"Ошибка записи еженедельных данных: {e}", exc_info=True)
        _alert_dev(bot, f"Ошибка записи weekly в Sheets: {e}")
        sys.exit(1)

    # 3. Отправить дайджест собственнику
    logger.info("Шаг 3: отправка еженедельного дайджеста...")
    try:
        digest = _build_weekly_digest(weekly_data, monday, sunday, week_num)
        send_or_log(bot, MAX_OWNER_USER_ID, digest, label="owner_weekly_digest")
    except Exception as e:
        logger.error(f"Ошибка отправки дайджеста: {e}", exc_info=True)

    logger.info(f"=== ФИНИШ weekly неделя {week_num} ===")


# ---------------------------------------------------------------------------
# Формирование текстов
# ---------------------------------------------------------------------------

def _num(sheet_data: dict, key: str, default: float = 0) -> float:
    """Безопасно прочитать число из словаря данных Sheets."""
    try:
        val = sheet_data.get(key, default)
        if val == "" or val is None:
            return default
        return float(str(val).replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return default


def _build_owner_report(sheet_data: dict, report_date: date) -> str:
    """
    Сформировать ежедневный отчёт для собственника.
    Читает данные из Google Sheets — включает и авто (строки 2–16),
    и ручной ввод администратора (строки 17–25).
    """
    SEP = "——————————————"

    revenue   = _num(sheet_data, "Выручка итого")
    orders    = _num(sheet_data, "Кол-во чеков")
    avg_chk   = _num(sheet_data, "Средний чек")
    guests    = _num(sheet_data, "Гости")
    kitchen   = _num(sheet_data, "Кухня")
    bar       = _num(sheet_data, "Бар")
    cancels   = _num(sheet_data, "Отмены (руб)")
    writeoffs = _num(sheet_data, "Списания (руб)")

    inkass     = _num(sheet_data, "Инкассация")
    expenses   = _num(sheet_data, "Расход из кассы")
    balance    = _num(sheet_data, "Остаток нал")
    staff      = _num(sheet_data, "Персонал кол-во итого")
    breakfasts = _num(sheet_data, "Завтраки (кол-во гостей по жетонам)")

    # Ручные данные считаются заполненными если есть хоть одно ненулевое значение
    has_manual = inkass > 0 or balance > 0 or staff > 0 or expenses > 0

    lines = [
        f"📊 {RESTAURANT_NAME} — {fmt_date_ru(report_date)}",
        SEP,
        f"💰 Выручка:      {fmt_money(revenue)}",
        f"🧾 Чеков:        {fmt_int(orders)}",
        f"💵 Средний чек:  {fmt_money(avg_chk)}",
        f"👥 Гостей:       {fmt_int(guests)}",
        f"🍽 Кухня:        {fmt_money(kitchen)}",
        f"🍹 Бар:          {fmt_money(bar)}",
    ]

    lines.append(SEP)
    if has_manual:
        lines += [
            f"🏦 Инкассация:   {fmt_money(inkass)}",
            f"📤 Расход:       {fmt_money(expenses)}",
            f"💵 Остаток нал:  {fmt_money(balance)}",
            f"👤 Персонал:     {fmt_int(staff)} чел.",
        ]
        if breakfasts:
            lines.append(f"🍳 Завтраки:     {fmt_int(breakfasts)} гостей")
    else:
        lines.append("⚠️ Ручные данные не заполнены")

    lines += [
        SEP,
        f"❌ Отмены:       {fmt_money(cancels)}",
        f"🗑 Списания:     {fmt_money(writeoffs)}",
        SEP,
        f"📎 {SHEETS_URL}",
    ]
    return "\n".join(lines)


def _aggregate_weekly(service, monday: date, sunday: date, week_num: int) -> dict:
    """
    Прочитать лист «Ежедневно» и собрать агрегаты за неделю.
    Структура листа: строка 1 — даты, колонка A — названия метрик.
    """
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEETS_ID,
        range="Ежедневно!A:AZ",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows = result.get("values", [])

    if not rows or len(rows) < 2:
        logger.warning("Лист «Ежедневно» пустой или только заголовок")
        return _empty_weekly(week_num, monday, sunday)

    # Строка 1: ["Дата", "2026-03-30", "2026-03-31", ...]
    date_row = rows[0]

    # Находим индексы колонок для дат внутри недели пн–вс
    week_col_indices = []
    for i, cell in enumerate(date_row):
        if i == 0:
            continue  # пропускаем колонку A
        try:
            d = date.fromisoformat(str(cell).strip())
            if monday <= d <= sunday:
                week_col_indices.append(i)
        except ValueError:
            pass

    if not week_col_indices:
        logger.warning(f"Нет данных за неделю {monday}–{sunday}")
        return _empty_weekly(week_num, monday, sunday)

    # Строим словарь: название метрики → список значений за каждый день недели
    metric_values: dict = {}
    for row in rows[1:]:
        if not row:
            continue
        metric_name = str(row[0]).strip() if row else ""
        if not metric_name:
            continue
        vals = []
        for col_idx in week_col_indices:
            if col_idx < len(row):
                try:
                    v = float(str(row[col_idx]).replace(" ", "").replace(",", ".") or 0)
                except (ValueError, TypeError):
                    v = 0.0
            else:
                v = 0.0
            vals.append(v)
        metric_values[metric_name] = vals

    def _sum(key: str) -> float:
        return sum(metric_values.get(key, []))

    n = len(week_col_indices)
    revenue     = _sum("Выручка итого")
    orders      = _sum("Кол-во чеков")
    guests      = _sum("Гости")
    kitchen     = _sum("Кухня")
    bar         = _sum("Бар")
    cancels     = _sum("Отмены (руб)")
    writeoffs_s = _sum("Списания (руб)")
    zp_total    = _sum("З/п итого")
    rev_morning = _sum("Утро — выручка (09–11)")
    rev_day     = _sum("День — выручка (11–17)")
    rev_evening = _sum("Вечер — выручка (17–23)")

    avg_check       = round(revenue / orders, 2) if orders else 0
    avg_check_guest = round(revenue / guests, 2) if guests else 0

    capacity = get_capacity(monday)
    tables   = capacity["tables"]
    seats    = capacity["seats"]
    turnover_table = round(guests / tables / n, 2) if tables and n else 0
    turnover_seat  = round(guests / seats  / n, 2) if seats  and n else 0

    logger.info(
        f"Неделя {week_num}: {n} дней, выручка={revenue}, "
        f"чеков={int(orders)}, гостей={int(guests)}"
    )

    return {
        "week_num":        week_num,
        "date_from":       str(monday),
        "date_to":         str(sunday),
        "revenue":         revenue,
        "avg_revenue_day": round(revenue / n, 2) if n else 0,
        "orders":          int(orders),
        "avg_orders_day":  round(orders / n, 2) if n else 0,
        "guests":          int(guests),
        "avg_guests_day":  round(guests / n, 2) if n else 0,
        "avg_check":       avg_check,
        "avg_check_guest": avg_check_guest,
        "kitchen":         kitchen,
        "bar":             bar,
        "cancellations":   cancels,
        "writeoffs":       writeoffs_s,
        "rev_morning":     rev_morning,
        "rev_day":         rev_day,
        "rev_evening":     rev_evening,
        "turnover_table":  turnover_table,
        "turnover_seat":   turnover_seat,
        "zp_total":        zp_total,
    }


def _empty_weekly(week_num, monday, sunday) -> dict:
    return {
        "week_num": week_num, "date_from": str(monday), "date_to": str(sunday),
        "revenue": 0, "avg_revenue_day": 0, "orders": 0, "avg_orders_day": 0,
        "guests": 0, "avg_guests_day": 0, "avg_check": 0, "avg_check_guest": 0,
        "kitchen": 0, "bar": 0, "cancellations": 0, "writeoffs": 0,
        "rev_morning": 0, "rev_day": 0, "rev_evening": 0,
        "turnover_table": 0, "turnover_seat": 0, "zp_total": 0,
    }


def _build_weekly_digest(data: dict, monday: date, sunday: date, week_num: int) -> str:
    """Сформировать еженедельный дайджест для собственника."""
    revenue = data.get("revenue", 0)
    orders  = data.get("orders", 0)
    guests  = data.get("guests", 0)
    avg_chk = data.get("avg_check", 0)
    avg_rev = data.get("avg_revenue_day", 0)

    return "\n".join([
        f"📊 {RESTAURANT_NAME} — неделя {week_num}",
        f"{fmt_date_ru(monday)} – {fmt_date_ru(sunday)}",
        "",
        f"💰 Выручка за неделю: {fmt_money(revenue)}",
        f"   Ср. выручка/день: {fmt_money(avg_rev)}",
        "",
        f"🧾 Чеков: {fmt_int(orders)} | Ср. чек: {fmt_money(avg_chk)}",
        f"👥 Гостей за неделю: {fmt_int(guests)}",
        "",
        f"📎 Таблица: {SHEETS_URL}",
    ])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def trim_sheet(cutoff_date_str: str):
    """
    Удалить из листа «Ежедневно» столбцы с датами раньше cutoff_date_str.
    Пример: python3 scripts/main.py trim 2026-04-01
    """
    try:
        cutoff = date.fromisoformat(cutoff_date_str)
    except ValueError:
        logger.error(f"Неверный формат даты: {cutoff_date_str}. Используйте YYYY-MM-DD.")
        sys.exit(1)

    logger.info(f"=== Удаление столбцов до {cutoff} из листа «Ежедневно» ===")
    service = _get_sheets_service()
    deleted = delete_columns_before_date(service, SHEETS_ID, cutoff)
    logger.info(f"Удалено столбцов: {deleted}. Таблица теперь начинается с {cutoff}.")


def main():
    parser = argparse.ArgumentParser(description="Монблан — автоматический отчёт")
    parser.add_argument(
        "mode",
        choices=["collect", "report", "weekly", "trim"],
        help=(
            "collect — сбор iiko → Sheets (23:30); "
            "report  — чтение Sheets → отчёт в MAX (10:00); "
            "weekly  — агрегация за прошлую неделю; "
            "trim    — удалить столбцы до указанной даты"
        ),
    )
    parser.add_argument(
        "date", nargs="?", default=None,
        help="Дата YYYY-MM-DD (для collect/report/weekly — дата отчёта; для trim — дата отсечки)"
    )
    args = parser.parse_args()

    if args.mode == "trim":
        cutoff = args.date or "2026-04-01"
        trim_sheet(cutoff)
        return

    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            logger.error(f"Неверный формат даты: {args.date}. Используйте YYYY-MM-DD.")
            sys.exit(1)
    else:
        target_date = yesterday_utc5()

    bot = _make_bot()
    try:
        if args.mode == "collect":
            daily_collect(target_date)
        elif args.mode == "report":
            daily_report(target_date)
        else:
            weekly(target_date)
    except Exception as e:
        logger.critical(f"Необработанная ошибка: {e}", exc_info=True)
        _alert_dev(bot, str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
