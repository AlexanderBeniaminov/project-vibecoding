#!/usr/bin/env bash
# Детектор дрейфа — проверяет что ключевые инварианты сессии 2026-06-17 на месте.
# Запуск: bash aihotel/drift_detect.sh
# Восстановление при расхождении: git checkout last-known-good -- <файл>

PASS=0; FAIL=0
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

check() {
  local desc="$1"; local file="$2"; local pattern="$3"
  if grep -q "$pattern" "$ROOT/$file" 2>/dev/null; then
    echo "  ✅ $desc"
    PASS=$((PASS+1))
  else
    echo "  ❌ ДРЕЙФ: $desc"
    echo "     Файл: $file"
    echo "     Ожидаем: $pattern"
    FAIL=$((FAIL+1))
  fi
}

echo "=== Drift Detector — сессия 2026-06-17 ==="
echo ""
echo "── travelline_collector.py ──"
check "read_monblan() существует"        "aihotel/travelline_collector.py"   "def read_monblan"
check "read_segments() существует"       "aihotel/travelline_collector.py"   "def read_segments"
check "_gs_client() существует"          "aihotel/travelline_collector.py"   "def _gs_client"
check "SEG_MAPPING определён (10 пар)"   "aihotel/travelline_collector.py"   "SEG_MAPPING"
check "MONBLAN_SHEET_ID hardcoded"       "aihotel/travelline_collector.py"   "MONBLAN_SHEET_ID"
check "main() вызывает read_monblan"     "aihotel/travelline_collector.py"   "read_monblan(client"
check "main() вызывает read_segments"    "aihotel/travelline_collector.py"   "read_segments(client"
check "write_to_sheet принимает client"  "aihotel/travelline_collector.py"   "write_to_sheet(client"

echo ""
echo "── agents.yml ──"
check "cron 23:50 МСК активен"           "aihotel/.github/workflows/agents.yml" "50 20 \* \* 1"
check "step привязан к 23:50 МСК"        "aihotel/.github/workflows/agents.yml" "github.event.schedule == '50 20 \* \* 1'"

echo ""
echo "── helper_bot.py ──"
check "NAMES_PAT или TEAM_ALIASES есть"  "telegram-helper/helper_bot.py"    "NAMES_PAT\|TEAM_ALIASES"
check "TASK_FOR_RE есть"                 "telegram-helper/helper_bot.py"    "TASK_FOR_RE"

echo ""
echo "── telegram-manager/manager_bot.py (сессия 2026-06-25) ──"
check "handler ловит F.photo"            "telegram-manager/manager_bot.py"  "F\.photo"
check "читает message.caption"           "telegram-manager/manager_bot.py"  "message\.caption"
check "мгновенный typing после auth"     "telegram-manager/manager_bot.py"  "send_chat_action.*typing"

echo ""
echo "── telegram-assistant/assistant_bot.py (сессия 2026-06-25) ──"
check "нет echo «Верно?» для reminder"   "telegram-assistant/assistant_bot.py" "Сразу вызывай add_reminder"
check "запрет Верно? в ЖЁСТКИХ ЗАПРЕТАХ" "telegram-assistant/assistant_bot.py" "НЕЛЬЗЯ перед add_reminder"

echo ""
echo "── deploy.sh health-check (сессия 2026-06-25) ──"
check "assistant deploy ждёт active"     "telegram-assistant/deploy.sh"     "is-active telegram-assistant"
check "manager deploy ждёт active"       "telegram-manager/deploy.sh"       "is-active telegram-manager"

echo ""
echo "── Git ──"
HEAD=$(cd "$ROOT" && git rev-parse HEAD)
TAG=$(cd "$ROOT" && git rev-parse last-known-good 2>/dev/null || echo "НЕТ ТЕГА")
echo "  HEAD:           $HEAD"
echo "  last-known-good: $TAG"
if [ "$HEAD" = "$TAG" ]; then
  echo "  ✅ HEAD = last-known-good"
  ((PASS++))
else
  echo "  ℹ️  HEAD опережает last-known-good (нормально если были коммиты после закрытия сессии)"
  ((PASS++))
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "✅ Все $PASS проверок прошли — дрейфа нет."
else
  echo "❌ Провалено: $FAIL / $((PASS+FAIL))"
  echo ""
  echo "Восстановление из источника правды:"
  echo "  git fetch origin && git checkout last-known-good -- aihotel/travelline_collector.py"
  echo "  git checkout last-known-good -- aihotel/.github/workflows/agents.yml"
  echo "  git checkout last-known-good -- telegram-helper/helper_bot.py"
  exit 1
fi
