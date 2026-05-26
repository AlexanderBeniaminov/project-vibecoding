#!/bin/bash
# Автоматический коммит всех изменений в репозитории Project VibeCoding.
# Запускается Stop-хуком Claude Code после каждой сессии.

REPO="/Users/user/Desktop/ИИ вайбкодинг/Project vibecoding"

cd "$REPO" || exit 1

# Синхронизируем knowledge-файлы ассистента из CLAUDE.md
python3 "$REPO/infrastructure/sync_knowledge.py" 2>/dev/null

# Проверяем есть ли изменения (tracked + untracked)
if git diff --quiet \
   && git diff --cached --quiet \
   && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    exit 0  # Нет изменений — ничего не делаем
fi

# Коммитим всё
git add -A

TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
git commit -m "auto: сохранение изменений $TIMESTAMP

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" 2>/dev/null

# Пушим (не падаем если нет интернета)
git push 2>/dev/null || true
