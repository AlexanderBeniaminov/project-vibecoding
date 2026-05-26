#!/usr/bin/env python3
"""
crm.py — Персональная CRM: история контактов, факты, договорённости.

Использование:
  python3 ~/bin/crm.py save "Богданов" "хочет скидку на корпоратив, перезвонить до 3 июня"
  python3 ~/bin/crm.py get "Богданов"
  python3 ~/bin/crm.py list
"""
import sys
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / ".config" / "crm.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON contacts(name COLLATE NOCASE)")
    conn.commit()
    return conn


def normalize_name(name: str) -> str:
    return name.strip().title()


def save(name: str, note: str) -> str:
    conn = get_conn()
    name_clean = normalize_name(name)
    conn.execute("INSERT INTO contacts (name, note) VALUES (?, ?)", (name_clean, note.strip()))
    conn.commit()
    conn.close()
    return f"✅ Сохранено для {name_clean}: {note.strip()}"


def get(name: str) -> str:
    conn = get_conn()
    name_clean = normalize_name(name)
    rows = conn.execute(
        "SELECT note, created_at FROM contacts WHERE name LIKE ? ORDER BY id DESC LIMIT 10",
        (f"%{name_clean}%",)
    ).fetchall()
    conn.close()
    if not rows:
        return f"По контакту «{name_clean}» ничего не найдено."
    lines = [f"📇 *{name_clean}* — последние записи:"]
    for r in rows:
        dt = r["created_at"][:16]
        lines.append(f"  • ({dt}) {r['note']}")
    return "\n".join(lines)


def list_recent() -> str:
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, note, created_at FROM contacts ORDER BY id DESC LIMIT 20"
    ).fetchall()
    conn.close()
    if not rows:
        return "CRM пуста."
    lines = ["📇 *Последние записи CRM:*"]
    for r in rows:
        dt = r["created_at"][:10]
        lines.append(f"  • ({dt}) *{r['name']}*: {r['note'][:100]}")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: crm.py [save|get|list] ...")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "save" and len(sys.argv) >= 4:
        print(save(sys.argv[2], sys.argv[3]))
    elif cmd == "get" and len(sys.argv) >= 3:
        print(get(sys.argv[2]))
    elif cmd == "list":
        print(list_recent())
    else:
        print("Неверная команда")
        sys.exit(1)
