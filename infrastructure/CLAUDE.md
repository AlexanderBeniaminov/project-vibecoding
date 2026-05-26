# Инструкции для Claude — Проект "Сервер + VPN"

## Кто пользователь
- Александр, Россия, Mac M2, VS Code
- Новичок в Linux/SSH/DevOps
- Один пользователь, два Claude-аккаунта: alex (основной) и oleg (резервный, тот же человек — для смены при исчерпании лимитов)

## Правила работы
- Всегда давать готовые команды для copy-paste — без сокращений
- Не объяснять теорию, если не спрашивают
- Сначала делать, потом объяснять по запросу
- Всегда указывать: эту команду на Маке или на сервере
- Перед началом сессии читать STATUS.md

## Сервер
- IP: 185.184.122.158 (u1host.com, Германия)
- ОС: Ubuntu 24.04.4, 2GB RAM, 30GB SSD
- SSH: `ssh server` (алиас в ~/.ssh/config, ключ ~/.ssh/id_ed25519)
- VPN: **3X-UI + VLESS + XTLS-Reality**, порт **443/TCP**, SNI: microsoft.com
- Панель 3X-UI: `http://185.184.122.158:26712/0bdmSbbW17viRgbmb6/` (порт 26712, basepath /0bdmSbbW17viRgbmb6/)
- SSH-туннель к панели (альтернатива): `ssh -L 26712:localhost:26712 server` → `http://localhost:26712/0bdmSbbW17viRgbmb6/`
- Клиент на устройствах: **Hiddify** (Mac / Android), подключается по ссылке `vless://...`
- Python: /home/parser/venv/bin/python (Python 3.12)
- Старый сервер Beget: 84.54.30.209 (алиас `ssh server-old`, отключить после проверки)

## Структура файлов на сервере
```
/home/parser/
├── venv/                         # Python virtualenv
├── config/
│   └── alex/
│       ├── settings.py           # ✅ заполнен (VK MAX + iiko)
│       └── service_account.json  # ✅ загружен (aihotel-bot@aihotel-gubaha.iam.gserviceaccount.com)
├── scrapers/                     # account_manager, iiko, travelline, telegram, universal
├── bots/                         # vk_max_bot.py, telegram_status_bot.py, daily_report.py
├── logs/                         # логи запусков
└── data/                         # временные данные
```

## VK MAX бот (alex) — настроен ✅
- API: https://botapi.max.ru
- Авторизация: `Authorization: TOKEN` (без слова Bearer!)
- VK_MAX_USER_ID: 8173086 (Александр)
- Ежедневный отчёт: daily_report.py, cron 06:00 UTC = 09:00 МСК
- Данные из листа ЕжеДневно: Выручка(стр.3), Кухня(7), Бар(8), Чек(5), Гости(6), Завтраки(25)

## Google Sheets (alex) — настроен ✅
- Service account: aihotel-bot@aihotel-gubaha.iam.gserviceaccount.com
- Файл на сервере: /home/parser/config/alex/service_account.json
- Таблица iiko: 1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI

## Важные детали
- Сервер в Германии (u1host) — полный VPN-туннель, Claude/Telegram/все сайты работают
- VLESS+Reality маскирует трафик под обычный HTTPS — обходит DPI лучше WireGuard/Amnezia
- Hiddify (вкл) = весь интернет через DE, выкл = прямое подключение
- Панель 3X-UI НЕ открыта в интернет — только через SSH-туннель (безопасность)
- Аккаунт oleg = тот же Александр, резервный Claude-аккаунт. Смена: `claude logout` → `claude`
- Папка config/oleg на сервере удалена — не нужна
