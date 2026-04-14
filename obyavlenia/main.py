"""
Точка входа. Запускает все парсеры, обновляет БД, Google Sheets и Telegram.
Может работать как разово (python main.py), так и по расписанию (python main.py --schedule).
"""
import sys
import argparse
import traceback
from datetime import datetime
from loguru import logger

import config
import database as db
import sheets
import notifier
from utils.deduplicator import process_listing, mark_gone_listings
from utils.filters import get_enabled_directions, reload_config

# ─── Логирование ──────────────────────────────────────────────────────────────
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")
logger.add(
    config.LOG_FILE,
    level="DEBUG",
    rotation="10 MB",
    retention="30 days",
    encoding="utf-8",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} | {message}",
)


def run_all_scrapers() -> dict:
    """
    Запускает все парсеры, обновляет БД.
    Возвращает статистику: {new, changed, unchanged, removed, errors}.
    """
    stats = {"new": 0, "changed": 0, "unchanged": 0, "removed": 0, "errors": 0}

    # Ленивый импорт парсеров (чтобы ошибка одного не ломала другие)
    scrapers_classes = [
        ("scrapers.altera",   "AlteraScraper"),
        ("scrapers.optima",   "OptimaScraper"),
        ("scrapers.biztotal", "BiztotalScraper"),
        ("scrapers.biznes",   "BiznesScraper"),
        ("scrapers.telegram_scraper", "TelegramScraper"),
        ("scrapers.avito",    "AvitoScraper"),   # последним — самый медленный
    ]

    for module_name, class_name in scrapers_classes:
        try:
            import importlib
            module = importlib.import_module(module_name)
            scraper_cls = getattr(module, class_name)
            scraper = scraper_cls()

            logger.info("▶ Запускаем парсер: {}", scraper.source_name)
            items = scraper.scrape()

            seen_ids: set[str] = set()
            source = scraper.source_name

            for item in items:
                seen_ids.add(item["id"])
                result = process_listing(item)
                stats[result if result in stats else "unchanged"] += 1
                if result == "restored":
                    stats["new"] += 1  # считаем восстановленные как новые

            removed = mark_gone_listings(source, seen_ids)
            stats["removed"] += removed

            # Задержка между площадками (кроме последнего)
            if module_name != scrapers_classes[-1][0]:
                from scrapers.base_scraper import BaseScraper
                BaseScraper.site_delay()

        except Exception as e:
            logger.error("Ошибка парсера {}: {}", module_name, traceback.format_exc())
            stats["errors"] += 1

    return stats


def run() -> None:
    """Один полный цикл сканирования."""
    start = datetime.now()
    logger.info("=" * 60)
    logger.info("Запуск парсера | {}", start.strftime("%Y-%m-%d %H:%M:%S"))

    # Сбрасываем кэш конфига (вдруг пользователь изменил keywords_config.json)
    reload_config()

    directions = get_enabled_directions()
    logger.info("Активные направления: {}", ", ".join(directions) if directions else "нет")

    # Инициализация БД
    db.init_db()

    try:
        stats = run_all_scrapers()
    except Exception as e:
        logger.critical("Критическая ошибка в run_all_scrapers: {}", e)
        notifier.send_error_alert(traceback.format_exc())
        return

    # Отправляем накопленные уведомления
    try:
        notifier.send_pending_notifications()
    except Exception as e:
        logger.error("Ошибка отправки уведомлений: {}", e)

    # Обновляем Google Sheets
    try:
        sheets.update_sheets()
    except Exception as e:
        logger.error("Ошибка обновления Google Sheets: {}", e)

    # Сводка — только если есть новые, изменённые или снятые объявления
    has_activity = stats["new"] or stats["changed"] or stats["removed"]
    if has_activity:
        try:
            notifier.send_summary(stats)
        except Exception as e:
            logger.error("Ошибка отправки сводки: {}", e)

    elapsed = (datetime.now() - start).seconds
    logger.info(
        "Завершено за {} сек | Новых: {} | Изменено: {} | Снято: {} | Ошибок: {}",
        elapsed, stats["new"], stats["changed"], stats["removed"], stats["errors"]
    )
    logger.info("=" * 60)


def run_scheduled() -> None:
    """Запускает парсер по расписанию через APScheduler."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.error("APScheduler не установлен. Запусти install.sh/install.bat")
        sys.exit(1)

    scheduler = BlockingScheduler(timezone=config.RUN_TIMEZONE)
    scheduler.add_job(
        run,
        CronTrigger(hour=config.RUN_HOUR, minute=config.RUN_MINUTE, timezone=config.RUN_TIMEZONE),
        id="daily_parse",
        replace_existing=True,
    )

    logger.info(
        "Планировщик запущен. Расписание: каждый день в {}:{} МСК",
        config.RUN_HOUR, str(config.RUN_MINUTE).zfill(2)
    )
    logger.info("Для остановки нажми Ctrl+C")

    # Запускаем один раз сразу при старте
    logger.info("Первый запуск сейчас...")
    run()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Планировщик остановлен.")


def check_setup() -> None:
    """Проверяет настройку и выводит что не заполнено."""
    missing = config.check_config()
    if missing:
        print("\n⚠️  Не заполнены обязательные переменные в .env:")
        for m in missing:
            print(f"   - {m}")
        print("\nОткрой файл .env и заполни их. Пример смотри в .env.example\n")
        sys.exit(1)
    print("✅ Конфигурация в порядке")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Парсер объявлений о продаже бизнеса")
    parser.add_argument(
        "--schedule",
        action="store_true",
        help=f"Запустить по расписанию (каждый день в {config.RUN_HOUR}:00 МСК)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Проверить конфигурацию .env без запуска парсера"
    )
    args = parser.parse_args()

    if args.check:
        check_setup()
    elif args.schedule:
        run_scheduled()
    else:
        db.init_db()
        run()
