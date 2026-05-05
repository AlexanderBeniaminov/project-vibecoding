# Проект: Сервер + VPN — Статус задач

## Сервер
- ВПС: Beget, IP 84.54.30.209, Ubuntu 24.04, 2GB RAM
- Пользователь на сервере: parser (для парсеров), root (для настройки)
- VPN-сеть: 10.66.66.0/24 (сервер 10.66.66.1, alex 10.66.66.2, oleg 10.66.66.3)

---

## БЛОК 1 — Сервер и VPN

| Задача | Статус | Примечание |
|--------|--------|------------|
| VPS создан на Beget | ✅ Готово | 84.54.30.209 |
| setup.sh выполнен | ✅ Готово | Всё зелёное |
| WireGuard установлен на сервере | ✅ Готово | wg-quick@wg0 |
| Профили alex.conf и oleg.conf созданы | ✅ Готово | QR-коды скачаны |
| WireGuard установлен на Mac (alex) | ✅ Готово | Импортирован alex.conf |
| WireGuard подключается (зелёный) | ✅ Готово | Рукопожатие есть |
| Split-tunnel: только трафик к серверу | ✅ Готово | AllowedIPs = 10.66.66.0/24 |
| UFW FORWARD policy исправлен | ✅ Готово | DEFAULT_FORWARD_POLICY=ACCEPT |
| Порт изменён с 51820 на 443/UDP | ✅ Готово | Обходит блокировку РКН |
| WireGuard на Mac (alex_split) | ✅ Готово | Подключён, рукопожатие работает |
| WireGuard на Mac (oleg_split) | ✅ Готово | Импортирован (для ноутбука Олега) |
| Оба VPN одновременно (WireGuard + Happ Plus) | ✅ Готово | Не конфликтуют |
| SSH-конфиг на Mac (~/.ssh/config) | ✅ Готово | Команда: ssh server |
| WireGuard на Android Huawei Nova 11 | ❌ Не сделано | QR-коды готовы |
| Watchdog (автоперезапуск VPN) | ✅ Готово | Настроен в cron |

---

## БЛОК 2 — Python и парсеры

| Задача | Статус | Примечание |
|--------|--------|------------|
| Python venv создан | ✅ Готово | /home/parser/venv (создан 2026-05-05) |
| Библиотеки установлены | ✅ Готово | requests, loguru, gspread, google-auth, python-telegram-bot |
| account_manager.py | ✅ Готово | + поддержка VK MAX (notify_vkmax) |
| travelline_parser.py | ✅ Готово | На сервере |
| iiko_parser.py | ✅ Готово | На сервере |
| telegram_monitor.py | ✅ Готово | На сервере |
| universal_parser.py | ✅ Готово | На сервере |
| settings.py для alex | ✅ Заполнено | VK MAX + iiko таблица |
| settings.py для oleg | ❌ Не заполнено | Нужны данные Олега |
| service_account.json для alex | ✅ Загружен | aihotel-bot@aihotel-gubaha.iam.gserviceaccount.com |
| service_account.json для oleg | ❌ Не загружен | |
| Cron: ежедневный отчёт (alex) | ✅ Готово | 06:00 UTC (09:00 МСК) через daily_report.py |

---

## БЛОК 3 — Боты

| Задача | Статус | Примечание |
|--------|--------|------------|
| telegram_status_bot.py | ✅ Готово | Код на сервере |
| vk_max_bot.py | ✅ Готово | Переписан под VK MAX Bot API (max.ru) |
| daily_report.py | ✅ Готово | Ежедневный отчёт → VK MAX |
| VK MAX бот (alex) | ✅ Готово | "Отчёты Монблан", отправка работает |
| VK MAX бот запущен как сервис | ❌ Не сделано | Нужен systemd unit |
| Telegram бот alex | ❌ Не сделано | Нужен TOKEN из BotFather |
| Telegram бот oleg | ❌ Не сделано | Нужен TOKEN из BotFather |

---

## БЛОК 4 — Google Sheets (alex)

| Задача | Статус | Примечание |
|--------|--------|------------|
| Service Account | ✅ Готово | aihotel-bot@aihotel-gubaha.iam.gserviceaccount.com |
| Таблица iiko (alex) | ✅ Подключена | 1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI |
| Лист ЕжеДневно | ✅ Работает | Выручка/Кухня/Бар/Чек/Гости/Завтраки |
| Ежедневный отчёт VK MAX | ✅ Протестирован | Успешно отправлен 2026-05-05 |
| Таблицы для oleg | ❌ Не настроено | |

---

## БЛОК 5 — VS Code Remote SSH

| Задача | Статус | Примечание |
|--------|--------|------------|
| Расширение Remote-SSH установлено | ❌ Не сделано | |
| SSH-конфиг настроен (alex + oleg) | ❌ Не сделано | |
| Подключение к серверу из VS Code | ❌ Не сделано | |

---

## БЛОК 6 — Финальная проверка

| Задача | Статус | Примечание |
|--------|--------|------------|
| check_all.sh прошёл без ошибок | ❌ Не проверено | |
| claude.ai через VPN (alex) | ❌ Не проверено | |
| claude.ai через VPN (oleg) | ❌ Не проверено | |
| Российские сайты без VPN | ❌ Не проверено | split-tunnel |
| Парсер → Google Sheets (alex) | ❌ Не проверено | |
| Парсер → Google Sheets (oleg) | ❌ Не проверено | |
| Telegram уведомление (alex) | ❌ Не проверено | |
| Telegram уведомление (oleg) | ❌ Не проверено | |

---

## Текущий приоритет (продолжить следующий раз)

1. 🤖 Запустить VK MAX бота как systemd-сервис (автозапуск)
2. ⚙️ Настроить settings.py и service_account.json для oleg
3. 🤖 Создать Telegram боты через BotFather (alex + oleg)
4. 📱 WireGuard на Android Huawei Nova 11
5. 🖥️ VS Code Remote-SSH
6. ✅ Финальная проверка check_all.sh
