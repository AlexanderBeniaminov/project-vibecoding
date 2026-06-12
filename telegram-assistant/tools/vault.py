from __future__ import annotations
import re
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_MSK = ZoneInfo("Europe/Moscow")

CARD_TYPES = {"note", "idea", "learning", "decision", "contact_card"}


def _vault_dir() -> Path:
    try:
        sys.path.insert(0, "/home/parser/bots/assistant")
        import config
        return Path(getattr(config, "VAULT_DIR", "/home/parser/bots/assistant/vault"))
    except Exception:
        return Path("/home/parser/bots/assistant/vault")


def _slug(title: str) -> str:
    s = re.sub(r"[^\w\s-]", "", title.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:60] or "card"


def append_daily(text: str) -> None:
    """Добавляет запись в сегодняшний daily-лог vault."""
    vault = _vault_dir()
    daily_dir = vault / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    ts = datetime.now(_MSK).strftime("%H:%M")
    with open(daily_dir / f"{today}.md", "a", encoding="utf-8") as f:
        f.write(f"- {ts} {text}\n")


def save_card(card_type: str, title: str, content: str, tags: list | str = "") -> str:
    """
    Сохраняет карточку знаний в vault.
    Типы: note, idea, learning, decision, contact_card
    """
    if card_type not in CARD_TYPES:
        card_type = "note"
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    vault = _vault_dir()
    card_dir = vault / f"{card_type}s"
    card_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    base = f"{today}-{_slug(title)}"
    fpath = card_dir / f"{base}.md"
    if fpath.exists():
        fpath = card_dir / f"{base}-2.md"

    tag_yaml = "[" + ", ".join(tags) + "]" if tags else "[]"
    card = (
        f"---\n"
        f"type: {card_type}\n"
        f"tags: {tag_yaml}\n"
        f"status: active\n"
        f"access_count: 1\n"
        f"last_accessed: {today}\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{content.strip()}\n"
    )
    fpath.write_text(card, encoding="utf-8")
    rel = fpath.relative_to(vault)
    return f"Карточка [{card_type}] «{title}» сохранена → vault/{rel}"


def search_vault(query: str, max_results: int = 8) -> str:
    """Ищет по заголовкам и содержимому всех карточек в vault."""
    vault = _vault_dir()
    if not vault.exists():
        return "Vault пуст — карточек ещё нет."

    query_lower = query.lower()
    results = []

    for md_file in sorted(vault.rglob("*.md"), reverse=True):
        if md_file.name == "MEMORY.md":
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if query_lower not in text.lower():
            continue
        lines = [l for l in text.splitlines()
                 if l.strip() and not l.startswith("---")
                 and not any(l.startswith(k) for k in ("type:", "tags:", "status:", "access_count:", "last_accessed:"))]
        preview = next((l.lstrip("# ").strip() for l in lines), "")[:120]
        rel = md_file.relative_to(vault)
        results.append(f"📄 {rel} — {preview}")

    if not results:
        return f"По запросу «{query}» ничего не найдено в vault."
    return "\n".join(results[:max_results])


def get_daily_log(date_iso: str | None = None) -> str:
    """Читает daily-лог за дату (по умолчанию сегодня)."""
    if not date_iso:
        date_iso = date.today().isoformat()
    fpath = _vault_dir() / "daily" / f"{date_iso}.md"
    if not fpath.exists():
        return ""
    return fpath.read_text(encoding="utf-8")
