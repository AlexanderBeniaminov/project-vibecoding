# CLAUDE.md — Менеджер двух ботов

Бот управляет правилами Напоминатора (assistant) и Помощника (helper). Живёт на VPS `/home/parser/bots/manager/`.

---

## Что умеет

- NLP-команды: «Напоминатор, сделай ответы короче» → создаёт `system_addon`-правило
- «Переделай» + reply → переформатирует ответ через LLM и предлагает сохранить как правило
- `/rules`, `/rule <id>`, `/delete_rule <id>`, `/toggle_rule <id>`, `/history <id>`
- Голосовые команды (Groq Whisper)

## Стек

| Компонент | Технология |
|-----------|-----------|
| Фреймворк | aiogram 3 (async, long-polling) |
| LLM | DeepSeek V4 Pro через RouterAI |
| Голос | Groq Whisper (`whisper-large-v3-turbo`) |
| БД правил | SQLite через `shared/rules_db.py` — `/home/parser/bots/shared/rules.db` |
| Сервис | `telegram-manager.service` |

## Файлы на сервере

```
/home/parser/bots/manager/
├── manager_bot.py
├── config.py          # секреты (не в git)
└── shared/ → симлинк или копия /home/parser/bots/shared/
```

## Деплой

```bash
bash telegram-manager/deploy.sh
```

Скрипт: rsync → рестарт → ждёт `active` до 10 сек → проверяет логи на `error/traceback`.  
При сбое выводит `journalctl -n 20` и завершается с `exit 1`.

## Критичные инварианты (не ломать)

### Обработчик сообщений
- Ловит ВСЕ типы: `F.text | F.voice | F.photo | F.document | F.video | F.sticker | F.audio`
- Для не-текстовых читает `message.caption` (фото со скриншотом + подпись)
- `send_chat_action("typing")` — ПЕРВЫЙ вызов после `_auth()`, до любой обработки

### Shared rules DB
- `/home/parser/bots/shared/rules.db` — единая база правил для обоих ботов
- `rule_engine.invalidate_cache()` после каждого изменения правил

## Правила

- ALLOWED_USER_IDS = {994743403} — только Александр
- Ответы: краткие, без лишних вопросов
