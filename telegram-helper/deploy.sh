#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVER="server"  # SSH alias из ~/.ssh/config
REMOTE_DIR="/home/parser/bots/helper"

echo "Синхронизирую файлы..."
rsync -avz --exclude '__pycache__' --exclude '*.pyc' --exclude 'config.py' --exclude 'data/' \
  "$SCRIPT_DIR/" "$SERVER:$REMOTE_DIR/"

echo "Перезапускаю сервис..."
ssh "$SERVER" "systemctl restart telegram-helper && sleep 3 && systemctl status telegram-helper --no-pager | grep -E 'Active|PID'"

echo ""
echo "Последние логи:"
ssh "$SERVER" "journalctl -u telegram-helper -n 5 --no-pager"
echo "Done."
