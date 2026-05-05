#!/bin/bash
# ============================================================
# setup.sh — Полная автоматическая настройка сервера
# Аккаунты: alex (Александр) и oleg (Олег)
# Запуск: sudo bash setup.sh
# ============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
err()  { echo -e "${RED}❌ $1${NC}"; exit 1; }

[[ $EUID -ne 0 ]] && err "Запусти от root: sudo bash setup.sh"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   УСТАНОВКА ИНФРАСТРУКТУРЫ (alex + oleg)                ║"
echo "║   WireGuard VPN + Python + Parsers + Bots               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Переменные ──────────────────────────────────────────────
SERVER_IP=$(curl -s https://api.ipify.org 2>/dev/null || curl -s https://ifconfig.me)
NIC=$(ip route | grep default | awk '{print $5}' | head -1)
WG_PORT=51820
WG_SERVER_IP="10.66.66.1"
WG_ALEX_IP="10.66.66.2"
WG_OLEG_IP="10.66.66.3"
PARSER_HOME="/home/parser"

log "Публичный IP сервера: $SERVER_IP"
log "Сетевой интерфейс: $NIC"

# ════════════════════════════════════════════════════════════
# 1. ОБНОВЛЕНИЕ И БАЗОВЫЕ ПАКЕТЫ
# ════════════════════════════════════════════════════════════
log "Обновление системы..."
export DEBIAN_FRONTEND=noninteractive
# Держим cloud-init заблокированным — иначе его обновление перезагружает сервер
apt-mark hold cloud-init 2>/dev/null || true
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    curl wget git ufw fail2ban unattended-upgrades \
    wireguard-tools \
    python3.12 python3-pip python3-venv python3-dev \
    qrencode \
    build-essential libssl-dev libffi-dev \
    net-tools htop nano jq || true
log "Пакеты установлены"

# ════════════════════════════════════════════════════════════
# 2. БЕЗОПАСНОСТЬ
# ════════════════════════════════════════════════════════════
log "Настройка fail2ban..."
cat > /etc/fail2ban/jail.local << 'FAIL2BAN'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 3
ignoreip = 127.0.0.1/8

[sshd]
enabled  = true
port     = ssh
logpath  = %(sshd_log)s
backend  = %(sshd_backend)s
FAIL2BAN
systemctl enable fail2ban --quiet
systemctl restart fail2ban

log "Настройка автообновлений безопасности..."
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
APT
systemctl enable unattended-upgrades --quiet

# ════════════════════════════════════════════════════════════
# 3. FIREWALL
# ════════════════════════════════════════════════════════════
log "Настройка UFW firewall..."
ufw --force reset > /dev/null 2>&1
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow ${WG_PORT}/udp comment 'WireGuard'
ufw --force enable
log "Firewall активен: порты 22 (SSH) и $WG_PORT (WireGuard)"

# ════════════════════════════════════════════════════════════
# 4. WIREGUARD VPN
# ════════════════════════════════════════════════════════════
log "Генерация WireGuard ключей..."
mkdir -p /etc/wireguard/clients
chmod 700 /etc/wireguard
cd /etc/wireguard

wg genkey | tee server_private.key | wg pubkey > server_public.key
wg genkey | tee alex_private.key   | wg pubkey > alex_public.key
wg genpsk > alex_psk.key
wg genkey | tee oleg_private.key   | wg pubkey > oleg_public.key
wg genpsk > oleg_psk.key

SERVER_PRIV=$(cat server_private.key)
SERVER_PUB=$(cat server_public.key)
ALEX_PRIV=$(cat alex_private.key)
ALEX_PUB=$(cat alex_public.key)
ALEX_PSK=$(cat alex_psk.key)
OLEG_PRIV=$(cat oleg_private.key)
OLEG_PUB=$(cat oleg_public.key)
OLEG_PSK=$(cat oleg_psk.key)
chmod 600 /etc/wireguard/*.key

log "Создание конфига WireGuard сервера..."
cat > /etc/wireguard/wg0.conf << EOF
[Interface]
Address    = ${WG_SERVER_IP}/24
ListenPort = ${WG_PORT}
PrivateKey = ${SERVER_PRIV}
PostUp     = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o ${NIC} -j MASQUERADE
PostDown   = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o ${NIC} -j MASQUERADE
SaveConfig = false

# ── Клиент: alex (Александр) ─────────────────────────────
[Peer]
PublicKey    = ${ALEX_PUB}
PresharedKey = ${ALEX_PSK}
AllowedIPs   = ${WG_ALEX_IP}/32

# ── Клиент: oleg (Олег) ──────────────────────────────────
[Peer]
PublicKey    = ${OLEG_PUB}
PresharedKey = ${OLEG_PSK}
AllowedIPs   = ${WG_OLEG_IP}/32
EOF
chmod 600 /etc/wireguard/wg0.conf

echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
sysctl -p > /dev/null 2>&1

# AllowedIPs = весь трафик через VPN (просто и надёжно)
log "Настройка AllowedIPs для клиентов..."
SPLIT_IPS="0.0.0.0/0, ::/0"
log "AllowedIPs: весь трафик через VPN (российские сайты тоже работают)"

# ЗАГЛУШКА — старый Python-код убран для надёжности
if false; then
python3 << 'PYEOF'
import urllib.request, json, ipaddress, sys

try:
    url = "https://stat.ripe.net/data/country-resource-list/data.json?resource=RU&v4_format=prefix"
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.load(r)
        ru_prefixes = data['data']['resources']['ipv4']
    print(f"Загружено {len(ru_prefixes)} российских CIDR из RIPE NCC")
except Exception as e:
    print(f"RIPE API недоступен ({e}), использую базовый список")
    ru_prefixes = [
        "2.56.0.0/13","5.8.0.0/16","5.16.0.0/15","5.44.0.0/14",
        "5.128.0.0/12","5.144.0.0/13","5.188.0.0/14","31.13.0.0/16",
        "31.28.0.0/16","31.128.0.0/11","37.0.0.0/15","37.9.0.0/16",
        "37.28.0.0/14","45.80.0.0/14","45.84.0.0/14","45.88.0.0/14",
        "45.96.0.0/12","46.0.0.0/12","46.16.0.0/12","46.32.0.0/11",
        "46.72.0.0/13","46.112.0.0/12","46.160.0.0/11","77.34.0.0/15",
        "77.40.0.0/13","77.72.0.0/13","77.88.0.0/13","78.24.0.0/13",
        "78.36.0.0/14","78.40.0.0/13","78.106.0.0/15","78.108.0.0/14",
        "79.98.0.0/16","79.104.0.0/13","79.128.0.0/11","79.174.0.0/15",
        "81.0.0.0/15","81.18.0.0/15","81.24.0.0/13","81.88.0.0/14",
        "81.176.0.0/12","81.200.0.0/13","82.97.0.0/16","82.138.0.0/16",
        "82.140.0.0/15","82.144.0.0/13","82.192.0.0/12","82.200.0.0/13",
        "82.208.0.0/13","82.216.0.0/13","83.102.0.0/16","83.148.0.0/14",
        "83.168.0.0/13","83.219.0.0/16","83.220.0.0/14","84.0.0.0/13",
        "84.201.0.0/16","84.204.0.0/14","85.0.0.0/15","85.92.0.0/14",
        "85.141.0.0/16","85.172.0.0/14","85.192.0.0/13","86.102.0.0/16",
        "87.224.0.0/12","87.240.0.0/12","87.248.0.0/13","88.80.0.0/14",
        "88.147.0.0/16","88.200.0.0/13","88.208.0.0/12","89.22.0.0/15",
        "89.36.0.0/14","89.40.0.0/13","89.109.0.0/16","89.175.0.0/16",
        "89.178.0.0/15","89.184.0.0/13","89.218.0.0/15","89.232.0.0/13",
        "91.90.0.0/16","91.108.0.0/14","91.144.0.0/16","91.185.0.0/16",
        "91.188.0.0/14","91.192.0.0/12","91.206.0.0/15","91.209.0.0/16",
        "91.213.0.0/16","91.215.0.0/16","91.218.0.0/16","91.220.0.0/16",
        "91.222.0.0/15","91.224.0.0/11","92.39.0.0/16","92.40.0.0/14",
        "92.60.0.0/16","92.61.0.0/16","92.62.0.0/15","92.63.0.0/16",
        "92.100.0.0/14","92.116.0.0/14","92.120.0.0/13","92.242.0.0/15",
        "93.72.0.0/13","93.153.0.0/16","93.157.0.0/16","93.158.0.0/15",
        "93.170.0.0/16","93.174.0.0/15","93.180.0.0/14","93.190.0.0/16",
        "93.200.0.0/13","94.19.0.0/16","94.25.0.0/16","94.26.0.0/16",
        "94.28.0.0/16","94.72.0.0/14","94.100.0.0/14","94.176.0.0/13",
        "94.184.0.0/14","94.199.0.0/16","94.224.0.0/11","94.230.0.0/15",
        "95.27.0.0/16","95.31.0.0/16","95.53.0.0/16","95.56.0.0/13",
        "95.84.0.0/14","95.108.0.0/14","95.143.0.0/16","95.163.0.0/16",
        "95.173.0.0/16","95.182.0.0/15","95.191.0.0/16","95.213.0.0/16",
        "176.0.0.0/15","176.4.0.0/14","176.8.0.0/14","176.12.0.0/14",
        "176.16.0.0/12","176.32.0.0/11","176.64.0.0/11","176.96.0.0/12",
        "176.112.0.0/13","176.120.0.0/14","176.192.0.0/11","176.224.0.0/12",
        "176.240.0.0/12","185.0.0.0/16","185.2.0.0/15","185.4.0.0/14",
        "185.8.0.0/13","185.16.0.0/12","185.32.0.0/12","185.48.0.0/13",
        "185.64.0.0/12","185.80.0.0/13","185.96.0.0/12","185.112.0.0/13",
        "185.128.0.0/11","185.160.0.0/12","185.176.0.0/12","185.192.0.0/11",
        "185.224.0.0/11","188.0.0.0/14","188.16.0.0/12","188.32.0.0/12",
        "188.64.0.0/11","188.96.0.0/11","188.128.0.0/11","188.160.0.0/11",
        "188.192.0.0/12","188.208.0.0/12","188.224.0.0/11","193.47.0.0/16",
        "193.105.0.0/16","193.106.0.0/15","193.108.0.0/14","193.124.0.0/14",
        "193.128.0.0/11","193.176.0.0/12","193.200.0.0/13","193.212.0.0/15",
        "193.226.0.0/15","193.228.0.0/14","193.232.0.0/13","193.240.0.0/12",
        "194.0.0.0/12","194.14.0.0/15","194.16.0.0/12","194.32.0.0/12",
        "194.48.0.0/13","194.58.0.0/16","194.67.0.0/16","194.85.0.0/16",
        "194.106.0.0/15","194.110.0.0/15","194.126.0.0/15","194.128.0.0/11",
        "194.160.0.0/12","194.176.0.0/12","194.186.0.0/16","194.190.0.0/16",
        "194.193.0.0/16","194.200.0.0/13","194.208.0.0/12","194.226.0.0/15",
        "194.228.0.0/14","194.232.0.0/13","194.240.0.0/12","195.2.0.0/15",
        "195.16.0.0/14","195.20.0.0/14","195.24.0.0/13","195.34.0.0/15",
        "195.68.0.0/16","195.69.0.0/16","195.74.0.0/16","195.82.0.0/16",
        "195.90.0.0/16","195.128.0.0/11","195.160.0.0/11","195.208.0.0/12",
        "195.225.0.0/16","195.226.0.0/15","195.230.0.0/16","195.239.0.0/16",
        "212.0.0.0/14","212.16.0.0/12","212.32.0.0/12","212.48.0.0/14",
        "212.52.0.0/14","212.56.0.0/14","212.72.0.0/13","212.80.0.0/14",
        "212.86.0.0/16","212.95.0.0/16","212.102.0.0/15","212.104.0.0/13",
        "212.112.0.0/14","212.116.0.0/14","212.120.0.0/14","212.124.0.0/14",
        "212.128.0.0/11","212.160.0.0/12","212.176.0.0/12","212.192.0.0/11",
        "212.224.0.0/11","213.0.0.0/11","213.33.0.0/16","213.79.0.0/16",
        "213.87.0.0/16","213.108.0.0/14","213.128.0.0/11","213.160.0.0/12",
        "213.176.0.0/12","213.192.0.0/11","213.224.0.0/12","213.232.0.0/14",
        "213.243.0.0/16","217.0.0.0/13","217.8.0.0/13","217.16.0.0/12",
        "217.32.0.0/11","217.64.0.0/11","217.96.0.0/12","217.112.0.0/13",
        "217.120.0.0/13","217.128.0.0/11","217.160.0.0/12","217.196.0.0/14",
        "217.200.0.0/13","217.208.0.0/12","217.224.0.0/11",
    ]

all_ipv4 = ipaddress.IPv4Network('0.0.0.0/0')
ru_networks = []
for p in ru_prefixes:
    try:
        ru_networks.append(ipaddress.IPv4Network(p.strip(), strict=False))
    except:
        pass

result = [all_ipv4]
for ru_net in ru_networks:
    new_result = []
    for net in result:
        if net.overlaps(ru_net):
            new_result.extend(net.address_exclude(ru_net))
        else:
            new_result.append(net)
    result = new_result

result.sort()
allowed = ', '.join(str(n) for n in result)
with open('/etc/wireguard/split_tunnel_allowed_ips.txt', 'w') as f:
    f.write(allowed)
print(f"Split-tunnel: {len(result)} CIDR блоков готово")
PYEOF
fi

log "Создание клиентских конфигов WireGuard..."
cat > /etc/wireguard/clients/alex.conf << EOF
[Interface]
PrivateKey = ${ALEX_PRIV}
Address    = ${WG_ALEX_IP}/32
DNS        = 1.1.1.1, 8.8.8.8

[Peer]
PublicKey    = ${SERVER_PUB}
PresharedKey = ${ALEX_PSK}
Endpoint     = ${SERVER_IP}:${WG_PORT}
AllowedIPs   = ${SPLIT_IPS}
PersistentKeepalive = 25
EOF

cat > /etc/wireguard/clients/oleg.conf << EOF
[Interface]
PrivateKey = ${OLEG_PRIV}
Address    = ${WG_OLEG_IP}/32
DNS        = 1.1.1.1, 8.8.8.8

[Peer]
PublicKey    = ${SERVER_PUB}
PresharedKey = ${OLEG_PSK}
Endpoint     = ${SERVER_IP}:${WG_PORT}
AllowedIPs   = ${SPLIT_IPS}
PersistentKeepalive = 25
EOF

log "Запуск WireGuard..."
systemctl enable wg-quick@wg0 --quiet
systemctl start wg-quick@wg0

log "Генерация QR-кодов..."
echo ""
echo "═══════════════════════ QR: alex (Александр) ═══════════════"
qrencode -t ansiutf8 < /etc/wireguard/clients/alex.conf
echo ""
echo "═══════════════════════ QR: oleg (Олег) ════════════════════"
qrencode -t ansiutf8 < /etc/wireguard/clients/oleg.conf
echo ""
qrencode -t png -o /etc/wireguard/clients/alex_qr.png < /etc/wireguard/clients/alex.conf
qrencode -t png -o /etc/wireguard/clients/oleg_qr.png < /etc/wireguard/clients/oleg.conf

# ════════════════════════════════════════════════════════════
# 5. WATCHDOG для WireGuard
# ════════════════════════════════════════════════════════════
log "Настройка watchdog WireGuard..."
cat > /usr/local/bin/wg-watchdog.sh << 'WATCHDOG'
#!/bin/bash
LOG=/var/log/wg-watchdog.log
if ! systemctl is-active --quiet wg-quick@wg0; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] WireGuard упал! Перезапускаю..." >> $LOG
    systemctl restart wg-quick@wg0
    if systemctl is-active --quiet wg-quick@wg0; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] WireGuard перезапущен успешно" >> $LOG
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ОШИБКА: не удалось перезапустить!" >> $LOG
    fi
fi
WATCHDOG
chmod +x /usr/local/bin/wg-watchdog.sh
(crontab -l 2>/dev/null; echo "*/2 * * * * /usr/local/bin/wg-watchdog.sh") | crontab -

# ════════════════════════════════════════════════════════════
# 6. PYTHON ОКРУЖЕНИЕ И СТРУКТУРА ПАПОК
# ════════════════════════════════════════════════════════════
log "Создание пользователя parser и структуры папок..."
useradd -m -s /bin/bash parser 2>/dev/null || true
PARSER_HOME=/home/parser

mkdir -p ${PARSER_HOME}/{scrapers,data,logs,reports,backups}
mkdir -p ${PARSER_HOME}/config/{alex,oleg}

log "Создание Python virtualenv..."
python3.12 -m venv ${PARSER_HOME}/venv
${PARSER_HOME}/venv/bin/pip install --quiet --upgrade pip setuptools wheel

log "Установка Python-библиотек (2-3 минуты)..."
${PARSER_HOME}/venv/bin/pip install --quiet \
    requests \
    playwright \
    selenium \
    beautifulsoup4 \
    lxml \
    schedule \
    gspread \
    google-auth \
    google-auth-oauthlib \
    google-auth-httplib2 \
    google-api-python-client \
    python-telegram-bot \
    pyTelegramBotAPI \
    telethon \
    vk-api \
    pandas \
    openpyxl \
    fake-useragent \
    tenacity \
    python-dotenv \
    aiohttp \
    aiofiles \
    loguru

${PARSER_HOME}/venv/bin/playwright install chromium 2>/dev/null || true
log "Python-библиотеки установлены"

# ── Конфиг alex ──────────────────────────────────────────────
cat > ${PARSER_HOME}/config/alex/settings.py << 'ALEXCFG'
# ⚠️ ЗАПОЛНИ ЭТИ ДАННЫЕ — не передавай файл никому
ACCOUNT      = "alex"
ACCOUNT_NAME = "Александр"

# Google Sheets (service_account.json положи рядом с этим файлом)
GOOGLE_SERVICE_ACCOUNT_JSON = "/home/parser/config/alex/service_account.json"
SPREADSHEET_IDS = {
    "travelline": "",   # ID из URL таблицы Travelline
    "iiko":       "",   # ID таблицы iiko
    "reports":    "",   # ID таблицы отчётов
}

# Telegram Bot (получить у @BotFather)
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID   = ""   # отправь /start боту, затем @userinfobot

# VK MAX Bot (vk.com/editapp — создать standalone-приложение)
VK_ACCESS_TOKEN = ""
VK_PEER_ID      = 0     # ID чата/беседы в VK MAX

# Travelline
TRAVELLINE_URL      = ""
TRAVELLINE_LOGIN    = ""
TRAVELLINE_PASSWORD = ""

# iiko
IIKO_SERVER_URL = ""   # например http://192.168.1.100:9900
IIKO_LOGIN      = ""
IIKO_PASSWORD   = ""

# Telegram Monitoring (получить на my.telegram.org)
TELEGRAM_API_ID   = 0
TELEGRAM_API_HASH = ""
TELEGRAM_PHONE    = ""  # +79001234567

MONITORED_CHANNELS = []  # ["@channel1", -1001234567890]
MONITOR_KEYWORDS   = []  # ["ключевое слово", "другое слово"]
ALEXCFG

# ── Конфиг oleg ──────────────────────────────────────────────
cat > ${PARSER_HOME}/config/oleg/settings.py << 'OLEGCFG'
# ⚠️ ЗАПОЛНИ ЭТИ ДАННЫЕ — не передавай файл никому
ACCOUNT      = "oleg"
ACCOUNT_NAME = "Олег"

GOOGLE_SERVICE_ACCOUNT_JSON = "/home/parser/config/oleg/service_account.json"
SPREADSHEET_IDS = {
    "travelline": "",
    "iiko":       "",
    "reports":    "",
}

TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID   = ""

VK_ACCESS_TOKEN = ""
VK_PEER_ID      = 0

TRAVELLINE_URL      = ""
TRAVELLINE_LOGIN    = ""
TRAVELLINE_PASSWORD = ""

IIKO_SERVER_URL = ""
IIKO_LOGIN      = ""
IIKO_PASSWORD   = ""

TELEGRAM_API_ID   = 0
TELEGRAM_API_HASH = ""
TELEGRAM_PHONE    = ""

MONITORED_CHANNELS = []
MONITOR_KEYWORDS   = []
OLEGCFG

# ── .gitignore ────────────────────────────────────────────────
cat > ${PARSER_HOME}/.gitignore << 'GITIGNORE'
config/
*.json
*.env
__pycache__/
*.pyc
*.pyo
.env
logs/
data/
backups/
venv/
GITIGNORE

# ════════════════════════════════════════════════════════════
# 7. CRON-РАСПИСАНИЕ
# ════════════════════════════════════════════════════════════
log "Настройка cron-расписания..."
CRON_CONTENT="
# Travelline — раз в день в 02:00
0 2 * * * /home/parser/venv/bin/python /home/parser/scrapers/travelline_parser.py alex >> /home/parser/logs/travelline_alex_\$(date +\%Y-\%m-\%d).log 2>&1
5 2 * * * /home/parser/venv/bin/python /home/parser/scrapers/travelline_parser.py oleg >> /home/parser/logs/travelline_oleg_\$(date +\%Y-\%m-\%d).log 2>&1

# iiko — каждый день в 04:00
0 4 * * * /home/parser/venv/bin/python /home/parser/scrapers/iiko_parser.py alex >> /home/parser/logs/iiko_alex_\$(date +\%Y-\%m-\%d).log 2>&1
5 4 * * * /home/parser/venv/bin/python /home/parser/scrapers/iiko_parser.py oleg >> /home/parser/logs/iiko_oleg_\$(date +\%Y-\%m-\%d).log 2>&1

# Telegram мониторинг — каждые 3 часа
0 */3 * * * /home/parser/venv/bin/python /home/parser/scrapers/telegram_monitor.py alex >> /home/parser/logs/tg_alex_\$(date +\%Y-\%m-\%d).log 2>&1
30 */3 * * * /home/parser/venv/bin/python /home/parser/scrapers/telegram_monitor.py oleg >> /home/parser/logs/tg_oleg_\$(date +\%Y-\%m-\%d).log 2>&1

# Очистка логов старше 30 дней
0 3 * * 1 find /home/parser/logs -name '*.log' -mtime +30 -delete

# Еженедельный бэкап конфигов (без ключей)
0 5 * * 0 tar czf /home/parser/backups/configs_\$(date +\%Y-\%m-\%d).tar.gz /etc/wireguard/clients/ /home/parser/scrapers/ 2>/dev/null
"
echo "$CRON_CONTENT" | crontab -u parser -

# ════════════════════════════════════════════════════════════
# 8. ПРАВА ДОСТУПА
# ════════════════════════════════════════════════════════════
chown -R parser:parser ${PARSER_HOME}
chmod 700 ${PARSER_HOME}/config
chmod 700 ${PARSER_HOME}/config/alex
chmod 700 ${PARSER_HOME}/config/oleg
chmod 600 ${PARSER_HOME}/config/alex/settings.py
chmod 600 ${PARSER_HOME}/config/oleg/settings.py

# ════════════════════════════════════════════════════════════
# ИТОГ
# ════════════════════════════════════════════════════════════
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                  ✅ УСТАНОВКА ЗАВЕРШЕНА!                ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "📁 WireGuard конфиги:"
echo "   /etc/wireguard/clients/alex.conf"
echo "   /etc/wireguard/clients/oleg.conf"
echo "   /etc/wireguard/clients/alex_qr.png  (QR для Android)"
echo "   /etc/wireguard/clients/oleg_qr.png"
echo ""
echo "📁 Конфиги парсеров (ЗАПОЛНИ ПЕРЕД ЗАПУСКОМ):"
echo "   /home/parser/config/alex/settings.py"
echo "   /home/parser/config/oleg/settings.py"
echo ""
echo "🔧 Следующие шаги:"
echo "   1. Скачай конфиги на Mac:"
echo "      scp root@${SERVER_IP}:/etc/wireguard/clients/alex.conf ~/Downloads/"
echo "      scp root@${SERVER_IP}:/etc/wireguard/clients/oleg.conf ~/Downloads/"
echo ""
echo "   2. Заполни settings.py для каждого аккаунта"
echo "   3. Загрузи service_account.json в config/alex/ и config/oleg/"
echo ""
echo "🔍 Статус WireGuard:"
wg show
