"""
rules_db.py — SQLite CRUD для системы правил управляющего бота.
БД: /home/parser/bots/shared/rules.db
"""
import json
import sqlite3
from pathlib import Path

RULES_DB = "/home/parser/bots/shared/rules.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(RULES_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    Path(RULES_DB).parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS rules (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
                target_bot  TEXT    NOT NULL,
                rule_type   TEXT    NOT NULL,
                trigger_kw  TEXT,
                instruction TEXT    NOT NULL,
                description TEXT,
                active      INTEGER DEFAULT 1,
                priority    INTEGER DEFAULT 0,
                use_count   INTEGER DEFAULT 0,
                last_used   TEXT
            );
            CREATE TABLE IF NOT EXISTS rule_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id       INTEGER REFERENCES rules(id) ON DELETE CASCADE,
                applied_at    TEXT    DEFAULT (datetime('now', 'localtime')),
                input_snippet TEXT,
                trigger_hit   TEXT
            );
        """)


def create_rule(
    target_bot: str,
    rule_type: str,
    instruction: str,
    trigger_kw: list | None = None,
    description: str | None = None,
    priority: int = 0,
) -> int:
    kw_json = json.dumps(trigger_kw, ensure_ascii=False) if trigger_kw else None
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO rules (target_bot, rule_type, trigger_kw, instruction, description, priority)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (target_bot, rule_type, kw_json, instruction, description, priority),
        )
        return cur.lastrowid


def get_active_rules(bot_name: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT * FROM rules
               WHERE active = 1 AND (target_bot = ? OR target_bot = 'all')
               ORDER BY priority DESC, id""",
            (bot_name,),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["trigger_kw"] = json.loads(d["trigger_kw"]) if d["trigger_kw"] else None
        result.append(d)
    return result


def get_system_addons(bot_name: str) -> list[str]:
    rules = get_active_rules(bot_name)
    return [r["instruction"] for r in rules if r["rule_type"] == "system_addon"]


def delete_rule(rule_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        return cur.rowcount > 0


def toggle_rule(rule_id: int) -> bool | None:
    """Переключает active. Возвращает новое состояние или None если правило не найдено."""
    with _connect() as conn:
        row = conn.execute("SELECT active FROM rules WHERE id = ?", (rule_id,)).fetchone()
        if not row:
            return None
        new_state = 0 if row["active"] else 1
        conn.execute("UPDATE rules SET active = ? WHERE id = ?", (new_state, rule_id))
        return bool(new_state)


def list_rules(bot_name: str | None = None) -> list[dict]:
    with _connect() as conn:
        if bot_name:
            rows = conn.execute(
                "SELECT * FROM rules WHERE target_bot = ? OR target_bot = 'all' ORDER BY id",
                (bot_name,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM rules ORDER BY id").fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["trigger_kw"] = json.loads(d["trigger_kw"]) if d["trigger_kw"] else None
        result.append(d)
    return result


def get_rule(rule_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["trigger_kw"] = json.loads(d["trigger_kw"]) if d["trigger_kw"] else None
    return d


def log_application(rule_id: int, input_snippet: str, trigger: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO rule_log (rule_id, input_snippet, trigger_hit) VALUES (?, ?, ?)",
            (rule_id, input_snippet[:120], trigger),
        )
        conn.execute(
            "UPDATE rules SET use_count = use_count + 1, last_used = datetime('now','localtime') WHERE id = ?",
            (rule_id,),
        )


def get_rule_log(rule_id: int, limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM rule_log WHERE rule_id = ? ORDER BY id DESC LIMIT ?",
            (rule_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
