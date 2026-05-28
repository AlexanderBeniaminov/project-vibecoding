#!/bin/bash
set -e

echo "==> Деплой telegram-manager..."

rsync -av \
  --exclude='config.py' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  telegram-manager/ parser@185.184.122.158:/home/parser/bots/manager/

echo "==> Деплой shared модуля..."
ssh parser@185.184.122.158 "mkdir -p /home/parser/bots/shared"
rsync -av \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='rules.db' \
  telegram-manager/shared/ parser@185.184.122.158:/home/parser/bots/shared/

echo "==> Перезапуск telegram-manager..."
ssh parser@185.184.122.158 "systemctl restart telegram-manager"

echo "==> Готово. Статус:"
ssh parser@185.184.122.158 "systemctl status telegram-manager --no-pager -l"
