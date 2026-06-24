"""Публикация постов в канал + расписание (APScheduler)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import db

_MSK = ZoneInfo("Europe/Moscow")

_bot = None
_scheduler: AsyncIOScheduler | None = None

DAY_NAMES = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}


def init(bot, scheduler: AsyncIOScheduler):
    """Вызывается при старте bot.py. Восстанавливает запланированные публикации."""
    global _bot, _scheduler
    _bot = bot
    _scheduler = scheduler
    restore_scheduled_jobs()
    _scheduler.add_job(
        check_lifehack_reminder, "cron", day_of_week="thu", hour=9, minute=0, id="lifehack_check"
    )


def restore_scheduled_jobs():
    """Читает generations со статусом 'to_publish' и регистрирует APScheduler job для каждого."""
    for gen in db.get_generations_by_status("to_publish"):
        if not gen.get("scheduled_at"):
            continue
        dt = datetime.fromisoformat(gen["scheduled_at"])
        if dt > datetime.now(_MSK).replace(tzinfo=None):
            _scheduler.add_job(
                _publish_job, "date", run_date=dt, args=[gen["id"]],
                id=f"publish_gen_{gen['id']}", replace_existing=True,
            )


async def _publish_job(gen_id: int):
    await publish_now(gen_id)


async def publish_now(gen_id: int) -> str:
    """Публикует пост в канал. Возвращает текст результата для пользователя."""
    gen = db.get_generation(gen_id)
    if not gen:
        return "Вариант не найден."
    msg = await _bot.send_message(config.CHANNEL_ID, gen["text"], parse_mode="HTML")
    db.mark_generation_published(gen_id, channel_message_id=msg.message_id)
    try:
        _scheduler.remove_job(f"publish_gen_{gen_id}")
    except Exception:
        pass
    return f"✅ Опубликовано (msg_id={msg.message_id})"


def schedule_generation(gen_id: int, dt: datetime):
    """Регистрирует публикацию generation на конкретное время (вызывается из sheets.sync_from_sheets)."""
    db.update_generation_schedule(gen_id, dt.isoformat())
    _scheduler.add_job(
        _publish_job, "date", run_date=dt, args=[gen_id],
        id=f"publish_gen_{gen_id}", replace_existing=True,
    )


# ── Слоты расписания ─────────────────────────────────────────
def next_publish_dates(count: int) -> list[datetime]:
    """Следующие даты по расписанию PUBLISH_DAYS/PUBLISH_HOUR, без проверки занятости."""
    dates = []
    cur = datetime.now(_MSK).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    while len(dates) < count:
        cur += timedelta(days=1)
        if cur.weekday() in config.PUBLISH_DAYS:
            dates.append(cur.replace(hour=config.PUBLISH_HOUR, minute=0))
    return dates


def get_free_slots(count: int = 3) -> list[datetime]:
    """Ближайшие N свободных слотов."""
    taken = {
        datetime.fromisoformat(g["scheduled_at"])
        for g in db.get_generations_by_status("to_publish")
        if g.get("scheduled_at")
    }
    free = []
    for dt in next_publish_dates(count * 3):
        if dt not in taken:
            free.append(dt)
        if len(free) >= count:
            break
    return free


def get_free_slots_2months() -> list[datetime]:
    """Все свободные слоты на 2 месяца вперёд — для дропдауна в Sheets."""
    taken = {
        datetime.fromisoformat(g["scheduled_at"])
        for g in db.get_generations_by_status("to_publish")
        if g.get("scheduled_at")
    }
    until = datetime.now(_MSK).replace(tzinfo=None) + timedelta(days=62)
    cur = datetime.now(_MSK).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    free = []
    while cur <= until:
        cur += timedelta(days=1)
        if cur.weekday() in config.PUBLISH_DAYS:
            dt = cur.replace(hour=config.PUBLISH_HOUR, minute=0)
            if dt not in taken:
                free.append(dt)
    return free


# ── Лайфхак-четверги ─────────────────────────────────────────
def is_lifehack_thursday(date: datetime) -> bool:
    start = datetime.strptime(config.LIFEHACK_START_DATE, "%Y-%m-%d")
    return date.weekday() == 3 and (date.date() - start.date()).days % 14 == 0


async def check_lifehack_reminder():
    today = datetime.now(_MSK).replace(tzinfo=None)
    if not is_lifehack_thursday(today):
        return
    # Ищем generation с рубрикой lifehack, запланированный на сегодня
    conn = db.get_conn()
    day_start = today.replace(hour=0, minute=0, second=0)
    day_end = today.replace(hour=23, minute=59, second=59)
    row = conn.execute(
        """SELECT g.id FROM generations g
           JOIN ideas i ON i.id = g.idea_id
           WHERE i.rubric='lifehack'
             AND g.status IN ('to_publish', 'published')
             AND g.scheduled_at BETWEEN ? AND ?""",
        (day_start.isoformat(), day_end.isoformat()),
    ).fetchone()
    conn.close()
    if row:
        return
    for user_id in config.ALLOWED_USER_IDS:
        await _bot.send_message(
            user_id,
            "🔔 Сегодня Лайфхак-четверг! Нет запланированного поста.\n"
            "Наговори тему — я подготовлю лайфхак прямо сейчас.",
        )
