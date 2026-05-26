#!/usr/bin/env python3
"""
Экспорт фактов из SQLite в knowledge/bot_facts.md.
Запускается на сервере: pull_from_server.sh вызывает его перед pull.
"""

import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = "/home/parser/bots/assistant/data/assistant.db"
KNOWLEDGE_DIR = Path("/home/parser/bots/assistant/knowledge")
OUTPUT = KNOWLEDGE_DIR / "bot_facts.md"

HEADER = """# Факты, запомненные ботом из Telegram-диалогов

<!-- Этот файл управляется автоматически.
     Не редактировать вручную. -->

"""


def export():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, category, text, created_at FROM memory ORDER BY id"
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"Ошибка чтения SQLite: {e}")
        return

    lines = [HEADER.rstrip()]

    if rows:
        # Группируем по категориям
        by_cat: dict[str, list] = {}
        for row in rows:
            cat = row["category"] or "fact"
            by_cat.setdefault(cat, []).append(row)

        cat_labels = {
            "fact": "📌 Факты",
            "preference": "⚙️ Предпочтения",
            "project": "📁 Проекты",
            "decision": "✅ Решения",
        }

        for cat, items in by_cat.items():
            label = cat_labels.get(cat, f"• {cat}")
            lines.append(f"\n## {label}\n")
            for row in items:
                dt = (row["created_at"] or "")[:10]
                lines.append(f"- {row['text']}  _{dt}_")
    else:
        lines.append("\n*Память пуста.*")

    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Экспортировано {len(rows)} фактов → {OUTPUT}")


if __name__ == "__main__":
    export()
