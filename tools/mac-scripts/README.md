# Mac Scripts — ~/bin/

Скрипты для OpenClaw (@pomoshniknamac_bot на Mac).  
Рабочие файлы живут в `~/bin/` — эта папка бэкап для git.

## Установка на новом Mac

```bash
cp tools/mac-scripts/*.py ~/bin/
chmod +x ~/bin/*.py
pip3 install google-auth google-auth-oauthlib google-api-python-client
```

## Конфиги (не в git, хранить отдельно)

| Файл | Описание |
|------|----------|
| `~/.config/mailru.json` | Пароль ab@entens.ru (IMAP/SMTP) |
| `~/.config/google/personal_service_account.json` | SA для Губаха Sheets |
| `~/.config/google/monblan_service_account.json` | SA для Монблан Sheets |
| `~/.config/google/aihotel_service_account.json` | SA для Губаха Finance |

## Скрипты

| Файл | Функция |
|------|---------|
| `gubaha_task.py` | Голос → задача в Google Sheets «Задачи недели» |
| `crm.py` | CRM контактов → SQLite `~/.config/crm.db` |
| `sheets_query.py` | Голос → данные из таблиц (Монблан, Губаха) |
| `gmail.py` | Email ab@entens.ru (Mail.ru IMAP/SMTP) |
| `delegate_to_planner.py` | Делегирование задачи в Планировщика (@assistent_beniaminova_bot) |
