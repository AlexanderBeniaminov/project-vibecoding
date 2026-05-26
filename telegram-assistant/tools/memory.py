from __future__ import annotations
from datetime import datetime
from pathlib import Path
from .db import get_conn

CATEGORIES = {"fact", "preference", "project", "decision"}

def _init_memory_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL DEFAULT 'fact',
            text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
        USING fts5(text, content=memory, content_rowid=id)
    """)
    conn.commit()
    conn.close()

def remember_fact(text: str, category: str = "fact") -> str:
    if category not in CATEGORIES:
        category = "fact"
    conn = get_conn()
    conn.execute(
        "INSERT INTO memory (category, text) VALUES (?, ?)",
        (category, text.strip()),
    )
    conn.execute("INSERT INTO memory_fts(memory_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()
    return f"Запомнено [{category}]: {text[:80]}"

def recall_facts(query: str, limit: int = 5) -> str:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT m.category, m.text
               FROM memory_fts f
               JOIN memory m ON m.id = f.rowid
               WHERE memory_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (query, limit),
        ).fetchall()
    except Exception:
        rows = []
    if not rows:
        rows = conn.execute(
            "SELECT category, text FROM memory ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    if not rows:
        return "Ничего не найдено в памяти."
    return "\n".join(f"[{r['category']}] {r['text']}" for r in rows)

def list_memories(category: str = "") -> str:
    conn = get_conn()
    if category and category in CATEGORIES:
        rows = conn.execute(
            "SELECT id, category, text FROM memory WHERE category=? ORDER BY id DESC LIMIT 20",
            (category,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, category, text FROM memory ORDER BY id DESC LIMIT 20"
        ).fetchall()
    conn.close()
    if not rows:
        return "Память пуста."
    return "\n".join(f"#{r['id']} [{r['category']}] {r['text']}" for r in rows)

def forget_fact(memory_id: int) -> str:
    conn = get_conn()
    conn.execute("DELETE FROM memory WHERE id=?", (memory_id,))
    conn.execute("INSERT INTO memory_fts(memory_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()
    return f"Факт #{memory_id} удалён из памяти."

def get_recent_summary(limit: int = 5) -> str:
    conn = get_conn()
    rows = conn.execute(
        "SELECT category, text FROM memory ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    if not rows:
        return ""
    return "\n".join(f"- [{r['category']}] {r['text']}" for r in rows)

# ── Обновление файлов базы знаний ─────────────────────────────

_KNOWLEDGE_FILES = {
    "projects": "projects.md",
    "user": "user.md",
}

def update_knowledge(target: str, content: str, mode: str = "append") -> str:
    """
    Обновить файл базы знаний.
    target: 'projects' или 'user'
    mode: 'append' — добавить в конец, 'replace_section' — заменить секцию по заголовку
    """
    import config as cfg
    knowledge_dir = Path(getattr(cfg, "KNOWLEDGE_DIR", "/home/parser/bots/assistant/knowledge"))
    fname = _KNOWLEDGE_FILES.get(target)
    if not fname:
        return f"Неизвестный файл: {target}. Доступны: {list(_KNOWLEDGE_FILES.keys())}"

    fpath = knowledge_dir / fname
    if not fpath.exists():
        return f"Файл {fpath} не найден."

    if mode == "append":
        with open(fpath, "a", encoding="utf-8") as f:
            f.write(f"\n\n<!-- обновлено {datetime.now().strftime('%d.%m.%Y %H:%M')} -->\n")
            f.write(content.strip())
        # Перезагрузить знания в памяти бота (глобальная переменная в основном модуле)
        _reload_knowledge()
        return f"✅ knowledge/{fname} обновлён."
    else:
        return "Режим replace_section пока не поддерживается. Используй append."

def _reload_knowledge():
    """Перезагружает KNOWLEDGE в основном модуле без перезапуска бота."""
    try:
        import importlib
        import assistant_bot
        assistant_bot.KNOWLEDGE = assistant_bot._load_knowledge()
    except Exception:
        pass  # не критично — обновится при следующем рестарте
