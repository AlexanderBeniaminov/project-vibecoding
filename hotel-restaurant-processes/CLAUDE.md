# CLAUDE.md — hotel-restaurant-processes
> Рабочий контекст для Claude. Читать перед любой работой с этой папкой.
> Актуальный статус этапов — в [PLAN.md](PLAN.md).

---

## Суть задачи

Ресторан «Монблан» (курорт Губаха, Пермский край) работает на **iiko**. Администратор тратит 28–41 мин/день + 60–90 мин/нед на ручной перенос данных из iiko в Excel.

**Решение:** Python-скрипт по расписанию забирает данные из iikoWeb OLAP → пишет в Google Sheets → MAX-бот отправляет отчёт собственнику и собирает ручные данные у администратора.

**Стек:** Python 3.10+ · GitHub Actions · Google Sheets API v4 · MAX мессенджер · iikoWeb OLAP API
**Стоимость:** 0 руб./месяц
**Важно:** Этот проект — Python. Соседний `otchety/` — Google Apps Script. Не путать.

---

## Расписание запусков

| Триггер | Cron (UTC) | Местное время (UTC+5) | Что делает |
|---|---|---|---|
| Ежедневный | `30 18 * * *` | 23:30 каждый день | Забирает данные за день, пишет в Лист 1, запрашивает ручной ввод у администратора, отправляет отчёт собственнику |
| Еженедельный | `0 2 * * 1` | 07:00 понедельник | Агрегирует данные Листа 1 за прошедшую неделю (пн–вс), записывает сводку в Лист 2 |
| Резервный | `30 1 * * *` | 06:30 следующий день | Повтор если основной упал (смена не была закрыта в 23:30) |

---

## iiko API — iikoWeb OLAP (ЕДИНСТВЕННЫЙ РАБОЧИЙ СПОСОБ)

> **❌ НЕ ИСПОЛЬЗОВАТЬ** iiko Transport API (`api-ru.iiko.services`):
> - `POST /api/1/order/by_table` — возвращает только заказы, созданные через API (с `sourceKey`).
>   POS-заказы с кассы iikoFront **никогда не возвращаются** → всегда 0 руб. выручки.
> - Проверено на реальных данных в апреле 2026 — все даты дают пустые заказы.
> - DNS `api-ru.iiko.services` может быть недоступен с mac-машины (timeout), но доступен с GitHub Actions.
>   Это не имеет значения — Transport API всё равно не даёт POS-данные.

### Рабочий метод: iikoWeb OLAP

**Сервер:** `https://kafe-monblan.iikoweb.ru`
**Логин:** `buh` / `Vjy,kfy2024` (роль ADM, storeId=82455)
**Токен TTL:** 1200 секунд (20 минут)

#### Авторизация
```
POST /api/auth/login
{"login": "buh", "password": "Vjy,kfy2024"}
→ {"token": "JWT...", "storeId": 82455, "store": "Кафе Монблан"}
```

#### OLAP запрос (3 шага)

**Шаг 1 — Инициализировать запрос:**
```
POST /api/olap/init
{
  "storeIds": [82455],
  "olapType": "SALES",          ← НЕ "reportType"
  "groupFields": ["OpenDate.Typed"],   ← НЕ "groupByRowFields"
  "dataFields": ["DishDiscountSumInt", "UniqOrderId.OrdersCount", "GuestNum"],  ← НЕ "aggregateFields"
  "filters": [
    {
      "field": "OpenDate.Typed",
      "filterType": "date_range",
      "dateFrom": "2026-04-05",    ← формат YYYY-MM-DD (без времени!)
      "dateTo": "2026-04-05",
      "valueMin": null, "valueMax": null,
      "valueList": [],
      "includeLeft": true, "includeRight": true, "inclusiveList": true
    },
    {
      "field": "OrderDeleted",
      "filterType": "value_list",
      "dateFrom": null, "dateTo": null,
      "valueMin": null, "valueMax": null,
      "valueList": ["NOT_DELETED"],
      "includeLeft": true, "includeRight": false, "inclusiveList": true
    }
  ]
}
→ {"error": false, "data": "requestId_hash..."}
```

