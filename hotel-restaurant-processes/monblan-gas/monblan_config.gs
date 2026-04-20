/**
 * КОНФИГУРАЦИЯ — МОНБЛАН ЕЖЕНЕДЕЛЬНЫЙ ТРЕКИНГ
 *
 * Заполните все поля перед запуском скриптов.
 * Файл хранится в Apps Script редактора второй таблицы.
 *
 * Google Таблица: https://docs.google.com/spreadsheets/d/1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI/edit
 */

const MB_CONFIG = {

  // ── ОБЩЕЕ ──────────────────────────────────────────────────────
  CAFE_NAME:    'Монблан',
  TIMEZONE:     'Asia/Yekaterinburg',
  TABLES:       90,    // количество столов (используется в формулах оборачиваемости)
  SEATS:        90,    // посадочных мест

  // ── ЛИСТ ТРЕКИНГА ─────────────────────────────────────────────
  // GID листа в таблице — gid=2051236241 (из URL)
  // Если имя листа изменилось — укажите актуальное
  TRACKING_SHEET_GID:  2051236241,
  TRACKING_SHEET_NAME: 'Монблан',   // запасной поиск по имени

  // Первая неделя данных (ISO-неделя года)
  START_YEAR: 2024,
  START_WEEK: 48,

  // Сколько недель-столбцов подготовить (формулы + заголовки)
  // 104 = примерно 2 года вперёд
  WEEKS_TO_INIT: 104,

  // ── IIKO (iikoWeb) ────────────────────────────────────────────
  // API: POST /api/auth/login {login, password} → JWT-токен
  // OLAP: POST /api/olap/init → GET /api/olap/fetch-status → POST /api/olap/fetch/DATA
  IIKO: {
    WEB_URL:  'https://kafe-monblan.iikoweb.ru',
    STORE_ID: 82455,           // integer ID в iikoWeb
    LOGIN:    '',              // ← логин iikoWeb (вставьте в Apps Script редакторе)
    PASSWORD: '',              // ← пароль iikoWeb
  },

  // ── УВЕДОМЛЕНИЯ ───────────────────────────────────────────────
  TELEGRAM: {
    BOT_TOKEN: '',   // ← токен от @BotFather
    CHAT_ID:   '',   // ← ID чата/группы
  },

  // ── РАСПИСАНИЕ ────────────────────────────────────────────────
  // Запуск каждый понедельник в 06:00 (сбор данных за прошедший Пн–Вс)
  SCHEDULE: {
    DAY_OF_WEEK: 1,  // 1 = понедельник
    HOUR:        6,
  },
};
