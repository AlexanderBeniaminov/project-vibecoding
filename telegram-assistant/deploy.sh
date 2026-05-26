#!/bin/bash
# Деплой бота на сервер. Запуск: bash telegram-assistant/deploy.sh
set -e

REMOTE="server"
REMOTE_PATH="/home/parser/bots/assistant"
LOCAL_PATH="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$LOCAL_PATH/.." && pwd)"

# 1. Сначала забираем актуальные знания С сервера (чтобы не затереть)
echo "Синхронизируем знания с сервера..."
ssh "$REMOTE" "python3 $REMOTE_PATH/export_facts.py" 2>/dev/null || true
scp -q "$REMOTE:$REMOTE_PATH/knowledge/bot_facts.md" \
    "$LOCAL_PATH/knowledge/bot_facts.md" 2>/dev/null || true

# 2. Обновляем projects.md и user.md из CLAUDE.md
python3 "$REPO_ROOT/infrastructure/sync_knowledge.py" 2>/dev/null || true

# 3. Коммитим если есть изменения в репозитории
cd "$REPO_ROOT"
if ! git diff --quiet || ! git diff --cached --quiet \
   || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    git add -A
    git commit -m "auto: sync перед деплоем $(date '+%Y-%m-%d %H:%M')

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" 2>/dev/null || true
    git push 2>/dev/null || true
fi

# 4. Деплоим на сервер
echo "Синхронизируем файлы на сервер..."
rsync -avz \
  --exclude 'config.py' \
  --exclude 'data/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.git/' \
  --exclude '.gitignore' \
  "$LOCAL_PATH/" "$REMOTE:$REMOTE_PATH/"

# 5. Перезапускаем сервис
echo "Перезапускаю сервис..."
ssh "$REMOTE" "systemctl restart telegram-assistant"

echo "Статус:"
ssh "$REMOTE" "systemctl status telegram-assistant --no-pager | grep -E 'Active|python'"
echo "Done."
