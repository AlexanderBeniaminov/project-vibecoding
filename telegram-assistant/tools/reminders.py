from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .db import get_conn

_MSK = ZoneInfo("Europe/Moscow")
_scheduler: AsyncIOScheduler | None = None
_bot = None
_pending_acks: dict[int, set[int]] = {}

REPEAT_MINUTES = 30

# Поддерживаемые типы повторений
RECURRENCE_LABELS = {
    "daily":   "каждый день",
    "weekly":  "каждую неделю",
    "monthly": "каждый месяц",
    "yearly":  "каждый год",
}

def init_scheduler(bot, scheduler: AsyncIOScheduler):
    global _scheduler, _bot
    _bot = bot
    _scheduler = scheduler
    _restore_pending()

def _next_dt(dt: datetime, recurrence: str) -> datetime:
    """Вычисляет следующее время срабатывания для повторяющегося напоминания."""
    if recurrence == "daily":
        return dt + timedelta(days=1)
    if recurrence == "weekly":
        return dt + timedelta(weeks=1)
    if recurrence == "monthly":
        # Следующий месяц, тот же день. Если дня нет — последний день месяца.
        month = dt.month + 1
        year = dt.year
        if month > 12:
            month = 1
            year += 1
        import calendar
        max_day = calendar.monthrange(year, month)[1]
        day = min(dt.day, max_day)
        return dt.replace(year=year, month=month, day=day)
    if recurrence == "yearly":
        import calendar
        year = dt.year + 1
        max_day = calendar.monthrange(year, dt.month)[1]
        day = min(dt.day, max_day)
        return dt.replace(year=year, day=day)
    return dt

def _restore_pending():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, user_id, text, remind_at, recurrence FROM reminders "
        "WHERE done=0 AND remind_at > datetime('now')"
    ).fetchall()
    conn.close()
    for r in rows:
        dt = datetime.fromisoformat(r["remind_at"])
        _scheduler.add_job(
            _fire, "date",
            run_date=dt,
            args=[r["user_id"], r["text"], r["id"], r["recurrence"]],
            id=f"rem_{r['id']}",
            replace_existing=True,
        )

def _main_keyboard(reminder_id: int):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Выполнено", callback_data=f"ack_{reminder_id}"),
        InlineKeyboardButton(text="⏰ Отложить",  callback_data=f"snz_{reminder_id}"),
    ]])

def _snooze_keyboard(reminder_id: int):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="15 мин", callback_data=f"snz_{reminder_id}_15"),
            InlineKeyboardButton(text="1 час",  callback_data=f"snz_{reminder_id}_60"),
        ],
        [
            InlineKeyboardButton(text="3 часа",  callback_data=f"snz_{reminder_id}_180"),
            InlineKeyboardButton(text="Завтра",  callback_data=f"snz_{reminder_id}_tmr"),
        ],
        [InlineKeyboardButton(text="◀ Назад", callback_data=f"snz_{reminder_id}_back")],
    ])

async def _fire(user_id: int, text: str, reminder_id: int, recurrence: str | None = None):
    if _bot:
        label = f" ({RECURRENCE_LABELS[recurrence]})" if recurrence else ""
        await _bot.send_message(
            user_id,
            f"⏰ *Напоминание{label}:* {text}",
            parse_mode="Markdown",
            reply_markup=_main_keyboard(reminder_id),
        )
    _pending_acks.setdefault(user_id, set()).add(reminder_id)
    if _scheduler:
        next_run = datetime.now(_MSK).replace(tzinfo=None) + timedelta(minutes=REPEAT_MINUTES)
        _scheduler.add_job(
            _fire, "date",
            run_date=next_run,
            args=[user_id, text, reminder_id, recurrence],
            id=f"repeat_rem_{reminder_id}",
            replace_existing=True,
        )

def ack_reminder_by_id(reminder_id: int, user_id: int):
    _pending_acks.get(user_id, set()).discard(reminder_id)
    if _scheduler:
        for jid in [f"repeat_rem_{reminder_id}"]:
            try:
                _scheduler.remove_job(jid)
            except Exception:
                pass

    conn = get_conn()
    row = conn.execute(
        "SELECT text, remind_at, recurrence FROM reminders WHERE id=?", (reminder_id,)
    ).fetchone()

    if row and row["recurrence"]:
        # Повторяющееся — планируем следующее срабатывание
        recurrence = row["recurrence"]
        old_dt = datetime.fromisoformat(row["remind_at"])
        next_dt = _next_dt(old_dt, recurrence)
        conn.execute(
            "UPDATE reminders SET remind_at=?, done=0 WHERE id=?",
            (next_dt.isoformat(), reminder_id),
        )
        conn.commit()
        conn.close()
        if _scheduler:
            _scheduler.add_job(
                _fire, "date",
                run_date=next_dt,
                args=[user_id, row["text"], reminder_id, recurrence],
                id=f"rem_{reminder_id}",
                replace_existing=True,
            )
    else:
        conn.execute("UPDATE reminders SET done=1 WHERE id=?", (reminder_id,))
        conn.commit()
        conn.close()

