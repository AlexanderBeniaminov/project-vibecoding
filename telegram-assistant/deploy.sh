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

# 6. Проверяем что сервис поднялся без ошибок (ждём до 10 сек)
echo "Проверяю запуск..."
for i in $(seq 1 10); do
    STATE=$(ssh "$REMOTE" "systemctl is-active telegram-assistant" 2>/dev/null)
    if [ "$STATE" = "active" ]; then
        # Дополнительно: нет ли ERROR в логах последних 5 строк
        ERRORS=$(ssh "$REMOTE" "journalctl -u telegram-assistant -n 5 --no-pager 2>/dev/null | grep -i 'error\|traceback\|exception'" || true)
        if [ -n "$ERRORS" ]; then
            echo "⚠️  Сервис active, но есть ошибки в логах:"
            echo "$ERRORS"
            exit 1
        fi
        echo "✅ telegram-assistant запущен (попытка $i/10)"
        break
    fi
    if [ "$i" -eq 10 ]; then
        echo "❌ Сервис не поднялся за 10 сек. Статус: $STATE"
        ssh "$REMOTE" "journalctl -u telegram-assistant -n 20 --no-pager"
        exit 1
    fi
    sleep 1
done

echo "Done."
