# Инструкции для Claude — Проект "Сервер + VPN"

## Кто пользователь
- Александр, Россия, Mac M2, VS Code
- Новичок в Linux/SSH/DevOps
- Два аккаунта: alex (Александр) и oleg (Олег)

## Правила работы
- Всегда давать готовые команды для copy-paste — без сокращений
- Не объяснять теорию, если не спрашивают
- Сначала делать, потом объяснять по запросу
- Всегда указывать: эту команду на Маке или на сервере
- Перед началом сессии читать STATUS.md

## Сервер
- IP: 84.54.30.209
- ОС: Ubuntu 24.04.4, 2GB RAM
- SSH: `ssh server` (алиас в ~/.ssh/config, ключ ~/.ssh/id_ed25519)
- WireGuard: wg-quick@wg0, порт **443/UDP** (не 51820 — изменён для обхода РКН)
- VPN-подсеть: 10.66.66.1 (сервер), 10.66.66.2 (alex), 10.66.66.3 (oleg)
- Python: /home/parser/venv/bin/python (Python 3.12)

## Структура файлов на сервере
```
/home/parser/
├── venv/                         # Python virtualenv
├── config/
│   ├── alex/
│   │   ├── settings.py           # ✅ заполнен (VK MAX + iiko)
│   │   └── service_account.json  # ✅ загружен (aihotel-bot@aihotel-gubaha.iam.gserviceaccount.com)
│   └── oleg/
│       ├── settings.py           # ❌ не заполнен
│       └── service_account.json  # ❌ не загружен
├── parsers/                      # account_manager, iiko, travelline, telegram, universal
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
- Beget — российский хостинг. Claude через наш VPN НЕ работает
- Claude работает через Happ Plus VPN (Германия) — не трогать!
- WireGuard нужен только для SSH и управления сервером
- settings.py для oleg ещё не заполнен
