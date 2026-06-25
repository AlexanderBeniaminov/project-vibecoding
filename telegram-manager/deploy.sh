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

# Проверяем что сервис поднялся без ошибок (ждём до 10 сек)
echo "==> Проверяю запуск..."
for i in $(seq 1 10); do
    STATE=$(ssh server "systemctl is-active telegram-manager" 2>/dev/null)
    if [ "$STATE" = "active" ]; then
        ERRORS=$(ssh server "journalctl -u telegram-manager -n 5 --no-pager 2>/dev/null | grep -i 'error\|traceback\|exception'" || true)
        if [ -n "$ERRORS" ]; then
            echo "⚠️  Сервис active, но есть ошибки в логах:"
            echo "$ERRORS"
            exit 1
        fi
        echo "✅ telegram-manager запущен (попытка $i/10)"
        break
    fi
    if [ "$i" -eq 10 ]; then
        echo "❌ Сервис не поднялся за 10 сек. Статус: $STATE"
        ssh server "journalctl -u telegram-manager -n 20 --no-pager"
        exit 1
    fi
    sleep 1
done
