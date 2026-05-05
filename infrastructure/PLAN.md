# План выполнения — Проект "Сервер + VPN"

## ✅ Выполнено
- [x] VPS создан на Beget (84.54.30.209, Ubuntu 24.04)
- [x] setup.sh запущен и выполнен успешно
- [x] WireGuard установлен на сервере (wg-quick@wg0)
- [x] Профили alex.conf и oleg.conf созданы, QR-коды скачаны
- [x] WireGuard установлен на Mac, alex_split импортирован и подключён ✅
- [x] oleg_split импортирован на Mac (для ноутбука Олега)
- [x] Порт WireGuard изменён с 51820 → 443/UDP (обход блокировки РКН)
- [x] UFW FORWARD policy = ACCEPT (пересылка пакетов разрешена)
- [x] AllowedIPs = 10.66.66.0/24 (split-tunnel, только трафик к серверу)
- [x] Оба VPN работают одновременно: WireGuard + Happ Plus (Германия)
- [x] SSH-конфиг на Mac: команда `ssh server` → 84.54.30.209
- [x] Python venv создан (/home/parser/venv)
- [x] Все библиотеки установлены
- [x] Код всех парсеров написан
- [x] Код ботов написан
- [x] Cron-задания настроены
- [x] fail2ban и UFW настроены
- [x] Файлы трекинга: CLAUDE.md, PROJECT.md, PLAN.md, STATUS.md

---

## ✅ Шаг 1 — VPN исправлен (ВЫПОЛНЕНО)

**Проблема:** При подключении WireGuard интернет падает полностью.

**Причина 1:** UFW блокирует пересылку пакетов (DEFAULT_FORWARD_POLICY=DROP).

**Причина 2:** AllowedIPs = 0.0.0.0/0 — весь трафик через VPN, должен быть split-tunnel.

**Действия на сервере:**
```bash
# 1. Разрешить пересылку пакетов в UFW
sed -i 's/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw
ufw reload

# 2. Проверить что ip_forward активен
cat /proc/sys/net/ipv4/ip_forward  # должно быть 1

# 3. Перегенерировать конфиги клиентов с split-tunnel AllowedIPs
# (только зарубежные IP через VPN)
```

**Действия на Mac:**
- Обновить alex.conf с правильным AllowedIPs (split-tunnel список)
- Импортировать oleg.conf

**Результат:** Российские сайты открываются напрямую, claude.ai — через VPN.

---

## 📱 Шаг 2 — WireGuard на всех устройствах (СЛЕДУЮЩИЙ)

- [x] Mac: alex_split и oleg_split импортированы
- [ ] Android Huawei Nova 11: установить WireGuard, отсканировать alex_qr.png и oleg_qr.png
- [ ] oleg_split перенести на ноутбук Олега

---

## 🤖 Шаг 3 — Создать Telegram боты

**Действия:**
1. Открыть Telegram → найти @BotFather
2. Написать `/newbot`
3. Имя: `Alex Parser Bot` (или любое)
4. Username: `alex_parser_XXXXX_bot` (уникальный)
5. Скопировать TOKEN
6. Повторить для oleg
7. Узнать CHAT_ID: написать боту `/start`, потом открыть:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`

**Что нужно получить:**
- `TELEGRAM_BOT_TOKEN` для alex
- `TELEGRAM_BOT_TOKEN` для oleg
- `TELEGRAM_CHAT_ID` для alex
- `TELEGRAM_CHAT_ID` для oleg

---

## ⚙️ Шаг 4 — Заполнить settings.py

**Файл:** `/home/parser/config/alex/settings.py`

Нужно вставить:
- `TELEGRAM_BOT_TOKEN` — из BotFather
- `TELEGRAM_CHAT_ID` — ID чата
- `SPREADSHEET_IDS` — ID Google таблиц (из ссылки на таблицу)
- `TRAVELLINE_LOGIN` / `TRAVELLINE_PASSWORD`
- `IIKO_API_KEY` / `IIKO_HOST`
- Telethon: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`
- `VK_ACCESS_TOKEN` (если нужен VK бот)

Повторить для oleg.

---

## 📤 Шаг 5 — Загрузить service_account.json

**С Mac на сервер:**
```bash
scp ~/путь/к/service_account.json root@84.54.30.209:/home/parser/config/alex/service_account.json
scp ~/путь/к/service_account.json root@84.54.30.209:/home/parser/config/oleg/service_account.json
```

Расшарить Google таблицы на email Service Account.

---

## 💻 Шаг 6 — VS Code Remote-SSH

**Установить расширение:**
- VS Code → Extensions → Remote - SSH → Install

**Настроить ~/.ssh/config на Mac:**
```
Host server-alex
    HostName 84.54.30.209
    User parser
    IdentityFile ~/.ssh/id_rsa

Host server-oleg
    HostName 84.54.30.209
    User parser
    IdentityFile ~/.ssh/id_rsa
```

---

## 📂 Шаг 7 — Перенести существующие iiko-скрипты

Скопировать готовые скрипты iiko с Mac на сервер:
```bash
scp ~/путь/к/iiko_script.py root@84.54.30.209:/home/parser/parsers/
```

---

## ✅ Шаг 8 — Финальная проверка

```bash
# На сервере
bash /home/parser/check_all.sh
```

**Чек-лист:**
- [ ] claude.ai открывается через VPN (alex)
- [ ] claude.ai открывается через VPN (oleg)
- [ ] Российские сайты без VPN (split-tunnel)
- [ ] Парсер → Google Sheets (alex)
- [ ] Парсер → Google Sheets (oleg)
- [ ] Telegram бот alex отвечает на /ping
- [ ] Telegram бот oleg отвечает на /ping
- [ ] Watchdog перезапускает VPN при падении
- [ ] Cron запускает парсеры по расписанию
