#!/usr/bin/env bash
# Детектор дрейфа настроек content-bot. Запуск: bash content-bot/check-drift.sh
# Проверяет: конфиг VPS, статус сервиса, структуру knowledge/, ключевые инварианты кода

set -euo pipefail
FAIL=0
ok()   { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; FAIL=1; }

echo "=== content-bot drift check ==="

# 1. VPS — сервис запущен
echo "--- Сервис ---"
if ssh server "systemctl is-active content-bot" 2>/dev/null | grep -q "^active"; then
  ok "content-bot active на VPS"
else
  fail "content-bot НЕ active на VPS"
fi

# 2. VPS — конфиг содержит нужные поля
echo "--- Config на VPS ---"
for field in OWNER_USER_ID SPREADSHEET_URL ALLOWED_USER_IDS; do
  if ssh server "grep -q '$field' /home/parser/bots/content-bot/config.py" 2>/dev/null; then
    ok "config.py: $field присутствует"
  else
    fail "config.py: $field ОТСУТСТВУЕТ"
  fi
done

# 2а. Алексей в ALLOWED_USER_IDS
if ssh server "grep 'ALLOWED_USER_IDS' /home/parser/bots/content-bot/config.py" 2>/dev/null | grep -q "1641605920"; then
  ok "config.py: Алексей (1641605920) в ALLOWED_USER_IDS"
else
  fail "config.py: Алексей (1641605920) ОТСУТСТВУЕТ в ALLOWED_USER_IDS"
fi

# 2б. Тестовый канал (не боевой)
if ssh server "grep 'CHANNEL_ID' /home/parser/bots/content-bot/config.py" 2>/dev/null | grep -q "\-1003762594394"; then
  ok "config.py: CHANNEL_ID — тестовый (-1003762594394)"
else
  fail "config.py: CHANNEL_ID — проверь, не переключился ли на боевой"
fi

# 3. Knowledge-файлы на VPS
echo "--- Knowledge ---"
for f in tone-of-voice.md audience.md business.md alexy-guide.md; do
  if ssh server "test -f /home/parser/bots/content-bot/knowledge/$f" 2>/dev/null; then
    ok "knowledge/$f на VPS"
  else
    fail "knowledge/$f ОТСУТСТВУЕТ на VPS"
  fi
done

# 4. Инварианты кода (локально — источник правды в git)
echo "--- Код ---"
BOT="content-bot/bot.py"
DB="content-bot/db.py"
SEARCH="content-bot/search.py"

grep -q "_cooldown_overlap" "$BOT" && ok "bot.py: анти-повтор _cooldown_overlap есть" || fail "bot.py: _cooldown_overlap ОТСУТСТВУЕТ"
grep -q "OWNER_USER_ID" "$BOT" && ok "bot.py: OWNER_USER_ID используется" || fail "bot.py: OWNER_USER_ID не используется"
grep -q "review:" "$BOT" && ok "bot.py: обработчик review: (На согласование) есть" || fail "bot.py: обработчик review: ОТСУТСТВУЕТ"
grep -q "region.*ru-ru" "$SEARCH" && ok "search.py: region=ru-ru" || fail "search.py: region=ru-ru ОТСУТСТВУЕТ"
grep -q "published_at" "$DB" && ok "db.py: get_published_texts проверяет published_at" || fail "db.py: published_at не используется в get_published_texts"
grep -q "_STATUS_ON_REVIEW" "content-bot/sheets.py" && ok "sheets.py: _STATUS_ON_REVIEW определён" || fail "sheets.py: _STATUS_ON_REVIEW ОТСУТСТВУЕТ"

echo "=== Итог ==="
[ "$FAIL" -eq 0 ] && echo "✅ Всё на месте — no drift" || echo "❌ Есть расхождения — см. выше"
exit $FAIL
