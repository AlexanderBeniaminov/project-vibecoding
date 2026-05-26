from .db import get_conn

def add_note(text: str, tags: str = "") -> str:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO notes (text, tags) VALUES (?, ?)", (text.strip(), tags.strip())
    )
    note_id = cur.lastrowid
    conn.commit()
    conn.close()
    return f"Заметка #{note_id} сохранена."

def list_notes(limit: int = 10) -> str:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, text, tags, created_at FROM notes ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    if not rows:
        return "Заметок пока нет."
    lines = []
    for r in rows:
        tag_str = f" [{r['tags']}]" if r['tags'] else ""
        lines.append(f"#{r['id']} ({r['created_at'][:16]}){tag_str}: {r['text'][:200]}")
    return "\n".join(lines)

def search_notes(query: str) -> str:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, text, tags, created_at FROM notes WHERE text LIKE ? OR tags LIKE ? ORDER BY id DESC LIMIT 10",
        (f"%{query}%", f"%{query}%"),
    ).fetchall()
    conn.close()
    if not rows:
        return f"По запросу «{query}» заметок не найдено."
    lines = []
    for r in rows:
        lines.append(f"#{r['id']} ({r['created_at'][:16]}): {r['text'][:200]}")
    return "\n".join(lines)

def delete_note(note_id: int) -> str:
    conn = get_conn()
    conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()
    return f"Заметка #{note_id} удалена."
