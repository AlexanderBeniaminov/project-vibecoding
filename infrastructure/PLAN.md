# План — Проект "Сервер + VPN"
# Обновлено: 2026-05-14

## ✅ Выполнено

### Сервер (u1host, Германия, 185.184.122.158)
- [x] VPS создан на u1host.com (Ubuntu 24.04, 2GB RAM, 30GB SSD)
- [x] setup.sh выполнен — всё зелёное
- [x] SSH-конфиг: `ssh server` → 185.184.122.158, ключ id_ed25519
- [x] UFW настроен: 22/tcp (SSH), 443/tcp (VLESS), 26712/tcp (3X-UI панель)

### VPN — VLESS + XTLS-Reality (3X-UI)
- [x] AmneziaWG остановлен и заменён на VLESS
- [x] 3X-UI v3.0.1 установлен, активен
- [x] VLESS+Reality inbound: порт 443, SNI www.microsoft.com
- [x] Клиенты созданы: alex, oleg, android (vless:// ссылки в ~/Downloads/)
- [x] QR-коды: ~/Downloads/qr_alex.png, qr_oleg.png, qr_android.png

### Клиенты
- [x] Happ Plus на Mac — подключён через сервер alex (VLESS, 336ms)
- [x] Claude десктоп на Mac — работает через Happ Plus
- [x] VS Code Claude Code — работает через Happ Plus
- [x] Hiddify на Android (Huawei Nova 11) — установлен и подключён
- [x] Telegram на телефоне — работает (SOCKS5 → Hiddify)

### Python и боты
- [x] Python venv: /home/parser/venv (Python 3.12)
- [x] Все парсеры на сервере: iiko, travelline, telegram, universal
- [x] settings.py для alex заполнен (VK MAX + iiko)
- [x] service_account.json для alex загружен
- [x] Cron: daily_report.py → 06:00 UTC (09:00 МСК) → отчёт в VK MAX ✅

---

## 🔲 Осталось сделать

### Приоритет 1 — Beget (через 3 дня, ~2026-05-17)
- [ ] Убедиться что новый сервер стабильно работает 3 дня
- [ ] Зайти на beget.com → отключить/удалить VPS 84.54.30.209

### Приоритет 2 — Аккаунт Олег
- [ ] Заполнить settings.py для oleg (VK MAX токен, iiko, Google Sheets)
- [ ] Скопировать service_account.json: `cp /home/parser/config/alex/service_account.json /home/parser/config/oleg/`
- [ ] Протестировать парсеры для oleg

### Приоритет 3 — Интерактивный VK MAX бот (опционально)
vk_max_bot.py отвечает на /ping, /status, /report в реальном времени.
Нужен только если хочешь управлять сервером через VK MAX.
```bash
# На сервере:
cat > /etc/systemd/system/vkmax-bot.service << 'EOF'
[Unit]
Description=VK MAX Bot (alex)
After=network.target

[Service]
User=root
WorkingDirectory=/home/parser
ExecStart=/home/parser/venv/bin/python3 /home/parser/bots/vk_max_bot.py alex
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vkmax-bot
systemctl start vkmax-bot
```

### Приоритет 4 — Настройка Олег на Mac
- [ ] В Happ Plus нажать + → вставить vless:// ссылку oleg из ~/Downloads/vless_links.txt

---

## Важные детали
- Happ Plus нужно запускать ДО Claude десктоп и VS Code
- Панель 3X-UI: http://185.184.122.158:26712/0bdmSbbW17viRgbmb6/
- Ссылки VLESS: ~/Downloads/vless_links.txt
- Старый Beget: 84.54.30.209 — отключить 2026-05-17