**Шаг 2 — Проверить статус:**
```
GET /api/olap/fetch-status/{requestId}
→ {"data": "SUCCESS"}   ← статус SUCCESS (не READY!)
   или "PROCESSING" (ждать 3 сек и повторить)
   или "ERROR" (неверные поля или нет лицензии OLAP)
```

**Шаг 3 — Получить данные:**
```
POST /api/olap/fetch/{requestId}/DATA
{"rowOffset": 0, "rowCount": 10000}
→ {
    "result": {
      "rawData": [
        {"DishDiscountSumInt": 34900, "GuestNum": 25, "OpenDate.Typed": "2026-04-05", "UniqOrderId.OrdersCount": 20}
      ],
      "totalRevenueInPeriod": 0,   ← поле summary не всегда заполнено, считать из rawData!
      ...
    }
  }
```

#### Ключевые поля OLAP

| Поле | Тип | Описание |
|---|---|---|
| `DishDiscountSumInt` | деньги | Выручка (со скидкой) |
| `DishSumInt` | деньги | Выручка без скидки |
| `UniqOrderId.OrdersCount` | кол-во | Число чеков |
| `GuestNum` | кол-во | Число гостей |
| `DishDiscountSumInt.average` | деньги | Средний чек |
| `DishAmountInt` | кол-во | Количество позиций |
| `DishName` | строка | Название блюда |
| `DishCategory.Accounting` | строка | Бухгалтерская категория |
| `PayTypes.Combo` | строка | Тип оплаты |
| `OpenDate.Typed` | дата | Дата открытия заказа |

#### OLAP типы (olapType)

| Значение | Что возвращает |
|---|---|
| `SALES` | Продажи (чеки, блюда, гости, типы оплаты) |
| `TRANSACTIONS` | Складские операции (списания) |

#### Важные ограничения OLAP

- `storeIds` — должен быть массив ровно с **одним** элементом: `[82455]`
- Статус `SUCCESS` (не `READY`) — иначе ждать бесконечно
- Данные считать из `result.rawData`, не из `totalRevenueInPeriod`
- Если `rawData` пуст — за эту дату нет продаж (ресторан не работал)
- Фильтр по дате: `filterType: "date_range"`, даты в формате `"YYYY-MM-DD"` (без времени)
- Категории Кухня/Бар: поле `DishCategory.Accounting` — нужно уточнить реальные названия категорий в iikoWeb

#### Проверенные реальные данные

```
2026-04-05: выручка 34 900 руб., 20 чеков, 25 гостей
            оплата: Банковские карты 20 320 руб., СБЕР банк 14 580 руб.
            топ блюд: глин 400 НОВ 6 210 руб. (9 шт.)
2024-01-01: выручка 213 305 руб., 365 чеков, 445 гостей
```

#### Presets OLAP (готовые запросы, сохранённые в iikoWeb)

```
GET /api/analytics/olap/presets/list?show-deleted=false
→ 8 presets: Почасовой отчет, Продажи по товарам, Отчет по типам оплаты, и др.
```
Используй эти presets как образец формата запроса.

#### Другие рабочие эндпоинты iikoWeb

| Эндпоинт | Метод | Что возвращает |
|---|---|---|
| `/api/auth/login` | POST | JWT токен |
| `/api/kpi-metric/stores` | GET | Список магазинов (storeId, uocOrganizationId) |
| `/api/stores/list` | GET | Полная инфо о магазинах (адрес, часовой пояс) |
| `/api/kpi/directory/bystores` | POST | Справочник из 407 KPI-метрик |
| `/api/analytics/olap/presets/list` | GET | Сохранённые OLAP-отчёты |
| `/api/analytics/olap/enums` | GET | Справочники enum-значений |
| `/api/olap/fetch/{id}/xls` | GET | Экспорт в Excel |

#### Что недоступно

| Данные | Причина |
|---|---|
| Временны́е срезы (утро/день/вечер) | OLAP не группирует по часам заказа по умолчанию; нужен `groupFields: ["HourClose"]` |
| Списания со склада | Нужен отдельный OLAP запрос с `olapType: "TRANSACTIONS"` |
| Отмены | Нужен отдельный OLAP запрос с фильтром `OrderDeleted: ["DELETED"]` |

---

## Структура Google Sheets