def snooze_reminder(reminder_id: int, user_id: int, minutes: int) -> str:
    """Откладывает напоминание на N минут. minutes=0 означает завтра в 09:00."""
    _pending_acks.get(user_id, set()).discard(reminder_id)
    if _scheduler:
        for jid in [f"repeat_rem_{reminder_id}", f"rem_{reminder_id}"]:
            try:
                _scheduler.remove_job(jid)
            except Exception:
                pass
    now_msk = datetime.now(_MSK).replace(tzinfo=None)
    if minutes == 0:
        tomorrow = now_msk.date() + timedelta(days=1)
        new_dt = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 9, 0)
        label = "завтра в 09:00"
    else:
        new_dt = now_msk + timedelta(minutes=minutes)
        if minutes == 15:
            label = "через 15 мин"
        elif minutes == 60:
            label = "через 1 час"
        elif minutes == 180:
            label = "через 3 часа"
        else:
            label = f"через {minutes} мин"
    conn = get_conn()
    row = conn.execute(
        "SELECT text, recurrence FROM reminders WHERE id=?", (reminder_id,)
    ).fetchone()
    conn.execute("UPDATE reminders SET remind_at=?, done=0 WHERE id=?", (new_dt.isoformat(), reminder_id))
    conn.commit()
    conn.close()
    text = row["text"] if row else "напоминание"
    recurrence = row["recurrence"] if row else None
    if _scheduler:
        _scheduler.add_job(
            _fire, "date",
            run_date=new_dt,
            args=[user_id, text, reminder_id, recurrence],
            id=f"rem_{reminder_id}",
            replace_existing=True,
        )
    return label

def add_reminder(text: str, remind_at: str, user_id: int, recurrence: str | None = None) -> str:
    try:
        dt = datetime.fromisoformat(remind_at)
    except ValueError:
        return f"Неверный формат времени: {remind_at}. Используй ISO8601, например 2026-05-20T18:00:00"
    now_msk = datetime.now(_MSK).replace(tzinfo=None)
    if dt <= now_msk:
        return "Это время уже прошло. Укажи время в будущем."
    if recurrence and recurrence not in RECURRENCE_LABELS:
        return f"Неверный тип повторения: {recurrence}. Допустимые: daily, weekly, monthly, yearly."
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO reminders (user_id, text, remind_at, recurrence) VALUES (?, ?, ?, ?)",
        (user_id, text, dt.isoformat(), recurrence),
    )
    rem_id = cur.lastrowid
    conn.commit()
    conn.close()
    if _scheduler:
        _scheduler.add_job(
            _fire, "date",
            run_date=dt,
            args=[user_id, text, rem_id, recurrence],
            id=f"rem_{rem_id}",
            replace_existing=True,
        )
    rec_label = f", повтор: {RECURRENCE_LABELS[recurrence]}" if recurrence else ""
    return f"Напоминание #{rem_id} установлено на {dt.strftime('%d.%m.%Y %H:%M')}{rec_label}."

def list_reminders(user_id: int) -> str:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, text, remind_at, recurrence FROM reminders WHERE user_id=? AND done=0 ORDER BY remind_at",
        (user_id,),
    ).fetchall()
    conn.close()
    if not rows:
        return "Активных напоминаний нет."
    lines = []
    for r in rows:
        rec = f" 🔁 {RECURRENCE_LABELS[r['recurrence']]}" if r["recurrence"] else ""
        lines.append(f"#{r['id']} — {r['remind_at'][:16]} — {r['text']}{rec}")
    return "\n".join(lines)

def get_reminders_for_date(user_id: int, date_iso: str) -> list[dict]:
    """Возвращает напоминания на конкретную дату. date_iso: '2026-05-26'"""
    from datetime import date as date_type
    d = date_type.fromisoformat(date_iso)
    day_start = datetime(d.year, d.month, d.day, 0, 0, 0)
    day_end   = datetime(d.year, d.month, d.day, 23, 59, 59)
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, text, remind_at FROM reminders "
        "WHERE user_id=? AND remind_at BETWEEN ? AND ? ORDER BY remind_at",
        (user_id, day_start.isoformat(), day_end.isoformat()),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_today_reminders(user_id: int) -> list[dict]:
    """Возвращает напоминания на сегодня (МСК), включая уже выполненные."""
    today = datetime.now(_MSK).date()
    day_start = datetime(today.year, today.month, today.day, 0, 0, 0)
    day_end   = datetime(today.year, today.month, today.day, 23, 59, 59)
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, text, remind_at FROM reminders "
        "WHERE user_id=? AND remind_at BETWEEN ? AND ? ORDER BY remind_at",
        (user_id, day_start.isoformat(), day_end.isoformat()),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def cancel_reminder(reminder_id: int) -> str:
    conn = get_conn()
    conn.execute("UPDATE reminders SET done=1 WHERE id=?", (reminder_id,))
    conn.commit()
    conn.close()
    if _scheduler:
        for jid in [f"rem_{reminder_id}", f"repeat_rem_{reminder_id}"]:
            try:
                _scheduler.remove_job(jid)
            except Exception:
                pass
    return f"Напоминание #{reminder_id} отменено."
