# Проекты Александра Бениаминова

### `aihotel/` — AI-система управления ВК Губаха
Два Python-агента (GitHub Actions, каждый понедельник):
- **Агент 1** — читает данные из Google Sheets "2026 старый" → анализирует → пишет дайджест
- **Агент 2** — дайджест + KPI-прогресс → DeepSeek V4 Pro (RouterAI) → задачи в "Задачи недели"
- Команда ВК Губаха (роли критичны для постановки задач):
  - **Виктор** — Руководитель проекта (операционное управление, координация). Удалённо.
  - **Евгения** — Бронирование и групповые продажи (TravelLine, Bitrix24, OTA). Удалённо.
  - **Надежда** — Маркетинг (акции, СММ, лидогенерация, пакеты ДР, группы). Удалённо.
  - **Управляющий** — Контроль объекта, дисциплина, гостевой сервис. На объекте.
  - **Тех.директор** — Главный инженер + функции менеджера НФ. На объекте.
- KPI апр–ноябрь 2026: загрузка 12%/19.8%, маржа 8%, выручка 15.4М, ДР 125, группы 6
- → подробнее: `aihotel/CLAUDE.md`

### `restaurant-monblan/` — Монблан трекинг
iiko → Google Sheets. Три потока: ежедневный / еженедельный (GAS) / ежемесячный (Python).
- Стек: Python, iiko OLAP API, Google Sheets, GAS, GitHub Actions
- → подробнее: `restaurant-monblan/CLAUDE.md`

### `telegram-assistant/` — Персональный AI-ассистент
Telegram-бот на сервере. Голос, напоминания, заметки, Google Calendar, веб-поиск.
- Стек: aiogram 3, DeepSeek V4 Pro (RouterAI), Groq Whisper, APScheduler, SQLite
- Деплой: `bash telegram-assistant/deploy.sh`
- → подробнее: `telegram-assistant/CLAUDE.md`

### `infrastructure/` — Сервер + VPN
VPS u1host Германия, Ubuntu 24.04. VLESS+XTLS-Reality (3X-UI). Python venv на /home/parser/venv.
- → подробнее: `infrastructure/CLAUDE.md`

### `entens-group_website/` — Лендинг EntenS Group
Одностраничный сайт, весь код в `index.html`.
- → подробнее: `entens-group_website/CLAUDE.md`

### `otchety/` — Отчёты курорта Губаха
Еженедельные отчёты для курорта. Отдельный проект, не пересекается с Монблан.
- → подробнее: `otchety/CLAUDE.md`

### `content-plan/` — Контент-план
Посты, аудитория, tone-of-voice для соцсетей Александра.

---

## Инфраструктура

| Ресурс | Значение |
|--------|----------|
| VPS | 185.184.122.158, SSH алиас `ssh server` |
| Python venv | `/home/parser/venv` (Python 3.12) |
| Боты на сервере | `/home/parser/bots/` |
| GCP личный | alex-personal-496919 |
| GCP aihotel | aihotel-gubaha |
| RouterAI | `https://routerai.ru/api/v1`, модель `deepseek/deepseek-v4-pro` |
| GitHub репо | AlexanderBeniaminov/project-vibecoding |

## Git

```bash
# Remote уже содержит токен — push работает напрямую
git add <files> && git commit -m "..." && git push
```

---

## Правила работы

- Делай автономно: коммит, пуш, деплой, GitHub Secrets — без запроса
- Спрашивай только при: удалении данных, внешних API с последствиями, `git push --force`
- Комментарии в коде — на русском
- Ответы — короткие и конкретные
- Если "да" / "давай" / "го" → запускай команду немедленно, без лишних вопросов
- Прежде чем начать задачу — одним предложением скажи, как будешь проверять результат

---

## После каждой задачи

Одним предложением: что ещё можно автоматизировать или оптимизировать в этом месте кода.
Не обязательно реализовывать — просто замечай возможности.

---

## gstack

Use `/browse` for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

---

## Общая инфраструктура


