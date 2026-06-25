"""SQLite — источник правды для Content Bot. Схема и CRUD-функции."""
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config

_MSK = ZoneInfo("Europe/Moscow")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS blacklist (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            text          TEXT NOT NULL,
            mode          TEXT NOT NULL,          -- 'temporary' | 'permanent'
            blocked_until TEXT,                   -- ISO8601, NULL для permanent
            reason        TEXT,
            created_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ideas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            text        TEXT NOT NULL,
            source      TEXT DEFAULT 'text',       -- 'text' | 'voice'
            status      TEXT DEFAULT 'saved',       -- 'saved' | 'in_progress' | 'paused'
            rubric      TEXT DEFAULT 'regular',      -- 'regular' | 'lifehack'
            created_at  TEXT NOT NULL,
            cooldown_until   TEXT                   -- published_at + 30 дней (заполняется при публикации любого варианта)
        );

        CREATE TABLE IF NOT EXISTS generations (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            idea_id      INTEGER NOT NULL REFERENCES ideas(id),
            variant_num  INTEGER NOT NULL,
            text         TEXT NOT NULL,
            audience     TEXT NOT NULL,
            format       TEXT NOT NULL,
            revision     INTEGER DEFAULT 0,
            sheets_hash  TEXT,
            created_at   TEXT NOT NULL,
            status       TEXT DEFAULT 'generated', -- 'generated' | 'draft' | 'to_publish' | 'published' | 'delete'
            scheduled_at TEXT,
            published_at TEXT,
            channel_message_id INTEGER
        );
    """)
    # Миграция: добавляем новые колонки к generations если их нет (для уже существующей БД)
    for col_def in [
        "ALTER TABLE generations ADD COLUMN status TEXT DEFAULT 'generated'",
        "ALTER TABLE generations ADD COLUMN scheduled_at TEXT",
        "ALTER TABLE generations ADD COLUMN published_at TEXT",
        "ALTER TABLE generations ADD COLUMN channel_message_id INTEGER",
        "ALTER TABLE generations ADD COLUMN notified_about_review_at TEXT",
    ]:
        try:
            conn.execute(col_def)
        except Exception:
            pass  # колонка уже существует
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now(_MSK).replace(tzinfo=None).isoformat()


# ── Идеи ──────────────────────────────────────────────────────
def add_idea(text: str, source: str = "text", rubric: str = "regular", status: str = "saved") -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO ideas (text, source, status, rubric, created_at) VALUES (?, ?, ?, ?, ?)",
        (text, source, status, rubric, _now()),
    )
    idea_id = cur.lastrowid
    conn.commit()
    conn.close()
    return idea_id


def get_idea(idea_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM ideas WHERE id=?", (idea_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_ideas(status: str = "saved", limit: int = 50, offset: int = 0) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ideas WHERE status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (status, limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_idea_status(idea_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE ideas SET status=? WHERE id=?", (status, idea_id))
    conn.commit()
    conn.close()


def get_published_texts(limit: int = 50) -> list[str]:
    """Темы публикаций для cooldown-фильтра: идеи с активным cooldown_until ИЛИ
    с опубликованным постом за последние 30 дней (страховка если cooldown_until не проставился)."""
    conn = get_conn()
    cutoff = (datetime.now(_MSK) - timedelta(days=config.IDEA_COOLDOWN_DAYS)).isoformat()
    rows = conn.execute(
        """SELECT DISTINCT i.text FROM ideas i
           WHERE i.cooldown_until > ?
              OR EXISTS (
                  SELECT 1 FROM generations g
                  WHERE g.idea_id = i.id
                    AND g.status = 'published'
                    AND g.published_at > ?
              )
           ORDER BY i.cooldown_until DESC NULLS LAST
           LIMIT ?""",
        (_now(), cutoff, limit),
    ).fetchall()
    conn.close()
    return [r["text"] for r in rows]


# ── Варианты постов ──────────────────────────────────────────
def add_generation(idea_id: int, variant_num: int, text: str, audience: str, format_: str) -> int:
    """Сохраняет вариант со статусом 'generated'. Переход в 'draft' — через mark_generation_saved()."""
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO generations (idea_id, variant_num, text, audience, format, created_at, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'generated')",
        (idea_id, variant_num, text, audience, format_, _now()),
    )
    gen_id = cur.lastrowid
    conn.commit()
    conn.close()
    return gen_id


def get_generation(gen_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM generations WHERE id=?", (gen_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def mark_review_notified(gen_id: int):
    """Отмечает, что Александр уже получил уведомление о «На согласование» (кнопкой или поллингом)."""
    conn = get_conn()
    conn.execute("UPDATE generations SET notified_about_review_at=? WHERE id=?", (_now(), gen_id))
    conn.commit()
    conn.close()


def get_generations_for_idea(idea_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM generations WHERE idea_id=? ORDER BY variant_num", (idea_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_generations_by_status(status: str) -> list[dict]:
    """Все варианты с заданным статусом — для восстановления расписания и sync."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM generations WHERE status=?", (status,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_generation_saved(gen_id: int):
    """'generated' → 'draft': пользователь нажал «Сохранить», вариант отправляется в Sheets."""
    conn = get_conn()
    conn.execute("UPDATE generations SET status='draft' WHERE id=?", (gen_id,))
    conn.commit()
    conn.close()


def update_generation_schedule(gen_id: int, scheduled_at: str):
    """'draft' → 'to_publish': дата из таблицы разобрана, APScheduler job зарегистрирован."""
    conn = get_conn()
    conn.execute(
        "UPDATE generations SET status='to_publish', scheduled_at=? WHERE id=?",
        (scheduled_at, gen_id),
    )
    conn.commit()
    conn.close()


def mark_generation_published(gen_id: int, channel_message_id: int | None = None):
    """Публикация состоялась. Также ставит cooldown на родительскую идею."""
    now = _now()
    cooldown_until = (
        datetime.now(_MSK).replace(tzinfo=None) + timedelta(days=config.IDEA_COOLDOWN_DAYS)
    ).isoformat()
    conn = get_conn()
    conn.execute(
        "UPDATE generations SET status='published', published_at=?, channel_message_id=? WHERE id=?",
        (now, channel_message_id, gen_id),
    )
    # Проставляем cooldown на уровне идеи чтобы тема не повторялась в Режиме 0
    gen = conn.execute("SELECT idea_id FROM generations WHERE id=?", (gen_id,)).fetchone()
    if gen:
        conn.execute(
            "UPDATE ideas SET cooldown_until=? WHERE id=?",
            (cooldown_until, gen["idea_id"]),
        )
    conn.commit()
    conn.close()


def delete_generation(gen_id: int):
    """Удаляет вариант из БД (триггер: статус «🗑 Удалить» в Sheets при 3:00-sync)."""
    conn = get_conn()
    conn.execute("DELETE FROM generations WHERE id=?", (gen_id,))
    conn.commit()
    conn.close()


def update_generation_text(gen_id: int, new_text: str):
    conn = get_conn()
    conn.execute(
        "UPDATE generations SET text=?, revision=revision+1 WHERE id=?",
        (new_text, gen_id),
    )
    conn.commit()
    conn.close()


def update_generation_hash(gen_id: int, sheets_hash: str):
    conn = get_conn()
    conn.execute("UPDATE generations SET sheets_hash=? WHERE id=?", (sheets_hash, gen_id))
    conn.commit()
    conn.close()


# ── Блэклист ──────────────────────────────────────────────────
def add_blacklist_entry(text: str, mode: str, blocked_until: str | None = None, reason: str = "") -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO blacklist (text, mode, blocked_until, reason, created_at) VALUES (?, ?, ?, ?, ?)",
        (text, mode, blocked_until, reason, _now()),
    )
    entry_id = cur.lastrowid
    conn.commit()
    conn.close()
    return entry_id


def list_blacklist() -> list[dict]:
    """Активные записи: permanent всегда, temporary — только не истёкшие."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM blacklist WHERE mode='permanent' OR blocked_until > ? ORDER BY created_at DESC",
        (_now(),),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_blacklist_entry(entry_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM blacklist WHERE id=?", (entry_id,))
    conn.commit()
    conn.close()
