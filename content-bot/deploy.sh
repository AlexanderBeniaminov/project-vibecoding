#!/bin/bash
# Деплой Content Bot на сервер. Запуск: bash content-bot/deploy.sh
set -e

REMOTE="server"
REMOTE_PATH="/home/parser/bots/content-bot"
LOCAL_PATH="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$LOCAL_PATH/.." && pwd)"

# 1. Коммитим если есть изменения в репозитории
cd "$REPO_ROOT"
if ! git diff --quiet || ! git diff --cached --quiet \
   || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    git add -A
    git commit -m "auto: sync content-bot перед деплоем $(date '+%Y-%m-%d %H:%M')

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" 2>/dev/null || true
    git push 2>/dev/null || true
fi

# 2. Деплоим на сервер
echo "Синхронизируем файлы на сервер..."
ssh "$REMOTE" "mkdir -p $REMOTE_PATH/data"
rsync -avz \
  --exclude 'config.py' \
  --exclude 'data/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.git/' \
  --exclude '.gitignore' \
  "$LOCAL_PATH/" "$REMOTE:$REMOTE_PATH/"

# 3. Перезапускаем сервис
echo "Перезапускаю сервис..."
ssh "$REMOTE" "systemctl restart content-bot"

echo "Статус:"
ssh "$REMOTE" "systemctl status content-bot --no-pager | grep -E 'Active|python'"
echo "Done."
