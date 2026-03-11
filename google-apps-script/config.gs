/**
 * КОНФИГУРАЦИЯ — ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ КУРОРТА ГУБАХА
 *
 * Заполните все поля перед запуском скриптов.
 * Этот файл храните в тайне — содержит API-ключи.
 */

const CONFIG = {

  // ── ОБЪЕКТ ────────────────────────────────────────────────
  RESORT_NAME: 'Курорт Губаха',
  REPORT_TIMEZONE: 'Asia/Yekaterinburg',

  // Ёмкость сегментов (для расчёта Occupancy и RevPAR)
  CAPACITY: {
    cottages:  { units: 33,  beds: 180 },
    alen:      { units: 14,  beds: 64  },
    daniel:    { units: 21,  beds: 102 },
    hostel:    { units: 35,  beds: 166 },   // Ален + Даниэль
    total_beds: 346,
  },

  // ── GOOGLE SHEETS ─────────────────────────────────────────
  // Оставьте пустым '' если скрипт запущен внутри нужной таблицы
  SPREADSHEET_ID: '1ptWfgoDDZ86Nc9Rzs-Wf0i5zBC3In6kYp-9NDthjlNM',

  // ── TRAVELLINE API ────────────────────────────────────────
  TRAVELLINE: {
    BASE_URL:   'https://api.travelline.ru/statistics/v1',
    API_KEY:    '',   // ← вставьте ваш ключ
    PROPERTY_ID: '',  // ← ID объекта в Travelline
  },

  // ── IIKO API ──────────────────────────────────────────────
  IIKO: {
    BASE_URL:   'https://iiko.biz/resto/api',  // для iiko.biz cloud
    LOGIN:      '',   // ← логин пользователя API
    PASSWORD:   '',   // ← пароль (SHA1-хэш)
    ORG_ID:     '',   // ← ID организации в IIKO
  },

  // ── CLAUDE API ────────────────────────────────────────────
  CLAUDE: {
    API_KEY:    '',   // ← ключ с console.anthropic.com
    MODEL:      'claude-opus-4-6',
    MAX_TOKENS: 2048,
  },

  // ── УВЕДОМЛЕНИЯ ───────────────────────────────────────────
  TELEGRAM: {
    BOT_TOKEN:  '',   // ← токен от @BotFather
    CHAT_ID:    '',   // ← ID чата или группы
  },
  EMAIL: {
    RECIPIENTS: [''],  // ← список email-адресов получателей
  },

  // ── РАСПИСАНИЕ ────────────────────────────────────────────
  // Отчёт за Пн–Вс, генерируется в воскресенье в 23:00 или понедельник в 06:00
  SCHEDULE: {
    DAY_OF_WEEK: 1,   // 1=Пн, 0=Вс (для Google Apps Script trigger)
    HOUR:        6,   // час запуска
  },

  // ── ПОРОГИ АНОМАЛИЙ (из документа структуры отчётов) ─────
  THRESHOLDS: {
    // Финансы — отель и ресторан
    revenue_daily:          { normal: 0.10, warn: 0.10, crit: 0.20 },  // ±10% норма
    adr:                    { normal: 0.10, warn: 0.10, crit: 0.20 },  // ±10%, >20% рост — предупреждение
    occupancy:              { normal: 0.10, warn: 0.10, crit: 0.20 },  // ±10%, падение >10% — сигнал
    los:                    { normal: 0.10, warn: 0.10, crit: 0.20 },  // ±10%
    repeat_guests:          { normal: 0.10, warn: 0.10, crit: 0.20 },  // ±10%
    avg_check_restaurant:   { normal: 0.10, warn: 0.10, crit: 0.20 },  // ±10%, рост >20% — предупреждение
    guests_restaurant:      { normal: 0.10, warn: 0.10, crit: 0.20 },  // ±10%
    menu_category:          { normal: 0.10, warn: 0.10, crit: 0.20 },  // ±10%
    banquet_revenue:        { normal: 0.10, warn: 0.10, crit: 0.20 },  // ±10%

    // Структурные сдвиги (в процентных пунктах)
    channel_share_pp:       { warn: 5  },   // изменение доли канала >5пп — сигнал
    category_share_pp:      { warn: 5  },   // изменение вклада категории >5пп
    weekday_weekend_pp:     { warn: 5  },   // будни/выходные >5пп
    revenue_vs_nights_pp:   { warn: 20 },   // люфт выручка/ночи >20%

    // Контроль процессов (отель)
    cancellations:          { normal: 0.05, warn: 0.05, crit: 0.10 },  // ±5%, >5пп/мес — сигнал
    returns_manual:         { normal: 0.05, warn: 0.05 },               // ±5%
    discount_bookings_pct:  { max: 0.20 },   // не более 20% от всех броней
    manual_discount_revenue:{ max: 0.01 },   // не более 1% от выручки в месяц
    promo_guests_pct:       { max: 0.20 },   // не более 20% гостей по акциям

    // Контроль процессов (ресторан)
    manual_inputs:          { normal: 0.05, warn: 0.05 },
    check_open_hours:       { warn: 4   },   // чек открыт >4 часов — подозрение
    deleted_positions_pct:  { crit: 0.01 },  // >1% от выручки позиций — критично
    discount_checks_pct:    { max: 0.20 },   // не более 20% чеков со скидкой
    banquet_no_upsell_pct:  { max: 0.10 },   // не более 10% банкетов без доп.продаж
    writeoffs:              { normal: 0.20, warn: 0.20, crit: 0.50 },  // ±20%, >50% — критично
    menu_sales_drop:        { warn: 0.20 },  // падение продаж блюда >20% — антирейтинг

    // Специфичные
    no_show:                'each',   // каждый случай — в отчёт
    zero_check:             'each',   // каждый нулевой чек — сигнал
    booking_no_prepay:      'each',   // каждое бронирование без предоплаты — в отчёт
    manual_discount:        'each',   // каждая ручная скидка — ФИО + сумма
  },
};
