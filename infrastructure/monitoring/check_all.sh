#!/bin/bash
# check_all.sh — Финальная проверка всей системы
# Запуск: bash /home/parser/check_all.sh

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✅ $1${NC}"; }
fail() { echo -e "${RED}  ❌ $1${NC}"; ERRORS=$((ERRORS+1)); }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }

ERRORS=0

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         ФИНАЛЬНАЯ ПРОВЕРКА ИНФРАСТРУКТУРЫ               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── 1. WireGuard ──────────────────────────────────────────────
echo "🔒 WireGuard VPN:"
if systemctl is-active --quiet wg-quick@wg0; then
    ok "wg-quick@wg0 запущен"
else
    fail "wg-quick@wg0 НЕ запущен"
fi

if ip link show wg0 > /dev/null 2>&1; then
    ok "Интерфейс wg0 существует"
else
    fail "Интерфейс wg0 не найден"
fi

PEERS=$(wg show wg0 2>/dev/null | grep -c "peer:" || echo 0)
if [ "$PEERS" -ge 2 ]; then
    ok "Клиентов VPN: $PEERS (alex + oleg)"
else
    warn "Клиентов VPN: $PEERS (ожидается 2)"
fi

# ── 2. Файлы конфигов ─────────────────────────────────────────
echo ""
echo "📁 Конфиги WireGuard:"
for f in /etc/wireguard/clients/alex.conf /etc/wireguard/clients/oleg.conf; do
    [ -f "$f" ] && ok "$f" || fail "$f отсутствует"
done

echo ""
echo "📁 Конфиги парсеров:"
for acc in alex oleg; do
    f="/home/parser/config/$acc/settings.py"
    if [ -f "$f" ]; then
        if grep -q "\[ВСТАВЬ" "$f" 2>/dev/null; then
            warn "$f — есть незаполненные поля [ВСТАВЬ...]"
        else
            ok "$f заполнен"
        fi
    else
        fail "$f отсутствует"
    fi
done

for acc in alex oleg; do
    f="/home/parser/config/$acc/service_account.json"
    [ -f "$f" ] && ok "service_account.json ($acc)" || warn "service_account.json ($acc) — не загружен"
done

# ── 3. Python ─────────────────────────────────────────────────
echo ""
echo "🐍 Python:"
if [ -f "/home/parser/venv/bin/python" ]; then
    ok "virtualenv создан"
    VER=$(/home/parser/venv/bin/python --version 2>&1)
    ok "$VER"
else
    fail "virtualenv не найден"
fi

for lib in requests gspread telegram playwright telethon vk_api pandas; do
    /home/parser/venv/bin/python -c "import $lib" 2>/dev/null \
        && ok "import $lib" || fail "import $lib — не установлен"
done

# ── 4. Cron ───────────────────────────────────────────────────
echo ""
echo "⏰ Cron-задания (parser):"
CRON=$(crontab -u parser -l 2>/dev/null)
for job in travelline_parser iiko_parser telegram_monitor wg-watchdog; do
    echo "$CRON" | grep -q "$job" \
        && ok "cron: $job" || warn "cron: $job — не найден"
done

# ── 5. Безопасность ───────────────────────────────────────────
echo ""
echo "🔒 Безопасность:"
systemctl is-active --quiet fail2ban && ok "fail2ban запущен" || fail "fail2ban не запущен"
ufw status | grep -q "Status: active" && ok "UFW активен" || fail "UFW не активен"
ufw status | grep -q "22/tcp" && ok "SSH порт открыт" || warn "SSH порт: проверь UFW"
ufw status | grep -q "51820/udp" && ok "WireGuard порт открыт" || warn "WireGuard порт: проверь UFW"

# ── 6. Сеть ───────────────────────────────────────────────────
echo ""
echo "🌐 Сетевая связность:"
curl -s --max-time 5 https://api.anthropic.com > /dev/null 2>&1 \
    && ok "Доступ к api.anthropic.com" || warn "api.anthropic.com недоступен с сервера (VPN клиенту нужен)"
curl -s --max-time 5 https://api.github.com > /dev/null 2>&1 \
    && ok "Доступ к github.com" || fail "github.com недоступен"
curl -s --max-time 5 https://api.telegram.org > /dev/null 2>&1 \
    && ok "Доступ к api.telegram.org" || fail "telegram.org недоступен"

# ── 7. Место на диске ─────────────────────────────────────────
echo ""
echo "💾 Ресурсы:"
DISK=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK" -lt 80 ]; then
    ok "Диск: $(df -h / | awk 'NR==2 {print $3"/"$2, "("$5")"}') использовано"
else
    warn "Диск: $DISK% — место заканчивается!"
fi

FREE_RAM=$(free -m | awk 'NR==2 {print $7}')
[ "$FREE_RAM" -gt 200 ] && ok "RAM свободно: ${FREE_RAM}MB" || warn "RAM свободно: ${FREE_RAM}MB — мало"

# ── ИТОГ ──────────────────────────────────────────────────────
echo ""
if [ "$ERRORS" -eq 0 ]; then
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗"
    echo    "║       ✅ ВСЕ ПРОВЕРКИ ПРОШЛИ УСПЕШНО                   ║"
    echo -e "╚══════════════════════════════════════════════════════════╝${NC}"
else
    echo -e "${RED}╔══════════════════════════════════════════════════════════╗"
    echo    "║       ❌ ОШИБОК: $ERRORS — проверь выделенные строки         ║"
    echo -e "╚══════════════════════════════════════════════════════════╝${NC}"
fi
echo ""
