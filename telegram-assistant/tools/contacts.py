from .db import get_conn


def _find(query: str) -> list:
    conn = get_conn()
    q = f"%{query.lower()}%"
    rows = conn.execute(
        "SELECT * FROM contacts WHERE lower(name) LIKE ? OR phone LIKE ? OR telegram LIKE ? ORDER BY name",
        (q, q, q),
    ).fetchall()
    conn.close()
    return rows


def _format(row) -> str:
    parts = [f"👤 {row['name']}"]
    if row['phone']:
        parts.append(f"📞 {row['phone']}")
    if row['telegram']:
        tg = row['telegram'] if row['telegram'].startswith('@') else f"@{row['telegram']}"
        parts.append(f"✈️ {tg}")
    if row['email']:
        parts.append(f"✉️ {row['email']}")
    if row['notes']:
        parts.append(f"📝 {row['notes']}")
    return "\n".join(parts)


def add_contact(name: str, phone: str = "", telegram: str = "", email: str = "", notes: str = "") -> str:
    conn = get_conn()
    existing = conn.execute("SELECT id FROM contacts WHERE lower(name) = ?", (name.lower(),)).fetchone()
    if existing:
        conn.execute(
            "UPDATE contacts SET phone=?, telegram=?, email=?, notes=? WHERE id=?",
            (phone, telegram, email, notes, existing["id"]),
        )
        conn.commit()
        conn.close()
        return f"Контакт «{name}» обновлён."
    conn.execute(
        "INSERT INTO contacts (name, phone, telegram, email, notes) VALUES (?, ?, ?, ?, ?)",
        (name, phone, telegram, email, notes),
    )
    conn.commit()
    conn.close()
    return f"Контакт «{name}» сохранён."


def find_contact(query: str) -> str:
    rows = _find(query)
    if not rows:
        return f"Контакт «{query}» не найден."
    return "\n\n".join(_format(r) for r in rows[:5])


def list_contacts() -> str:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM contacts ORDER BY name").fetchall()
    conn.close()
    if not rows:
        return "Список контактов пуст."
    return "\n".join(f"#{r['id']} {r['name']}" + (f" {r['telegram']}" if r['telegram'] else "") + (f" {r['phone']}" if r['phone'] else "") for r in rows)


def delete_contact(contact_id: int) -> str:
    conn = get_conn()
    conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    conn.commit()
    conn.close()
    return f"Контакт #{contact_id} удалён."


def format_contact_card(query: str) -> str:
    """Возвращает карточку контакта для пересылки."""
    rows = _find(query)
    if not rows:
        return f"Контакт «{query}» не найден."
    row = rows[0]
    return _format(row)