**ID таблицы:** `1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI`
**Сервисный аккаунт:** `montblanc-report@composite-wind-449411-d8.iam.gserviceaccount.com`

**Общий принцип:** колонка A — названия параметров, данные идут вправо по колонкам.

### Лист «Ежедневно»
- **Строка 1** — даты (`2026-03-29`, `2026-03-30`, ...)
- **Строки 2..N** — значения параметров (порядок = `METRICS_DAILY` в `sheets_writer.py`)
- Числовой формат: `# ##0` (пробел как разделитель тысяч)

| Параметр | Источник |
|---|---|
| Выручка итого, Нал, СБП, Карта, По счёту | iikoWeb OLAP auto |
| Кол-во чеков, Средний чек, Гости | iikoWeb OLAP auto |
| Кухня, Бар | iikoWeb OLAP auto (нужно уточнить категории) |
| Отмены (руб) | iikoWeb OLAP (фильтр DELETED) |
| Списания (руб) | iikoWeb OLAP (TRANSACTIONS) |
| Инкассация, Расход из кассы, Остаток нал | MAX ручной ввод |
| Повара/Официанты/Бармены/Посудомойщицы — кол-во и з/п | MAX ручной ввод |
| Персонал итого, З/п итого | расчёт |
| Завтраки (гостей) | MAX ручной ввод |
| Статус | авто: `✅ полный` / `⚠️ авто (без кассы)` |

### Лист «Еженедельно»
- **Строка 1** — номер недели (`Неделя 13`, `Неделя 14`, ...)
- **Строка 2** — период пн–вс (`23.03.2026 – 29.03.2026`)
- **Строки 3..N** — значения параметров (порядок = `METRICS_WEEKLY` в `sheets_writer.py`)

---

## MAX мессенджер (вместо Telegram)

**Мессенджер:** MAX (max.ru, formerly TamTam)
**Bot API:** `https://botapi.max.ru`
**Авторизация:** `?access_token=MAX_BOT_TOKEN` (query param)

### Поток А — Ежедневный (23:30)
```
1. iikoWeb OLAP → данные за день → Лист 1 (авто)
2. → Администратору: запрос ручных данных (касса, персонал, завтраки)
3. Ожидание ответа 30 мин → парсинг → Лист 1 (ручные)
4. → Собственнику: итоговый отчёт
```

### Формат запроса администратору
```
Инкассация: 70000
Расход: 3500
Остаток: 26500
Завтраки: 12
Повара: 3/9000
Официанты: 4/12000
Бармены: 1/3500
Посудомойщицы: 2/5000
```

### Формат ежедневного отчёта собственнику
```
📊 Монблан — {дата}

💰 Выручка: {итого} руб.
   Нал: {нал} | СБП: {сбп} | Карта: {карта}
🍽 Кухня: {кухня} | 🍹 Бар: {бар}
🧾 Чеков: {чеки} | Ср. чек: {ср_чек} руб. | Гостей: {гости}

👥 Персонал: {кол} чел. | З/п: {зп} руб.
🏦 Инкассация: {инкасс} | Остаток: {остаток} руб.

📎 Таблица → {ссылка}
```

---

## Переменные окружения (GitHub Actions Secrets)

```
# iikoWeb OLAP (основной источник данных) ✅ есть
IIKO_WEB_LOGIN    = buh
IIKO_WEB_PASSWORD = Vjy,kfy2024
IIKO_STORE_ID     = 82455

# iiko Transport API (не используется, оставлено для справки)
IIKO_API_LOGIN    = 42c9095b39264541b93ba7b0b21feb6e
IIKO_ORG_ID       = 6551e510-21d3-4ae1-8034-5eb229987543

# Google Sheets ✅ добавлены
GOOGLE_SHEETS_ID             = 1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI
GOOGLE_SERVICE_ACCOUNT_JSON  = {...json...}

# MAX мессенджер ❓ ждём от клиента
MAX_BOT_TOKEN       = ...
MAX_OWNER_USER_ID   = ...
MAX_ADMIN_USER_ID   = ...
MAX_DEV_USER_ID     = ...
```

---

## Тип iiko-системы

