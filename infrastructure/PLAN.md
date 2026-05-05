# План выполнения — Проект "Сервер + VPN"

## ✅ Выполнено

- [x] VPS создан на Beget (84.54.30.209, Ubuntu 24.04)
- [x] WireGuard установлен на сервере (wg-quick@wg0)
- [x] Профили alex.conf и oleg.conf созданы, QR-коды скачаны
- [x] WireGuard установлен на Mac, alex_split импортирован и подключён
- [x] oleg_split импортирован на Mac (для ноутбука Олега)
- [x] Порт WireGuard изменён с 51820 → 443/UDP (обход РКН)
- [x] UFW FORWARD policy = ACCEPT
- [x] AllowedIPs = 10.66.66.0/24 (split-tunnel, только трафик к серверу)
- [x] Оба VPN работают одновременно: WireGuard + Happ Plus (Германия)
- [x] SSH-конфиг: `ssh server` → 84.54.30.209, ключ id_ed25519
- [x] Python venv создан (/home/parser/venv)
- [x] Библиотеки установлены (requests, gspread, google-auth, loguru, python-telegram-bot)
- [x] Все парсеры скопированы на сервер
- [x] account_manager.py — добавлена поддержка VK MAX (notify_vkmax)
- [x] vk_max_bot.py переписан под VK MAX Bot API (botapi.max.ru)
- [x] daily_report.py — ежедневный отчёт из Google Sheets → VK MAX
- [x] settings.py для alex заполнен (VK MAX токен + iiko таблица)
- [x] service_account.json для alex загружен на сервер
- [x] Cron: daily_report.py запускается в 06:00 UTC (09:00 МСК)
- [x] Ежедневный отчёт протестирован — сообщение приходит в VK MAX ✅

---

## 🔲 Следующие шаги

### Шаг 1 — Systemd-сервис для VK MAX бота (автозапуск)

**На сервере** (чтобы бот отвечал на /ping, /status, /report):
```bash
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
systemctl status vkmax-bot
```

---

### Шаг 2 — Настройка oleg

Нужны данные:
- VK MAX токен (если у Олега отдельный бот) или тот же бот с другим user_id
- Google Sheets таблицы Олега
- service_account.json (тот же файл, что для alex)

```bash
# Скопировать service_account.json для oleg
scp /home/parser/config/alex/service_account.json \
    /home/parser/config/oleg/service_account.json
```

---

### Шаг 3 — Telegram боты (опционально)

1. Открыть Telegram → @BotFather → `/newbot`
2. Скопировать TOKEN
3. Написать боту `/start`, узнать CHAT_ID через:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Добавить в settings.py:
   ```python
   TELEGRAM_BOT_TOKEN = "..."
   TELEGRAM_CHAT_ID   = "..."
   ```

---

### Шаг 4 — WireGuard на Android (Huawei Nova 11)

1. Установить приложение WireGuard из AppGallery
2. QR-коды уже готовы: alex_qr.png и oleg_qr.png (скачаны ранее)
3. Отсканировать QR в приложении

---

### Шаг 5 — VS Code Remote-SSH

```
# ~/.ssh/config уже есть Host server → 84.54.30.209
# Установить в VS Code: расширение "Remote - SSH"
# Подключиться: Ctrl+Shift+P → "Remote-SSH: Connect to Host" → server
```

---

### Шаг 6 — Финальная проверка

```bash
# На сервере
bash /home/parser/check_all.sh
```

**Чек-лист:**
- [ ] VK MAX бот отвечает на /ping
- [ ] Ежедневный отчёт приходит в 09:00 МСК
- [ ] Cron запускает парсеры по расписанию
- [ ] WireGuard watchdog работает
- [ ] Логи пишутся в /home/parser/logs/
