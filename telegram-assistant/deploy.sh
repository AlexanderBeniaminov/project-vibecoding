#!/bin/bash
# Деплой бота на сервер. Запуск: bash deploy.sh
set -e

REMOTE="server"
REMOTE_PATH="/home/parser/bots/assistant"
LOCAL_PATH="$(cd "$(dirname "$0")" && pwd)"

echo "Синхронизирую файлы..."
rsync -avz \
  --exclude 'config.py' \
  --exclude 'data/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.git/' \
  --exclude '.gitignore' \
  "$LOCAL_PATH/" "$REMOTE:$REMOTE_PATH/"

echo "Перезапускаю сервис..."
ssh "$REMOTE" "systemctl restart telegram-assistant"

echo "Статус:"
ssh "$REMOTE" "systemctl status telegram-assistant --no-pager | grep -E 'Active|python'"
echo "Done."