**iiko Cloud** — подтверждено.
- Клиентский URL: `kafe-monblan.iikoweb.ru` (iikoWeb 9.6.6)
- Терминалы: iikoFront 9.2.7014.0 (POS-кассы в ресторане)
- storeId в iikoWeb: `82455`
- uocOrganizationId (Transport API): `6551e510-21d3-4ae1-8034-5eb229987543`
- Часовой пояс: UTC+5 (Asia/Yekaterinburg)

---

## Константы

| Параметр | Значение | Статус |
|---|---|---|
| Посадочных мест (текущее) | 90 | ✅ |
| Кол-во столов (текущее) | 15 | ✅ |
| Посадочных мест (до 15.12.2025) | 58 | ✅ |
| Кол-во столов (до 15.12.2025) | 14 | ✅ |
| Дата изменения зала | 15 декабря 2025 | ✅ |
| Часовой пояс | UTC+5 | ✅ |
| iikoWeb storeId | 82455 | ✅ |
| iikoWeb логин | buh / Vjy,kfy2024 | ✅ |
| Категории Кухня/Бар | ❓ нужно уточнить в `DishCategory.Accounting` | ❓ |
| MAX токены | ❓ ждём от клиента | ❓ |

---

## Структура кода

```
hotel-restaurant-processes/
  scripts/
    main.py           — точка входа: daily() / weekly(); логирование; MAX-отчёты
    iiko_client.py    — iikoWeb OLAP: IikoWebSession + _olap_query() + collect_daily_data()
    sheets_writer.py  — запись в Sheets (параметры в строках, даты в колонках)
    max_bot.py        — MAX мессенджер: отправка + polling ответа администратора
    config.py         — константы (без секретов); IIKO_WEB_* + get_capacity()
    utils.py          — UTC+5, retry(), fmt_money(), parse_admin_reply()
    test_iiko.py      — тест iikoWeb OLAP (ищет дату с данными за 30 дней)
    test_sheets.py    — тест Google Sheets
  .github/
    workflows/
      daily_report.yml   — cron: '30 18 * * *' UTC + резервный '30 1 * * *' + workflow_dispatch
      weekly_report.yml  — cron: '0 2 * * 1' UTC + workflow_dispatch
  logs/
  requirements.txt
```

---

## Открытые вопросы

| # | Вопрос | Статус |
|---|---|---|
| 1 | Реальные названия категорий `DishCategory.Accounting` для Кухня/Бар | ❓ Нужно проверить в iikoWeb |
| 2 | MAX мессенджер: токен бота + user_id (3 шт.) | ❓ Ждём от клиента |
| 3 | Мероприятия в iiko: тег или тип заказа? | ❓ Не уточнено |
| 4 | Ресторан не работал 6–12 апреля 2026 — почему? | ℹ️ Данных нет, это нормально |

---

## Точки отказа и решения

| Проблема | Решение |
|---|---|
| Токен iikoWeb истёк (401) | `IikoWebSession._login()` вызывается автоматически через `_ensure_token()` |
| OLAP статус ERROR | Неверные имена полей или нет лицензии OLAP у пользователя |
| OLAP пустые данные | За эту дату нет продаж — это нормально |
| storeIds != 1 элемент | Ошибка "Restaurant must be array with length = 1" — всегда передавать `[82455]` |
| Смена не закрыта в 23:30 | Резервный запуск в 06:30, данные за вчера |
| Администратор не ответил | Ожидание 30 мин, затем `⚠️ не заполнено` в Sheets |
| Google Sheets: новая дата → новая колонка | `_find_or_create_date_column()` в sheets_writer.py |
| GitHub Actions упал | Уведомление MAX разработчику + ссылка на run |

---

## Правила при написании кода

- Python 3.10+, зависимости в `requirements.txt`
- Ключи только через env vars, никогда в коде
- Все даты UTC+5 при запросах в iikoWeb; UTC в GitHub Actions cron
- Retry обязателен для всех внешних запросов
- При любой ошибке API — продолжать отчёт, пометить поле `⚠️ нет данных`
- Комментарии на русском
- Логировать каждый внешний запрос и его результат

---

## Связь с другими папками

| Папка | Отношение |
|---|---|
| `otchety/` | Параллельный проект курорта (отель + ресторан), Google Apps Script. Не конфликтуют. |
| `google-apps-script/` | Скрипты для `otchety/`. Не трогать. |
