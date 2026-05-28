#!/bin/bash
set -e

echo "==> Деплой telegram-manager..."

rsync -av -e ssh \
  --exclude='config.py' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  telegram-manager/ server:/home/parser/bots/manager/

echo "==> Деплой shared модуля..."
rsync -av -e ssh \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='rules.db' \
  telegram-manager/shared/ server:/home/parser/bots/shared/

echo "==> Права на папки..."
ssh server "sudo chown -R parser:parser /home/parser/bots/shared /home/parser/bots/manager"

echo "==> Перезапуск telegram-manager..."
ssh server "systemctl restart telegram-manager"

echo "==> Готово. Статус:"
ssh server "systemctl status telegram-manager --no-pager -l"
