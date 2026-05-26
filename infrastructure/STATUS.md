# Проект: Сервер + VPN — Статус задач

## Сервер
- ВПС: u1host.com (Германия), IP 185.184.122.158, Ubuntu 24.04, 2GB RAM, 30GB SSD
- SSH: `ssh server` → root@185.184.122.158
- VPN: 3X-UI + VLESS + XTLS-Reality, порт 443/TCP, клиент — Happ Plus (Mac) / Hiddify (Android)
- Панель 3X-UI: `http://185.184.122.158:26712/0bdmSbbW17viRgbmb6/`
- Один пользователь (Александр), два Claude-аккаунта (alex/oleg) — смена через `claude logout`
- Старый Beget 84.54.30.209: отключить ~2026-05-17

---

## БЛОК 1 — Сервер и VPN

| Задача | Статус | Примечание |
|--------|--------|------------|
| VPS создан на u1host.com (Германия) | ✅ Готово | 185.184.122.158 |
| setup.sh выполнен | ✅ Готово | Всё зелёное |
| AmneziaWG остановлен и отключён | ✅ Готово | inactive, disabled |
| UFW: только нужные порты (22, 443/tcp, 26712/tcp) | ✅ Готово | WireGuard UDP и wg0 правила удалены |
| 3X-UI панель установлена (v3.0.1) | ✅ Готово | active since 2026-05-13, порт 26712 |
| VLESS + XTLS-Reality inbound настроен | ✅ Готово | Порт 443, SNI www.microsoft.com |
| Клиент alex создан | ✅ Готово | UUID: 41be9190-..., vless:// в ~/Downloads/vless_links.txt |
| Клиент android создан | ✅ Готово | UUID: 93f50951-..., vless:// в ~/Downloads/vless_links.txt |
| Клиент oleg создан | ✅ Готово | UUID: 124c8dc3-..., добавлен через SQLite |
| QR-коды сгенерированы | ✅ Готово | ~/Downloads/qr_alex.png, qr_android.png, qr_oleg.png |
| SSH-конфиг на Mac | ✅ Готово | `ssh server` = новый, `ssh server-old` = Beget |
| Happ Plus на Mac — подключён | ✅ Готово | ПОДКЛЮЧЕН через alex (VLESS), 336ms |
| Сервер alex добавлен в Happ Plus | ✅ Готово | vless:// импортирован, активен |
| VS Code Claude Code работает | ✅ Готово | через Happ Plus TUN (порт 10808) |
| Claude десктоп на Mac | ✅ Готово | работает после перезапуска с активным Happ Plus |
| Hiddify на Android (Huawei Nova 11) | ✅ Готово | Установлен, подключён через android-клиент |

---

## БЛОК 2 — Python и парсеры

| Задача | Статус | Примечание |
|--------|--------|------------|
| Python venv создан | ✅ Готово | /home/parser/venv (Python 3.12) |
| Библиотеки установлены | ✅ Готово | requests, gspread, loguru, telegram и др. |
| account_manager.py | ✅ Готово | /home/parser/scrapers/ |
| travelline_parser.py | ✅ Готово | /home/parser/scrapers/ |
| iiko_parser.py | ✅ Готово | /home/parser/scrapers/ |
| telegram_monitor.py | ✅ Готово | /home/parser/scrapers/ |
| universal_parser.py | ✅ Готово | /home/parser/scrapers/ |
| settings.py (alex) | ✅ Готово | VK MAX + iiko таблица |
| service_account.json (alex) | ✅ Готово | aihotel-bot@aihotel-gubaha.iam.gserviceaccount.com |
| config/oleg удалён | ✅ Готово | oleg = тот же пользователь, отдельная папка не нужна |
| Cron: ежедневный отчёт | ✅ Готово | 06:00 UTC (09:00 МСК) через daily_report.py |

---

## БЛОК 3 — Боты

| Задача | Статус | Примечание |
|--------|--------|------------|
| telegram_status_bot.py | ✅ Готово | /home/parser/bots/ |
| vk_max_bot.py | ✅ Готово | /home/parser/bots/ |
| daily_report.py | ✅ Готово | cron 06:00 UTC, отчёты приходят |
| VK MAX бот как systemd-сервис | ⏸ Опционально | нужен только для /ping /status в реальном времени |
| Telegram бот | ⏸ Опционально | нужен TOKEN из BotFather если потребуется |

---

## БЛОК 4 — Google Sheets

| Задача | Статус | Примечание |
|--------|--------|------------|
| Service Account | ✅ Готово | aihotel-bot@aihotel-gubaha.iam.gserviceaccount.com |
| Таблица iiko | ✅ Подключена | 1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI |

---

## БЛОК 5 — Финальная проверка

| Задача | Статус | Примечание |
|--------|--------|------------|
| Hiddify подключается на Mac (alex) | ❌ Нужно проверить | После настройки 3X-UI |
| curl ifconfig.me через VPN = немецкий IP | ❌ Нужно проверить | |
| claude.ai открывается через VPN | ❌ Нужно проверить | |
| Telegram работает через VPN | ❌ Нужно проверить | |
| Ежедневный отчёт VK MAX | ❌ Нужно проверить | Подождать 09:00 МСК |
| Отключить Beget | ❌ После 3 дней проверки | beget.com панель управления |

---

## Текущий приоритет

1. ✅ ~~Сервер настроен: 3X-UI v3.0.1, VLESS+Reality, 3 клиента, UFW чистый~~
2. ✅ ~~Happ Plus на Mac подключён к серверу alex (VLESS), VS Code работает~~
3. ✅ ~~Claude десктоп работает — перезапуск с активным Happ Plus~~
4. ✅ ~~Android — Hiddify установлен и подключён~~
5. 🤖 **VK MAX бот** — запустить как systemd-сервис (опционально)
6. ⏱ Подождать 09:00 МСК — ежедневный отчёт VK MAX
7. 🗑 Через 3 дня — отключить Beget на beget.com
