"""
files.py — Поиск по локальному индексу файлов Mac.

Индекс синхронизируется Mac-сторонним indexer.py (каждые 2 часа) → rsync → data/file_index.json
"""
import json
from datetime import datetime
from pathlib import Path

import config

# Путь к индексу на сервере
INDEX_PATH = Path(getattr(config, "DB_PATH", "/home/parser/bots/assistant/data/assistant.db")).parent / "file_index.json"

# Кеш: загружаем индекс один раз, перечитываем если файл изменился
_cache: dict | None = None
_cache_mtime: float = 0.0


def _load_index() -> dict | None:
    global _cache, _cache_mtime
    if not INDEX_PATH.exists():
        return None
    try:
        mtime = INDEX_PATH.stat().st_mtime
        if _cache is not None and mtime == _cache_mtime:
            return _cache
        _cache = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        _cache_mtime = mtime
        return _cache
    except Exception:
        return None


def search_files(query: str, file_type: str | None = None) -> str:
    """Поиск файлов по имени и содержимому. Возвращает до 10 результатов."""
    index = _load_index()
    if index is None:
        return (
            "Индекс файлов Mac не найден. "
            "Запустите индексацию: python3 ~/file-indexer/indexer.py"
        )

    indexed_at = index.get("indexed_at", "неизвестно")
    try:
        dt = datetime.fromisoformat(indexed_at)
        indexed_at_fmt = dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        indexed_at_fmt = indexed_at

    files = index.get("files", [])
    if not files:
        return f"Индекс пуст (обновлён {indexed_at_fmt})."

    # Нормализуем запрос
    words = query.lower().split()

    # Фильтр по типу файла
    if file_type:
        ext_filter = file_type.lower().lstrip(".")
        files = [f for f in files if f.get("ext", "").lstrip(".").lower() == ext_filter]
        if not files:
            return f"Файлов с расширением .{ext_filter} не найдено (индекс от {indexed_at_fmt})."

    # Скоринг: имя файла = 2 очка за слово, содержимое = 1 очко
    scored = []
    for f in files:
        name_lower = f.get("name", "").lower()
        snippet_lower = f.get("snippet", "").lower()
        path_lower = f.get("path", "").lower()

        score = 0
        for w in words:
            if w in name_lower:
                score += 2
            if w in snippet_lower:
                score += 1
            # частичное совпадение в пути (папка проекта)
            if w in path_lower and w not in name_lower:
                score += 1

        if score > 0:
            scored.append((score, f))

    if not scored:
        return f'Ничего не найдено по запросу "{query}" (индекс от {indexed_at_fmt}).'

    # Сортировка: score DESC, modified DESC
    scored.sort(key=lambda x: (x[0], x[1].get("modified", "")), reverse=True)
    top = scored[:10]

    lines = [f"Найдено {len(scored)} файлов (индекс от {indexed_at_fmt}), показываю топ {len(top)}:\n"]
    for i, (score, f) in enumerate(top, 1):
        name = f.get("name", "")
        path = f.get("path", "")
        ext = f.get("ext", "")
        modified = f.get("modified", "")[:10]  # только дата
        size = f.get("size_mb", 0)
        snippet = f.get("snippet", "")

        # Короткий путь — убираем /Users/user/
        short_path = path.replace("/Users/user/", "~/")

        line = f"{i}. **{name}**"
        if modified:
            line += f" ({modified})"
        if size:
            line += f" [{size} MB]"
        line += f"\n   📁 {short_path}"
        if snippet and any(w in snippet.lower() for w in words):
            # Показываем фрагмент вокруг совпадения
            for w in words:
                idx = snippet.lower().find(w)
                if idx >= 0:
                    start = max(0, idx - 60)
                    end = min(len(snippet), idx + 120)
                    excerpt = ("..." if start > 0 else "") + snippet[start:end] + ("..." if end < len(snippet) else "")
                    line += f"\n   💬 {excerpt.strip()}"
                    break
        lines.append(line)

    return "\n".join(lines)
