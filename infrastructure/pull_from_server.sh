#!/bin/bash
# Забирает актуальные знания бота с сервера в git-репозиторий.
# Вызывается из auto_commit.sh после каждой сессии Claude.

REMOTE="server"
REMOTE_BOT="/home/parser/bots/assistant"
LOCAL_KNOWLEDGE="/Users/user/Desktop/ИИ вайбкодинг/Project vibecoding/telegram-assistant/knowledge"

# Проверяем доступность сервера (таймаут 5 сек)
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$REMOTE" true 2>/dev/null; then
    exit 0  # Сервер недоступен — пропускаем молча
fi

# Экспортируем SQLite-факты в bot_facts.md на сервере
ssh "$REMOTE" "python3 $REMOTE_BOT/export_facts.py" 2>/dev/null || true

# Тянем bot_facts.md с сервера
scp -q "$REMOTE:$REMOTE_BOT/knowledge/bot_facts.md" "$LOCAL_KNOWLEDGE/bot_facts.md" 2>/dev/null || true

echo "pull_from_server: готово"
