import sqlite3
import sys
sys.path.insert(0, "/home/parser/bots/assistant")
import config

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            tags TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            remind_at TEXT NOT NULL,
            done INTEGER DEFAULT 0,
            recurrence TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            telegram TEXT DEFAULT '',
            email TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS agreements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            source TEXT DEFAULT 'call',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            status TEXT DEFAULT 'pending',
            calendar_event_id TEXT,
            digest_sent_at TEXT
        );
    """)
    # Миграция: добавить recurrence если колонки ещё нет
    cols = [row[1] for row in conn.execute("PRAGMA table_info(reminders)").fetchall()]
    if "recurrence" not in cols:
        conn.execute("ALTER TABLE reminders ADD COLUMN recurrence TEXT DEFAULT NULL")
    conn.commit()
    conn.close()


def add_agreement(text: str, source: str = "call") -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO agreements (text, source) VALUES (?, ?)",
        (text, source),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_pending_agreements(only_today: bool = False) -> list:
    conn = get_conn()
    if only_today:
        rows = conn.execute(
            "SELECT * FROM agreements WHERE status='pending' AND date(created_at)=date('now','localtime') ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agreements WHERE status='pending' AND date(created_at)<date('now','localtime') ORDER BY id"
        ).fetchall()
    result = [dict(r) for r in rows]
    conn.close()
    return result


def get_agreement_by_id(agreement_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM agreements WHERE id=?", (agreement_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_agreement_status(agreement_id: int, status: str, calendar_event_id: str | None = None, text: str | None = None):
    conn = get_conn()
    if calendar_event_id is not None and text is not None:
        conn.execute(
            "UPDATE agreements SET status=?, calendar_event_id=?, text=? WHERE id=?",
            (status, calendar_event_id, text, agreement_id),
        )
    elif calendar_event_id is not None:
        conn.execute(
            "UPDATE agreements SET status=?, calendar_event_id=? WHERE id=?",
            (status, calendar_event_id, agreement_id),
        )
    elif text is not None:
        conn.execute(
            "UPDATE agreements SET text=? WHERE id=?",
            (text, agreement_id),
        )
    else:
        conn.execute("UPDATE agreements SET status=? WHERE id=?", (status, agreement_id))
    conn.commit()
    conn.close()


def mark_digest_sent(agreement_ids: list[int]):
    conn = get_conn()
    conn.executemany(
        "UPDATE agreements SET digest_sent_at=datetime('now','localtime') WHERE id=?",
        [(i,) for i in agreement_ids],
    )
    conn.commit()
    conn.close()
