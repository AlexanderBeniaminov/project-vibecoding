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
    """Вызывается при старте bot.py. Восстанавливает запланированные публикации
    и лайфхак-напоминания — паттерн идентичен tools/reminders.py:_restore_pending()."""
    global _bot, _scheduler
    _bot = bot
    _scheduler = scheduler
    restore_scheduled_jobs()
    _scheduler.add_job(
        check_lifehack_reminder, "cron", day_of_week="thu", hour=9, minute=0, id="lifehack_check"
    )


def restore_scheduled_jobs():
    for idea in db.get_scheduled_ideas():
        dt = datetime.fromisoformat(idea["scheduled_at"])
        _scheduler.add_job(
            _publish_job, "date", run_date=dt, args=[idea["id"]],
            id=f"publish_{idea['id']}", replace_existing=True,
        )


async def _publish_job(idea_id: int):
    generations = db.get_generations_for_idea(idea_id)
    if not generations:
        return
    # Берём вариант, который был утверждён последним (с наибольшим revision/id)
    gen = max(generations, key=lambda g: g["id"])
    await publish_now(idea_id, gen["id"])


async def publish_now(idea_id: int, gen_id: int) -> str:
    """Публикует пост в канал. Возвращает текстовое описание результата для пользователя."""
    gen = db.get_generation(gen_id)
    if not gen:
        return "Вариант не найден."
    msg = await _bot.send_message(config.CHANNEL_ID, gen["text"], parse_mode="HTML")
    db.mark_published(idea_id, channel_message_id=msg.message_id)
    try:
        _scheduler.remove_job(f"publish_{idea_id}")
    except Exception:
        pass
    return f"✅ Опубликовано в {config.CHANNEL_ID} (msg_id={msg.message_id})"


def schedule_post(idea_id: int, gen_id: int, dt: datetime):
    db.schedule_idea(idea_id, dt.isoformat())
    _scheduler.add_job(
        _publish_job, "date", run_date=dt, args=[idea_id],
        id=f"publish_{idea_id}", replace_existing=True,
    )


# ── Слоты расписания ────────────────────────────────────────
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
    """Возвращает ближайшие свободные слоты публикации (не занятые другой идеей)."""
    conn = db.get_conn()
    taken_rows = conn.execute(
        "SELECT scheduled_at FROM ideas WHERE status='scheduled' AND scheduled_at IS NOT NULL"
    ).fetchall()
    conn.close()
    taken = {datetime.fromisoformat(r["scheduled_at"]) for r in taken_rows}

    free = []
    candidates = next_publish_dates(count * 3)  # с запасом, часть может быть занята
    for dt in candidates:
        if dt not in taken:
            free.append(dt)
        if len(free) >= count:
            break
    return free


# ── Лайфхак-четверги ──────────────────────────────────────────
def is_lifehack_thursday(date: datetime) -> bool:
    start = datetime.strptime(config.LIFEHACK_START_DATE, "%Y-%m-%d")
    return date.weekday() == 3 and (date.date() - start.date()).days % 14 == 0


async def check_lifehack_reminder():
    today = datetime.now(_MSK).replace(tzinfo=None)
    if not is_lifehack_thursday(today):
        return
    conn = db.get_conn()
    day_start = today.replace(hour=0, minute=0, second=0)
    day_end = today.replace(hour=23, minute=59, second=59)
    row = conn.execute(
        "SELECT id FROM ideas WHERE rubric='lifehack' AND scheduled_at BETWEEN ? AND ?",
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
