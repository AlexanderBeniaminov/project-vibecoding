"""
main.py — точка входа.

Использование:
  python3 scripts/main.py daily              # отчёт за вчера
  python3 scripts/main.py daily 2026-03-29   # отчёт за конкретную дату
  python3 scripts/main.py weekly             # агрегация за прошлую неделю
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
from config import (
    SHEETS_ID, GOOGLE_SERVICE_ACCOUNT_JSON,
    MAX_BOT_TOKEN, MAX_OWNER_USER_ID,
    MAX_ADMIN_USER_ID, MAX_DEV_USER_ID,
    RESTAURANT_NAME, get_capacity,
)
from iiko_client import collect_daily_data
from max_bot import MaxBot, send_or_log
from sheets_writer import get_service, setup_spreadsheet, write_daily_row, write_weekly_row
from utils import yesterday_utc5, fmt_date, week_bounds, fmt_date_ru, fmt_money, fmt_int, parse_admin_reply


# ---------------------------------------------------------------------------
# Инициализация клиентов
# ---------------------------------------------------------------------------

def _get_sheets_service():
    """Подключиться к Google Sheets API."""
    if GOOGLE_SERVICE_ACCOUNT_JSON:
        return get_service(credentials_json=GOOGLE_SERVICE_ACCOUNT_JSON)
    # Локальный запуск — файл credentials.json рядом со скриптом
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    return get_service(credentials_path=creds_path)


def _make_bot() -> MaxBot | None:
    """Создать MaxBot или вернуть None если токен не настроен."""
    if not MAX_BOT_TOKEN:
        logger.warning("MAX_BOT_TOKEN не задан — уведомления отключены")
        return None
    try:
        return MaxBot(MAX_BOT_TOKEN)
    except Exception as e:
        logger.error(f"Ошибка инициализации MaxBot: {e}")
        return None


def _alert_dev(bot: MaxBot | None, message: str):
    """Отправить алерт разработчику при критической ошибке."""
    dev_id = MAX_DEV_USER_ID or MAX_OWNER_USER_ID
    send_or_log(bot, dev_id, f"🔴 {RESTAURANT_NAME}: {message}", label="alert_dev")


# ---------------------------------------------------------------------------
# daily — ежедневный отчёт
# ---------------------------------------------------------------------------

# Время ожидания ответа администратора (секунды)
ADMIN_POLL_TIMEOUT_SEC = 30 * 60  # 30 минут

SHEETS_URL = f"https://docs.google.com/spreadsheets/d/{SHEETS_ID}/edit"


def daily(report_date: date):
    logger.info(f"=== СТАРТ daily за {report_date} ===")
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

    # 2. Записать автоматические данные в Sheets
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

    # 3. Запросить ручные данные у администратора и ждать ответ
    logger.info("Шаг 3: запрос ручных данных у администратора...")
    manual_data = None

    if bot and MAX_ADMIN_USER_ID:
        try:
            # Сбросить старые обновления, чтобы не принять вчерашний ответ
            bot.flush_updates()

            admin_request = _build_admin_request(report_date)
            bot.send_message(MAX_ADMIN_USER_ID, admin_request)
            logger.info("Запрос отправлен администратору, ожидание ответа...")

            reply_text = bot.poll_for_reply(
                from_user_id=MAX_ADMIN_USER_ID,
                timeout_sec=ADMIN_POLL_TIMEOUT_SEC,
            )

            if reply_text:
                manual_data = parse_admin_reply(reply_text)
                if manual_data:
                    logger.info(f"Ответ администратора разобран: {manual_data}")
                    # Дописать ручные данные в Sheets
                    data["manual"] = manual_data
                    try:
                        write_daily_row(service, SHEETS_ID, data)
                        logger.info("Ручные данные записаны в Google Sheets")
                    except Exception as e:
                        logger.error(f"Ошибка записи ручных данных: {e}", exc_info=True)
                else:
                    logger.warning(f"Не удалось разобрать ответ: {reply_text!r}")
                    send_or_log(bot, MAX_ADMIN_USER_ID,
                                "⚠️ Не смог разобрать ответ. Пришлите данные в точном формате из предыдущего сообщения.",
                                label="admin_parse_error")
            else:
                logger.warning("Администратор не ответил за 30 минут")
                # Ячейки помечаем как не заполненные
                data["manual"] = {"статус": "⚠️ не заполнено"}
                try:
                    write_daily_row(service, SHEETS_ID, data)
                except Exception as e:
                    logger.error(f"Ошибка записи статуса отсутствия данных: {e}")

        except Exception as e:
            logger.error(f"Ошибка при работе с MAX: {e}", exc_info=True)
    else:
        logger.warning("MAX не настроен или ADMIN_USER_ID отсутствует — ручной ввод пропущен")

    # 4. Отправить итоговый отчёт собственнику
    logger.info("Шаг 4: отправка отчёта собственнику...")
    try:
        report_text = _build_owner_report(data, report_date)
        send_or_log(bot, MAX_OWNER_USER_ID, report_text, label="owner_daily_report")
    except Exception as e:
        logger.error(f"Ошибка отправки отчёта: {e}", exc_info=True)

    logger.info(f"=== ФИНИШ daily за {report_date} ===")


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

def _build_owner_report(data: dict, report_date: date) -> str:
    """Сформировать ежедневный отчёт для собственника."""
    summary  = data.get("orders_summary") or {}
    payments = data.get("payment_types") or {}
    cats     = data.get("category_revenue") or {}

    revenue  = summary.get("revenue", 0)
    orders   = summary.get("orders", 0)
    avg_chk  = summary.get("avg_check", 0)
    guests   = summary.get("guests", 0)

    nal      = payments.get("Наличные", payments.get("Нал", 0))
    sbp      = payments.get("СБП", payments.get("Безналичный", 0))
    card     = payments.get("Банковская карта", payments.get("Карта", 0))
    invoice  = payments.get("По счёту", payments.get("Безнал", 0))

    kitchen = sum(v for k, v in cats.items() if any(w in k.lower() for w in ["кухня", "kitchen", "еда"]))
    bar     = sum(v for k, v in cats.items() if any(w in k.lower() for w in ["бар", "bar", "напитки"]))

    # None = недоступно в iiko Cloud API
    cancellations = data.get("cancellations")
    writeoffs     = data.get("writeoffs")

    manual   = data.get("manual") or {}
    # Проверяем, что это реальные ручные данные, а не маркер отсутствия
    has_manual = bool(manual) and "статус" not in manual

    inkass   = manual.get("инкассация", "—")
    balance  = manual.get("остаток_нал", "—")
    staff_total = 0
    zp_total    = 0
    for role in ["повара", "официанты", "бармены", "посудомойщицы"]:
        r = manual.get(role, {})
        if isinstance(r, dict):
            staff_total += r.get("кол", 0)
            zp_total    += r.get("зп", 0)

    lines = [
        f"📊 {RESTAURANT_NAME} — {fmt_date_ru(report_date)}",
        "",
        f"💰 Выручка: {fmt_money(revenue)}",
        f"   Нал: {fmt_money(nal)} | СБП: {fmt_money(sbp)}",
        f"   Карта: {fmt_money(card)} | Счёт: {fmt_money(invoice)}",
        "",
        f"🍽 Кухня: {fmt_money(kitchen)} | 🍹 Бар: {fmt_money(bar)}",
        f"🧾 Чеков: {fmt_int(orders)} | Ср. чек: {fmt_money(avg_chk)} | Гостей: {fmt_int(guests)}",
    ]
    if has_manual:
        lines += [
            "",
            f"👥 Персонал: {fmt_int(staff_total)} чел. | З/п: {fmt_money(zp_total)}",
            f"🏦 Инкассация: {fmt_money(inkass)} | Остаток: {fmt_money(balance)}",
        ]
    else:
        lines += ["", "⚠️ Ручные данные не заполнены (администратор не ответил)"]

    # Отмены и списания могут быть None (недоступны в iiko Cloud API)
    cancel_str = fmt_money(cancellations) if cancellations is not None else "⚠️ нет данных"
    writeoff_str = fmt_money(writeoffs) if writeoffs is not None else "⚠️ нет данных"
    lines += [
        "",
        f"⚠️ Отмены: {cancel_str} | 🗑 Списания: {writeoff_str}",
        "",
        f"📎 Таблица: {SHEETS_URL}",
    ]
    return "\n".join(lines)


def _build_admin_request(report_date: date) -> str:
    """Сформировать запрос ручных данных у администратора."""
    return "\n".join([
        f"📋 Монблан — данные за {fmt_date_ru(report_date)} собраны автоматически.",
        "",
        "Заполните вручную и ответьте в этом чате в точно таком формате:",
        "",
        "Инкассация: 70000",
        "Расход: 3500",
        "Остаток: 26500",
        "Завтраки: 12",
        "Повара: 3/9000",
        "Официанты: 4/12000",
        "Бармены: 1/3500",
        "Посудомойщицы: 2/5000",
        "",
        "⏱ Жду ответ 30 минут.",
    ])


def _aggregate_weekly(service, monday: date, sunday: date, week_num: int) -> dict:
    """
    Прочитать лист «Ежедневно» и собрать агрегаты за неделю.
    Возвращает словарь для write_weekly_row().
    """
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEETS_ID,
        range="Ежедневно!A:AZ"
    ).execute()
    rows = result.get("values", [])

    if not rows or len(rows) < 2:
        logger.warning("Лист «Ежедневно» пустой или только заголовок")
        return _empty_weekly(week_num, monday, sunday)

    headers = rows[0]

    def col(name):
        try:
            return headers.index(name)
        except ValueError:
            return -1

    def _f(row, name):
        idx = col(name)
        if idx < 0 or idx >= len(row):
            return 0
        try:
            return float(str(row[idx]).replace(" ", "").replace(",", ".") or 0)
        except (ValueError, TypeError):
            return 0

    # Фильтруем строки за нужную неделю
    week_rows = []
    for row in rows[1:]:
        if not row:
            continue
        try:
            row_date = date.fromisoformat(str(row[0]))
        except (ValueError, IndexError):
            continue
        if monday <= row_date <= sunday:
            week_rows.append(row)

    if not week_rows:
        logger.warning(f"Нет данных за неделю {monday}–{sunday}")
        return _empty_weekly(week_num, monday, sunday)

    n = len(week_rows)
    revenue      = sum(_f(r, "Выручка итого") for r in week_rows)
    orders       = sum(_f(r, "Кол-во чеков")  for r in week_rows)
    guests       = sum(_f(r, "Гости")          for r in week_rows)
    kitchen      = sum(_f(r, "Кухня")          for r in week_rows)
    bar          = sum(_f(r, "Бар")            for r in week_rows)
    cancels      = sum(_f(r, "Отмены (руб)")   for r in week_rows)
    writeoffs_s  = sum(_f(r, "Списания (руб)") for r in week_rows)
    rev_morning  = sum(_f(r, "Утро (выручка)") for r in week_rows)
    rev_day      = sum(_f(r, "День (выручка)") for r in week_rows)
    rev_evening  = sum(_f(r, "Вечер (выручка)") for r in week_rows)
    zp_total     = sum(_f(r, "З/п итого")      for r in week_rows)

    avg_check       = round(revenue / orders, 2) if orders else 0
    avg_check_guest = round(revenue / guests, 2) if guests else 0

    capacity = get_capacity(monday)
    tables   = capacity["tables"]
    seats    = capacity["seats"]
    turnover_table = round(guests / tables / n, 2) if tables and n else 0
    turnover_seat  = round(guests / seats  / n, 2) if seats  and n else 0

    return {
        "week_num":        week_num,
        "date_from":       str(monday),
        "date_to":         str(sunday),
        "revenue":         revenue,
        "avg_revenue_day": round(revenue / n, 2) if n else 0,
        "orders":          orders,
        "avg_orders_day":  round(orders / n, 2) if n else 0,
        "guests":          guests,
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

def main():
    parser = argparse.ArgumentParser(description="Монблан — автоматический отчёт")
    parser.add_argument("mode", choices=["daily", "weekly"],
                        help="Тип отчёта: daily или weekly")
    parser.add_argument("date", nargs="?", default=None,
                        help="Дата в формате YYYY-MM-DD (по умолчанию: вчера для daily, прошлая неделя для weekly)")
    args = parser.parse_args()

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
        if args.mode == "daily":
            daily(target_date)
        else:
            weekly(target_date)
    except Exception as e:
        logger.critical(f"Необработанная ошибка: {e}", exc_info=True)
        _alert_dev(bot, str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
