from __future__ import annotations
from datetime import datetime
from pathlib import Path
from .db import get_conn

# Категории для LLM (pending_* — внутренние, не передаются модели)
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


# ── Сохранение с подтверждением ───────────────────────────────

def remember_fact_pending(text: str, category: str = "fact") -> tuple[int, str, str]:
    """
    Сохраняет факт как ожидающий подтверждения.
    Категория хранится как 'pending_fact', 'pending_preference' и т.д.
    Возвращает (fact_id, orig_category, text).
    """
    if category not in CATEGORIES:
        category = "fact"
    pending_cat = f"pending_{category}"
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO memory (category, text) VALUES (?, ?)",
        (pending_cat, text.strip()),
    )
    fact_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return (fact_id, category, text.strip())


def approve_fact(fact_id: int) -> str:
    """Подтверждает pending-факт — переводит в правильную категорию."""
    conn = get_conn()
    row = conn.execute("SELECT category, text FROM memory WHERE id=?", (fact_id,)).fetchone()
    if not row:
        conn.close()
        return f"Факт #{fact_id} не найден"
    cat = row["category"]
    if not cat.startswith("pending_"):
        conn.close()
        return f"Факт #{fact_id} уже подтверждён [{cat}]"
    orig_cat = cat[8:]  # убираем "pending_"
    conn.execute("UPDATE memory SET category=? WHERE id=?", (orig_cat, fact_id))
    conn.execute("INSERT INTO memory_fts(memory_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()
    return f"Сохранено [{orig_cat}]: {row['text'][:80]}"


def correct_fact(fact_id: int, new_text: str) -> str:
    """Исправляет текст и подтверждает pending-факт."""
    conn = get_conn()
    row = conn.execute("SELECT category FROM memory WHERE id=?", (fact_id,)).fetchone()
    if not row:
        conn.close()
        return f"Факт #{fact_id} не найден"
    cat = row["category"]
    orig_cat = cat[8:] if cat.startswith("pending_") else cat
    conn.execute(
        "UPDATE memory SET text=?, category=? WHERE id=?",
        (new_text.strip(), orig_cat, fact_id),
    )
    conn.execute("INSERT INTO memory_fts(memory_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()
    return f"Исправлено [{orig_cat}]: {new_text[:80]}"


def reject_fact(fact_id: int) -> str:
    """Удаляет pending-факт."""
    conn = get_conn()
    conn.execute("DELETE FROM memory WHERE id=? AND category LIKE 'pending_%'", (fact_id,))
    conn.commit()
    conn.close()
    return f"Факт #{fact_id} отклонён"


def get_pending_facts() -> list[dict]:
    """Список фактов, ожидающих подтверждения."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, category, text, created_at FROM memory WHERE category LIKE 'pending_%' ORDER BY id"
    ).fetchall()
    conn.close()
    return [
        {"id": r["id"], "category": r["category"][8:], "text": r["text"], "created_at": r["created_at"]}
        for r in rows
    ]


# ── Стандартные операции (исключают pending) ──────────────────

def remember_fact(text: str, category: str = "fact") -> str:
    """Прямое сохранение без подтверждения (используется внутренне / при исправлении)."""
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
               WHERE memory_fts MATCH ? AND m.category NOT LIKE 'pending_%'
               ORDER BY rank
               LIMIT ?""",
            (query, limit),
        ).fetchall()
    except Exception:
        rows = []
    if not rows:
        rows = conn.execute(
            "SELECT category, text FROM memory WHERE category NOT LIKE 'pending_%' ORDER BY id DESC LIMIT ?",
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
            "SELECT id, category, text FROM memory WHERE category NOT LIKE 'pending_%' ORDER BY id DESC LIMIT 20"
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
        "SELECT category, text FROM memory WHERE category NOT LIKE 'pending_%' ORDER BY id DESC LIMIT ?",
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
    "bot_facts": "bot_facts.md",  # факты из Telegram-диалогов
    "facts": "bot_facts.md",      # алиас
}


def update_knowledge(target: str, content: str, mode: str = "append") -> str:
    """
    Обновить файл базы знаний.
    target: 'projects', 'user' или 'bot_facts'
    mode: 'append' — добавить в конец
    """
    import config as cfg
    knowledge_dir = Path(getattr(cfg, "KNOWLEDGE_DIR", "/home/parser/bots/assistant/knowledge"))
    fname = _KNOWLEDGE_FILES.get(target)
    if not fname:
        return f"Неизвестный файл: {target}. Доступны: {list(_KNOWLEDGE_FILES.keys())}"

    fpath = knowledge_dir / fname
    if not fpath.exists():
        # Создаём файл если нет
        fpath.write_text("", encoding="utf-8")

    if mode == "append":
        with open(fpath, "a", encoding="utf-8") as f:
            f.write(f"\n\n<!-- обновлено {datetime.now().strftime('%d.%m.%Y %H:%M')} -->\n")
            f.write(content.strip())
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
        pass
