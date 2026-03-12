/**
 * СОЗДАНИЕ ШАБЛОНА ЕЖЕНЕДЕЛЬНОГО ОТЧЁТА — КУРОРТ ГУБАХА
 *
 * Инструкция:
 *   1. Откройте Google Таблицу (или создайте новую)
 *   2. Меню → Расширения → Apps Script
 *   3. Вставьте содержимое этого файла (и config.gs) в редактор
 *   4. Нажмите "Сохранить" (Ctrl+S)
 *   5. Выберите функцию createReportTemplate и нажмите ▶ Выполнить
 *   6. Разрешите доступ при появлении запроса
 *
 * После запуска будут созданы 7 листов с готовой структурой.
 * Запускать ОДИН РАЗ — при повторном запуске листы пересоздаются.
 */

// ═══════════════════════════════════════════════════════════════
// ПАЛИТРА ЦВЕТОВ
// ═══════════════════════════════════════════════════════════════
const C = {
  hotelDark:  '#1a3a5c',   // Тёмно-синий — заголовки отеля
  hotelMid:   '#2d6a9f',   // Средний синий — подзаголовки
  hotelLight: '#d0e4f7',   // Светло-голубой — строки данных
  restDark:   '#7b3f00',   // Тёмно-коричневый — заголовки ресторана
  restMid:    '#c05c0a',   // Оранжевый — подзаголовки
  restLight:  '#fce4d6',   // Персиковый — строки данных
  opsDark:    '#2d6a2d',   // Зелёный — операционный журнал
  opsLight:   '#e2f0d9',   // Светло-зелёный
  dashDark:   '#4a1060',   // Фиолетовый — дашборд
  dashLight:  '#ead6f0',   // Светло-фиолетовый
  aiDark:     '#1a4a3a',   // Тёмно-зелёный — ИИ-анализ
  aiLight:    '#d0ead8',   // Светло-зелёный
  rawDark:    '#555555',   // Серый — сырые данные
  rawLight:   '#f0f0f0',

  white:      '#ffffff',
  rowEven:    '#f8f9fa',
  textDark:   '#1a1a1a',
  textMid:    '#444444',

  // Светофор
  green:      '#c6efce',
  yellow:     '#ffeb9c',
  red:        '#ffc7ce',
  greenText:  '#276221',
  yellowText: '#7d6608',
  redText:    '#9c0006',
};

// ═══════════════════════════════════════════════════════════════
// ГЛАВНАЯ ФУНКЦИЯ
// ═══════════════════════════════════════════════════════════════
function createReportTemplate() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  ss.setSpreadsheetTimeZone(CONFIG.REPORT_TIMEZONE);

  SpreadsheetApp.getActiveSpreadsheet().toast('Создаём листы...', 'Губаха Отчёт', 30);

  buildSheet1_Hotel(ss);
  buildSheet2_Comparison(ss);
  buildSheet3_Restaurant(ss);
  buildSheet4_Operations(ss);
  buildSheet5_Dashboard(ss);
  buildSheet6_AI(ss);
  buildSheet7_Raw(ss);

  cleanupDefaultSheets(ss);

  // Открываем дашборд по умолчанию
  ss.setActiveSheet(ss.getSheetByName('05 | Дашборд'));

  SpreadsheetApp.getUi().alert(
    '✅ Шаблон создан!\n\n' +
    'Листы:\n' +
    '  01 | Отель — Данные недели\n' +
    '  02 | Отель — YoY / WoW\n' +
    '  03 | Ресторан Монблан\n' +
    '  04 | Операционный журнал\n' +
    '  05 | Дашборд\n' +
    '  06 | ИИ-анализ\n' +
    '  07 | Сырые данные\n\n' +
    'Следующий шаг: заполните config.gs ключами API.'
  );
}

// ═══════════════════════════════════════════════════════════════
// ЛИСТ 1 — ОТЕЛЬ: ДАННЫЕ ТЕКУЩЕЙ НЕДЕЛИ
// ═══════════════════════════════════════════════════════════════
function buildSheet1_Hotel(ss) {
  const sh = getOrCreateSheet(ss, '01 | Отель — Данные недели');
  sh.clear();
  sh.setTabColor(C.hotelDark);

  // Ширина колонок
  sh.setColumnWidth(1, 280);  // Показатель
  sh.setColumnWidth(2, 140);  // Коттеджи
  sh.setColumnWidth(3, 140);  // Ален
  sh.setColumnWidth(4, 140);  // Даниэль
  sh.setColumnWidth(5, 140);  // Итого
  sh.setColumnWidth(6, 200);  // Примечание / порог

  // ── Заголовок таблицы ──
  setCell(sh, 1, 1, '🏨 ОТЕЛЬ — ДАННЫЕ НЕДЕЛИ', C.hotelDark, C.white, 13, true, 6);
  setCell(sh, 2, 1, 'Период:', C.hotelMid, C.white, 10, true);
  setCell(sh, 2, 2, '', C.hotelLight, C.textDark, 10, false);  // дата заполняется скриптом
  setCell(sh, 2, 3, 'Заполнено:', C.hotelMid, C.white, 10, true);
  setCell(sh, 2, 4, '', C.hotelLight, C.textDark, 10, false);
  mergeRange(sh, 1, 1, 1, 6);

  // ── Заголовки сегментов ──
  const segHeaders = ['Показатель', 'Коттеджи\n(33 ед.)', 'Хостел Ален\n(64 кр.м.)', 'Хостел Даниэль\n(102 кр.м.)', 'ИТОГО', 'Порог / Примечание'];
  writeHeaderRow(sh, 4, segHeaders, C.hotelDark, C.white, 10);
  sh.setRowHeight(4, 40);

  // ── БЛОК 1: Финансы ──
  writeSectionHeader(sh, 5, '💰 ФИНАНСЫ', C.hotelMid, C.white, 6);

  const finRows = [
    ['Выручка за неделю, ₽',              '', '', '', '', ''],
    ['Средняя стоимость суток (ADR), ₽',  '', '', '', '', 'Люфт ±10%. Рост >20% — предупреждение'],
    ['RevPAR (Доход на номер), ₽',        '', '', '', '', 'Выручка / доступные номеро-ночи'],
    ['Загрузка (Occupancy), %',           '', '', '', '', 'Люфт ±10%. Падение >10% — сигнал'],
    ['Кол-во гостей (ночёвки)',           '', '', '', '', ''],
    ['Выручка от доп. услуг, ₽',         '', '', '', '', 'Трансфер, аренда, беседки. Люфт ±10%'],
    ['Выручка от завтраков, ₽',          '', '', '', '', ''],
    ['Кол-во завтраков',                  '', '', '', '', ''],
  ];
  writeDataBlock(sh, 6, finRows);

  // ── БЛОК 2: Бронирования ──
  writeSectionHeader(sh, 15, '📋 БРОНИРОВАНИЯ', C.hotelMid, C.white, 6);

  const bookRows = [
    ['Кол-во заездов за неделю',                    '', '', '', '', ''],
    ['Средняя длина пребывания (LOS), ночей',        '', '', '', '', 'Люфт ±10%'],
    ['Отмены — кол-во',                              '', '', '', '', 'Динамика ±5%. >5пп за месяц — сигнал'],
    ['Отмены — % от броней',                         '', '', '', '', ''],
    ['No-show (факт)',                               '', '', '', '', 'Каждый случай: №брони, ФИО, сумма'],
    ['Бронирования без предоплаты',                  '', '', '', '', 'Каждый факт: №брони, ФИО, дата заезда'],
    ['Забронировано на следующий месяц, ₽',          '', '', '', '', 'Опережающий показатель'],
    ['Забронировано на следующий месяц, % от плана', '', '', '', '', ''],
  ];
  writeDataBlock(sh, 16, bookRows);

  // ── БЛОК 3: Каналы продаж ──
  writeSectionHeader(sh, 25, '📡 КАНАЛЫ ПРОДАЖ', C.hotelMid, C.white, 6);

  const chanRows = [
    ['Прямые бронирования, %',         '', '', '', '', 'Изменение >5пп — пересмотр стратегии'],
    ['OTA (Booking, Ostrovok и др.), %', '', '', '', '', ''],
    ['По телефону (входящие), %',       '', '', '', '', ''],
    ['Корпоративные, %',               '', '', '', '', ''],
    ['Группы / ДР, %',                 '', '', '', '', ''],
    ['Доля постоянных гостей, %',      '', '', '', '', 'Люфт ±10%'],
    ['Гости по акциям / промо, %',     '', '', '', '', 'Не более 20% от всех броней'],
  ];
  writeDataBlock(sh, 26, chanRows);

  // ── БЛОК 4: Контроль ──
  writeSectionHeader(sh, 34, '🔍 КОНТРОЛЬ (ручные операции)', C.hotelMid, C.white, 6);

  const ctrlRows = [
    ['Ручные скидки — кол-во',     '', '', '', '', 'Каждая: ФИО сотрудника, №брони, сумма'],
    ['Ручные скидки — сумма, ₽',   '', '', '', '', 'Норма: менее 1% от выручки в месяц'],
    ['Скидочных броней, % от всех','', '', '', '', 'Не более 20%'],
    ['Возвраты — кол-во',          '', '', '', '', 'Динамика ±5%'],
    ['Возвраты — сумма, ₽',        '', '', '', '', ''],
    ['Удалённых / изменённых броней', '', '', '', '', 'Каждый факт — сигнал к контролю'],
  ];
  writeDataBlock(sh, 35, ctrlRows);

  // Закрепляем строку с заголовками
  sh.setFrozenRows(4);
}

// ═══════════════════════════════════════════════════════════════
// ЛИСТ 2 — ОТЕЛЬ: СРАВНЕНИЕ YoY / WoW
// ═══════════════════════════════════════════════════════════════
function buildSheet2_Comparison(ss) {
  const sh = getOrCreateSheet(ss, '02 | Отель — YoY / WoW');
  sh.clear();
  sh.setTabColor(C.hotelMid);

  sh.setColumnWidth(1, 260);

  // 4 сегмента × 3 колонки каждый = 12 колонок
  const segments = ['Коттеджи', 'Хостел Ален', 'Хостел Даниэль', 'ИТОГО'];
  const subCols  = ['Текущая\nнеделя', 'Прошлый\nгод (YoY)', 'Откл., %'];

  let col = 2;
  segments.forEach(seg => {
    sh.setColumnWidth(col, 120);
    sh.setColumnWidth(col + 1, 120);
    sh.setColumnWidth(col + 2, 100);
    col += 3;
  });

  // Заголовок
  setCell(sh, 1, 1, '📊 ОТЕЛЬ — СРАВНЕНИЕ С ПРОШЛЫМ ГОДОМ (YoY)', C.hotelDark, C.white, 13, true, 13);
  mergeRange(sh, 1, 1, 1, 13);

  setCell(sh, 2, 1, 'Период текущей недели:', C.hotelMid, C.white, 10, true);
  setCell(sh, 2, 2, '', C.hotelLight, C.textDark, 10, false, 3);
  setCell(sh, 2, 5, 'Аналогичный период прошлого года:', C.hotelMid, C.white, 10, true);
  setCell(sh, 2, 6, '', C.hotelLight, C.textDark, 10, false, 3);
  mergeRange(sh, 2, 2, 2, 4);
  mergeRange(sh, 2, 6, 2, 8);

  // Сегменты (строка 3) — групповые заголовки
  col = 2;
  segments.forEach(seg => {
    setCell(sh, 3, col, seg, C.hotelMid, C.white, 10, true, 3);
    mergeRange(sh, 3, col, 3, col + 2);
    col += 3;
  });
  setCell(sh, 3, 1, 'Показатель', C.hotelDark, C.white, 10, true);

  // Подзаголовки (строка 4)
  setCell(sh, 4, 1, '', C.hotelLight, C.textDark, 9, true);
  col = 2;
  segments.forEach(() => {
    subCols.forEach((sub, i) => {
      setCell(sh, 4, col + i, sub, C.hotelLight, C.textDark, 9, true);
    });
    col += 3;
  });
  sh.setRowHeight(4, 36);

  // Метрики
  const metrics = [
    '💰 ФИНАНСЫ',
    'Выручка за неделю, ₽',
    'Средняя стоимость суток (ADR), ₽',
    'RevPAR (Доход на номер), ₽',
    'Загрузка (Occupancy), %',
    'Выручка от доп. услуг, ₽',
    '📋 БРОНИРОВАНИЯ',
    'Кол-во заездов',
    'Средняя длина пребывания (LOS), ночей',
    'Отмены, %',
    'No-show, кол-во',
    'Доля постоянных гостей, %',
    '📡 КАНАЛЫ',
    'Прямые бронирования, %',
    'OTA, %',
    'По телефону, %',
  ];

  let row = 5;
  metrics.forEach(m => {
    if (m.startsWith('💰') || m.startsWith('📋') || m.startsWith('📡')) {
      writeSectionHeader(sh, row, m, C.hotelMid, C.white, 13);
    } else {
      setCell(sh, row, 1, m, null, C.textDark, 10, false);
      sh.getRange(row, 1).setBackground(row % 2 === 0 ? C.rowEven : C.white);
      col = 2;
      for (let s = 0; s < 4; s++) {
        // Текущая
        sh.getRange(row, col).setBackground(row % 2 === 0 ? C.rowEven : C.white);
        // Прошлый год
        sh.getRange(row, col + 1).setBackground(row % 2 === 0 ? C.rowEven : C.white);
        // Отклонение % — с условным форматированием (зелёный/красный)
        const devCell = sh.getRange(row, col + 2);
        devCell.setBackground(row % 2 === 0 ? C.rowEven : C.white);
        devCell.setNumberFormat('0.0%');
        col += 3;
      }
    }
    row++;
  });

  // Условное форматирование для колонок отклонений (+/-)
  [4, 7, 10, 13].forEach(startCol => {
    const devCol = startCol; // 3-я колонка каждого сегмента
    const rng = sh.getRange(6, devCol, 20);
    const rulesPos = SpreadsheetApp.newConditionalFormatRule()
      .whenNumberGreaterThan(0.10)
      .setBackground(C.green).setFontColor(C.greenText)
      .setRanges([rng]).build();
    const rulesNeg = SpreadsheetApp.newConditionalFormatRule()
      .whenNumberLessThan(-0.10)
      .setBackground(C.red).setFontColor(C.redText)
      .setRanges([rng]).build();
    const rules = sh.getConditionalFormatRules();
    rules.push(rulesPos, rulesNeg);
    sh.setConditionalFormatRules(rules);
  });

  sh.setFrozenRows(4);
}

// ═══════════════════════════════════════════════════════════════
// ЛИСТ 3 — РЕСТОРАН МОНБЛАН
// ═══════════════════════════════════════════════════════════════
function buildSheet3_Restaurant(ss) {
  const sh = getOrCreateSheet(ss, '03 | Ресторан Монблан');
  sh.clear();
  sh.setTabColor(C.restDark);

  sh.setColumnWidth(1, 280);
  sh.setColumnWidth(2, 130);  // Текущая неделя
  sh.setColumnWidth(3, 130);  // Прошлый год
  sh.setColumnWidth(4, 110);  // Откл. %
  sh.setColumnWidth(5, 200);  // Примечание

  setCell(sh, 1, 1, '🍽 РЕСТОРАН МОНБЛАН — ДАННЫЕ НЕДЕЛИ', C.restDark, C.white, 13, true, 5);
  mergeRange(sh, 1, 1, 1, 5);
  setCell(sh, 2, 1, 'Период:', C.restMid, C.white, 10, true);
  setCell(sh, 2, 2, '', C.restLight, C.textDark, 10, false, 2);
  mergeRange(sh, 2, 2, 2, 3);

  writeHeaderRow(sh, 4, ['Показатель', 'Текущая неделя', 'Прошлый год (YoY)', 'Откл., %', 'Порог / Примечание'], C.restDark, C.white, 10);

  // ── БЛОК 1: Финансы ──
  writeSectionHeader(sh, 5, '💰 ФИНАНСЫ', C.restMid, C.white, 5);
  const finRows = [
    ['Выручка за неделю — ИТОГО, ₽',      '', '', '', '±10% к прош. году. Рост >10% — хвалим'],
    ['  в т.ч. Кухня, ₽',                 '', '', '', ''],
    ['  в т.ч. Бар, ₽',                   '', '', '', ''],
    ['  в т.ч. Банкеты / Мероприятия, ₽', '', '', '', ''],
    ['Доля кухни, %',                      '', '', '', 'Изменение доли >5пп — акцент'],
    ['Доля бара, %',                       '', '', '', ''],
    ['Средний чек на 1 гостя, ₽',         '', '', '', 'Люфт ±10%. Рост >20% — предупреждение'],
    ['Средний чек по кухне, ₽',           '', '', '', ''],
    ['Средний чек по бару, ₽',            '', '', '', ''],
    ['Food cost — сумма, ₽',              '', '', '', ''],
    ['Food cost — % от выручки',          '', '', '', 'Исторический коридор. +3пп — предупреждение; +5пп — критично'],
    ['Маржинальная прибыль — Кухня, ₽',   '', '', '', ''],
    ['Маржинальная прибыль — Бар, ₽',     '', '', '', ''],
    ['Маржинальная прибыль — ИТОГО, ₽',   '', '', '', ''],
    ['Маржинальность — % от выручки',     '', '', '', ''],
  ];
  writeDataBlock(sh, 6, finRows);  // строки 6–20

  // ── БЛОК 2: Банкеты / мероприятия ──
  writeSectionHeader(sh, 22, '🎉 БАНКЕТЫ / МЕРОПРИЯТИЯ', C.restMid, C.white, 5);
  const banquetRows = [
    ['Банкетов / мероприятий — кол-во',  '', '', '', 'Банкет без доп.продаж — сигнал (порог >10%)'],
    ['Банкеты — сумма выручки, ₽',       '', '', '', ''],
    ['Средний чек на гостя (банкет), ₽', '', '', '', ''],
    ['Средний чек на мероприятие, ₽',    '', '', '', ''],
  ];
  writeDataBlock(sh, 23, banquetRows);  // строки 23–26

  // ── БЛОК 3: Гости и трафик ──
  writeSectionHeader(sh, 28, '👥 ГОСТИ И ТРАФИК', C.restMid, C.white, 5);
  const guestRows = [
    ['Кол-во гостей за неделю',             '', '', '', 'Люфт ±10%'],
    ['Кол-во чеков за неделю',              '', '', '', ''],
    ['Оборачиваемость стола (раз/день)',     '', '', '', 'Рост — позитивный сигнал'],
    ['Средний стол (чеков/столов)',          '', '', '', '90 посадочных мест'],
    ['Доля постоянных гостей, %',           '', '', '', 'Люфт ±10%'],
    ['Гости по акциям / промо, %',          '', '', '', 'Не более 20%'],
  ];
  writeDataBlock(sh, 29, guestRows);  // строки 29–34

  // ── БЛОК 4: Выручка по времени суток ──
  writeSectionHeader(sh, 36, '⏰ ВЫРУЧКА ПО ВРЕМЕНИ СУТОК', C.restMid, C.white, 5);
  const timeRows = [
    ['Утро 09:00–11:00 — выручка, ₽',     '', '', '', ''],
    ['Утро 09:00–11:00 — кол-во гостей',  '', '', '', ''],
    ['День 11:00–17:00 — выручка, ₽',     '', '', '', ''],
    ['День 11:00–17:00 — кол-во гостей',  '', '', '', ''],
    ['Вечер 17:00–21:00 — выручка, ₽',    '', '', '', ''],
    ['Вечер 17:00–21:00 — кол-во гостей', '', '', '', ''],
  ];
  writeDataBlock(sh, 37, timeRows);  // строки 37–42

  // ── БЛОК 5: Списания ──
  writeSectionHeader(sh, 44, '🗑 СПИСАНИЯ', C.restMid, C.white, 5);
  const writeoffRows = [
    ['Списания "со списанием" — сумма, ₽',      '', '', '', '±20% к прош. неделе. >50% — критично'],
    ['Списания "со списанием" — кол-во позиций', '', '', '', ''],
    ['Списания "без списания" — сумма, ₽',      '', '', '', 'Аннулированные позиции до закрытия чека'],
    ['Списания "без списания" — кол-во',        '', '', '', 'Каждая: ФИО, №чека, сумма'],
    ['Удалённые позиции из чеков — кол-во',     '', '', '', 'Норма: <1% от выручки этих позиций'],
    ['Нулевые чеки — кол-во',                   '', '', '', 'Каждый — сигнал к злоупотреблению'],
  ];
  writeDataBlock(sh, 45, writeoffRows);  // строки 45–50

  // ── БЛОК 6: ТОП блюда ──
  writeSectionHeader(sh, 52, '🏆 ТОП-10 БЛЮД ПО ВЫРУЧКЕ', C.restMid, C.white, 5);
  sh.getRange(53, 1).setValue('#').setFontWeight('bold');
  sh.getRange(53, 2).setValue('Наименование').setFontWeight('bold');
  sh.getRange(53, 3).setValue('Выручка, ₽').setFontWeight('bold');
  sh.getRange(53, 4).setValue('Кол-во продаж').setFontWeight('bold');
  sh.getRange(53, 5).setValue('vs Прошлый год, %').setFontWeight('bold');
  sh.getRange(53, 1, 1, 5).setBackground(C.restLight);
  for (let i = 1; i <= 10; i++) {
    sh.getRange(53 + i, 1).setValue(i);
    sh.getRange(53 + i, 1, 1, 5).setBackground(i % 2 === 0 ? C.rowEven : C.white);
  }

  writeSectionHeader(sh, 65, '⚠️ АНТИРЕЙТИНГ — ПАДЕНИЕ ПРОДАЖ >20%', C.restDark, C.white, 5);
  sh.getRange(66, 1).setValue('Наименование').setFontWeight('bold');
  sh.getRange(66, 2).setValue('Текущий период').setFontWeight('bold');
  sh.getRange(66, 3).setValue('Прошлый год').setFontWeight('bold');
  sh.getRange(66, 4).setValue('Изменение, %').setFontWeight('bold');
  sh.getRange(66, 1, 1, 4).setBackground(C.red);
  for (let i = 1; i <= 5; i++) {
    sh.getRange(66 + i, 1, 1, 5).setBackground(i % 2 === 0 ? '#fdecea' : C.white);
  }

  // ── БЛОК 7: Контроль ──
  writeSectionHeader(sh, 73, '🔍 КОНТРОЛЬ (ручные операции)', C.restMid, C.white, 5);
  const ctrlRows = [
    ['Ручные скидки — кол-во',               '', '', '', 'Каждая: ФИО официанта, №чека, сумма, время'],
    ['Ручные скидки — сумма, ₽',             '', '', '', 'Норма: менее 1% от выручки в месяц'],
    ['Скидочных чеков, % от всех',           '', '', '', 'Не более 20%'],
    ['Чеков открытых >4 часов',              '', '', '', 'Каждый: №стола, ФИО официанта, время'],
    ['Транзакций с несколькими картами',     '', '', '', 'Более 1 карты в чеке — сигнал к мошенничеству'],
    ['Возвраты — кол-во',                    '', '', '', 'Динамика ±5%'],
    ['Возвраты — сумма, ₽',                  '', '', '', ''],
    ['Ручных вводов, % изменение нед./нед.', '', '', '', 'Люфт ±5%'],
  ];
  writeDataBlock(sh, 74, ctrlRows);  // строки 74–81

  // ── БЛОК 8: Отзывы ──
  writeSectionHeader(sh, 83, '⭐ ОТЗЫВЫ', C.restMid, C.white, 5);
  sh.getRange(84, 1).setValue('Платформа').setFontWeight('bold').setBackground(C.restLight);
  sh.getRange(84, 2).setValue('Кол-во за неделю').setFontWeight('bold').setBackground(C.restLight);
  sh.getRange(84, 3).setValue('Всего / рейтинг').setFontWeight('bold').setBackground(C.restLight);
  sh.getRange(84, 4).setValue('Доля негативных, %').setFontWeight('bold').setBackground(C.restLight);
  sh.getRange(84, 5).setValue('Примечание').setFontWeight('bold').setBackground(C.restLight);
  [['Яндекс Карты'], ['2ГИС'], ['Книга отзывов (оффлайн)'], ['Booking / OTA']].forEach((platform, i) => {
    sh.getRange(85 + i, 1).setValue(platform[0]);
    sh.getRange(85 + i, 1, 1, 5).setBackground(i % 2 === 0 ? C.rowEven : C.white);
  });

  sh.setFrozenRows(4);
}

// ═══════════════════════════════════════════════════════════════
// ЛИСТ 4 — ОПЕРАЦИОННЫЙ ЖУРНАЛ (ручной ввод)
// ═══════════════════════════════════════════════════════════════
function buildSheet4_Operations(ss) {
  const sh = getOrCreateSheet(ss, '04 | Операционный журнал');
  sh.clear();
  sh.setTabColor(C.opsDark);

  sh.setColumnWidth(1, 220);
  sh.setColumnWidth(2, 80);
  sh.setColumnWidth(3, 80);
  sh.setColumnWidth(4, 350);

  setCell(sh, 1, 1, '📝 ОПЕРАЦИОННЫЙ ЖУРНАЛ — РУЧНОЙ ВВОД', C.opsDark, C.white, 13, true, 4);
  mergeRange(sh, 1, 1, 1, 4);
  setCell(sh, 2, 1, 'Период (Пн–Вс):', C.opsDark, C.white, 10, true);
  setCell(sh, 2, 2, '', C.opsLight, C.textDark, 10, false, 3);
  mergeRange(sh, 2, 2, 2, 4);
  setCell(sh, 3, 1, 'Заполнил:', C.opsDark, C.white, 10, true);
  setCell(sh, 3, 2, '', C.opsLight, C.textDark, 10, false, 3);
  mergeRange(sh, 3, 2, 3, 4);

  writeHeaderRow(sh, 5, ['Параметр', 'Значение', 'Ед.', 'Комментарий / детали'], C.opsDark, C.white, 10);

  // ── БЛОК 1: Уборки ──
  writeSectionHeader(sh, 6, '🧹 УБОРКИ', C.opsDark, C.white, 4);
  const cleanRows = [
    ['Уборок коттеджей — всего',         '', 'шт.', ''],
    ['  в т.ч. стыковочных',             '', 'шт.', ''],
    ['Уборок хостел Ален — всего',       '', 'шт.', ''],
    ['  в т.ч. стыковочных',             '', 'шт.', ''],
    ['Уборок хостел Даниэль — всего',    '', 'шт.', ''],
    ['  в т.ч. стыковочных',             '', 'шт.', ''],
  ];
  writeDataBlock(sh, 7, cleanRows, true);

  // ── БЛОК 2: Звонки ──
  writeSectionHeader(sh, 14, '📞 ЗВОНКИ', C.opsDark, C.white, 4);
  const callRows = [
    ['Входящих звонков — всего',         '', 'шт.', ''],
    ['Неотвеченных звонков',             '', 'шт.', ''],
    ['% неотвеченных',                   '', '%',   'Норма: <10%. 10–20% — предупреждение. >20% — критично'],
  ];
  writeDataBlock(sh, 15, callRows, true);

  // ── БЛОК 3: Ремонтные заявки ──
  writeSectionHeader(sh, 19, '🔧 РЕМОНТ И ТЕХНИКА', C.opsDark, C.white, 4);
  const repairRows = [
    ['Заявок на ремонт — подано',        '', 'шт.', ''],
    ['Заявок выполнено',                 '', 'шт.', ''],
    ['Заявок не выполнено (открытые)',   '', 'шт.', 'Перечислить объекты'],
    ['Технических неполадок (водо/электро)', '', 'шт.', 'Описание и статус'],
  ];
  writeDataBlock(sh, 20, repairRows, true);

  // ── БЛОК 4: Персонал ──
  writeSectionHeader(sh, 25, '👥 ПЕРСОНАЛ', C.opsDark, C.white, 4);
  const staffRows = [
    ['Трансферов выполнено',             '', 'шт.', ''],
    ['Персонала в среднем за смену',     '', 'чел.', ''],
  ];
  writeDataBlock(sh, 26, staffRows, true);

  // ── БЛОК 5: Инциденты ──
  writeSectionHeader(sh, 29, '⚠️ ИНЦИДЕНТЫ С ГОСТЯМИ', C.opsDark, C.white, 4);
  sh.getRange(30, 1).setValue('Описание инцидента').setFontWeight('bold').setBackground(C.opsLight);
  sh.getRange(30, 2).setValue('Котт/Хостел').setFontWeight('bold').setBackground(C.opsLight);
  sh.getRange(30, 3).setValue('Статус').setFontWeight('bold').setBackground(C.opsLight);
  sh.getRange(30, 4).setValue('Как решили').setFontWeight('bold').setBackground(C.opsLight);
  for (let i = 1; i <= 5; i++) {
    sh.getRange(30 + i, 1, 1, 4).setBackground(i % 2 === 0 ? C.rowEven : C.white);
    sh.setRowHeight(30 + i, 40);
  }

  // ── БЛОК 6: Отзывы ──
  writeSectionHeader(sh, 37, '⭐ ОТЗЫВЫ (ВНЕШНИЕ)', C.opsDark, C.white, 4);
  sh.getRange(38, 1).setValue('Платформа').setFontWeight('bold').setBackground(C.opsLight);
  sh.getRange(38, 2).setValue('Кол-во').setFontWeight('bold').setBackground(C.opsLight);
  sh.getRange(38, 3).setValue('Средний балл').setFontWeight('bold').setBackground(C.opsLight);
  sh.getRange(38, 4).setValue('Содержание (кратко)').setFontWeight('bold').setBackground(C.opsLight);
  [['Яндекс'], ['2ГИС'], ['Книга отзывов'], ['Booking / OTA']].forEach((platform, i) => {
    sh.getRange(39 + i, 1).setValue(platform[0]);
    sh.getRange(39 + i, 1, 1, 4).setBackground(i % 2 === 0 ? C.rowEven : C.white);
  });

  // ── БЛОК 7: Прочее ──
  writeSectionHeader(sh, 44, '🌤 ПРОЧЕЕ (контекст недели)', C.opsDark, C.white, 4);
  const miscRows = [
    ['Погода (краткое описание)',         '', '',   ''],
    ['События на курорте',               '', '',   'Соревнования, концерты, фестивали'],
    ['Праздничные / выходные дни',       '', 'шт.', ''],
    ['Прочие замечания',                 '', '',   ''],
  ];
  writeDataBlock(sh, 45, miscRows, true);

  sh.setFrozenRows(5);
}

// ═══════════════════════════════════════════════════════════════
// ЛИСТ 5 — СВОДНЫЙ ДАШБОРД
// ═══════════════════════════════════════════════════════════════
function buildSheet5_Dashboard(ss) {
  const sh = getOrCreateSheet(ss, '05 | Дашборд');
  sh.clear();
  sh.setTabColor(C.dashDark);

  // Ширина
  [1,2,3,4,5,6,7].forEach(c => sh.setColumnWidth(c, 140));
  sh.setColumnWidth(1, 200);

  setCell(sh, 1, 1, '📊 СВОДНЫЙ ДАШБОРД — КУРОРТ ГУБАХА', C.dashDark, C.white, 14, true, 7);
  mergeRange(sh, 1, 1, 1, 7);
  setCell(sh, 2, 1, 'Неделя:', C.dashDark, C.white, 10, true);
  setCell(sh, 2, 2, '', C.dashLight, C.textDark, 10, false, 3);
  mergeRange(sh, 2, 2, 2, 4);

  // ── ОТЕЛЬ ──
  setCell(sh, 4, 1, '🏨 ОТЕЛЬ', C.hotelDark, C.white, 12, true, 7);
  mergeRange(sh, 4, 1, 4, 7);

  writeHeaderRow(sh, 5, ['Показатель', 'Коттеджи', 'Хостел Ален', 'Хостел Даниэль', 'ИТОГО', 'vs ПГ, %', 'Статус'], C.hotelMid, C.white, 10);

  const hotelKpi = [
    'Выручка, ₽',
    'Загрузка (Occupancy), %',
    'ADR (Средняя цена), ₽',
    'RevPAR, ₽',
    'Кол-во гостей',
    'LOS, ночей',
    'Отмены, %',
  ];
  hotelKpi.forEach((k, i) => {
    const row = 6 + i;
    setCell(sh, row, 1, k, null, C.textDark, 10, false);
    sh.getRange(row, 1, 1, 7).setBackground(i % 2 === 0 ? C.rowEven : C.white);
    // Статус — светофор (заполняется формулами / скриптом)
    sh.getRange(row, 7).setValue('—').setHorizontalAlignment('center');
  });

  // ── РЕСТОРАН ──
  setCell(sh, 14, 1, '🍽 РЕСТОРАН МОНБЛАН', C.restDark, C.white, 12, true, 7);
  mergeRange(sh, 14, 1, 14, 7);

  writeHeaderRow(sh, 15, ['Показатель', 'Факт', 'Прошлый год', 'Откл., %', '', '', 'Статус'], C.restMid, C.white, 10);

  const restKpi = [
    'Выручка, ₽',
    'Food cost, %',
    'Средний чек, ₽',
    'Кол-во гостей',
    'Маржинальность, %',
    'Списания "со списанием", ₽',
  ];
  restKpi.forEach((k, i) => {
    const row = 16 + i;
    setCell(sh, row, 1, k, null, C.textDark, 10, false);
    sh.getRange(row, 1, 1, 7).setBackground(i % 2 === 0 ? C.rowEven : C.white);
    sh.getRange(row, 7).setValue('—').setHorizontalAlignment('center');
  });

  // ── ОПЕРАЦИИ ──
  setCell(sh, 23, 1, '⚙️ ОПЕРАЦИИ', C.opsDark, C.white, 12, true, 7);
  mergeRange(sh, 23, 1, 23, 7);

  writeHeaderRow(sh, 24, ['Показатель', 'Факт', 'Норма', '', '', '', 'Статус'], C.opsDark, C.white, 10);

  const opsKpi = [
    ['Невыполненных заявок на ремонт', '', '0'],
    ['% неотвеченных звонков',         '', '<10%'],
    ['Открытых техн. неполадок',        '', '0'],
    ['No-show за неделю',              '', '0'],
  ];
  opsKpi.forEach((k, i) => {
    const row = 25 + i;
    setCell(sh, row, 1, k[0], null, C.textDark, 10, false);
    setCell(sh, row, 2, k[1], null, C.textDark, 10, false);
    setCell(sh, row, 3, k[2], null, C.textMid, 9, false);
    sh.getRange(row, 1, 1, 7).setBackground(i % 2 === 0 ? C.rowEven : C.white);
    sh.getRange(row, 7).setValue('—').setHorizontalAlignment('center');
  });

  // ── ЛЕГЕНДА СВЕТОФОРА ──
  setCell(sh, 30, 1, 'Легенда:', C.dashDark, C.white, 10, true, 3);
  mergeRange(sh, 30, 1, 30, 3);
  sh.getRange(31, 1).setValue('🟢 Норма (откл. <10%)').setBackground(C.green);
  sh.getRange(32, 1).setValue('🟡 Внимание (откл. 10–20%)').setBackground(C.yellow);
  sh.getRange(33, 1).setValue('🔴 Критично (откл. >20%)').setBackground(C.red);
  sh.getRange(31, 1, 3, 3).setFontSize(10);

  sh.setFrozenRows(2);
}

// ═══════════════════════════════════════════════════════════════
// ЛИСТ 6 — ИИ-АНАЛИЗ
// ═══════════════════════════════════════════════════════════════
function buildSheet6_AI(ss) {
  const sh = getOrCreateSheet(ss, '06 | ИИ-анализ');
  sh.clear();
  sh.setTabColor(C.aiDark);

  sh.setColumnWidth(1, 140);
  sh.setColumnWidth(2, 700);

  setCell(sh, 1, 1, '🤖 ИИ-АНАЛИЗ — ПРОБЛЕМНЫЕ ТОЧКИ И РЕКОМЕНДАЦИИ', C.aiDark, C.white, 13, true, 2);
  mergeRange(sh, 1, 1, 1, 2);
  setCell(sh, 2, 1, 'Сгенерировано:', C.aiDark, C.white, 10, true);
  setCell(sh, 2, 2, '', C.aiLight, C.textDark, 10, false);
  setCell(sh, 3, 1, 'Период:', C.aiDark, C.white, 10, true);
  setCell(sh, 3, 2, '', C.aiLight, C.textDark, 10, false);
  setCell(sh, 4, 1, 'Модель:', C.aiDark, C.white, 10, true);
  setCell(sh, 4, 2, CONFIG.CLAUDE.MODEL, C.aiLight, C.textDark, 10, false);

  // Разделы
  const sections = [
    { row: 6,  title: 'A. ВЫЯВЛЕННЫЕ ОТКЛОНЕНИЯ', desc: 'Список аномалий, определённых системой на основе исторических данных:' },
    { row: 14, title: 'Б. ВОЗМОЖНЫЕ ПРИЧИНЫ',     desc: 'Анализ каждого отклонения с учётом сезонности и исторических паттернов:' },
    { row: 22, title: 'В. РЕКОМЕНДАЦИИ',           desc: 'Конкретные, применимые действия по каждой проблемной точке:' },
    { row: 30, title: 'Г. СВОДНАЯ ОЦЕНКА НЕДЕЛИ',  desc: 'Итоговая оценка и приоритет действий:' },
  ];

  sections.forEach(s => {
    setCell(sh, s.row, 1, s.title, C.aiDark, C.white, 11, true, 2);
    mergeRange(sh, s.row, 1, s.row, 2);
    setCell(sh, s.row + 1, 1, s.desc, C.aiLight, C.textDark, 9, false, 2);
    mergeRange(sh, s.row + 1, s.row + 1, s.row + 1, 2);  // fix: mergeRange params
    sh.getRange(s.row + 1, 1).setWrap(true);
    sh.getRange(s.row + 1, 1, 1, 2).merge();

    // Поле для текста ИИ
    const aiCell = sh.getRange(s.row + 2, 1, 5, 2);
    aiCell.merge();
    aiCell.setBackground(C.white);
    aiCell.setBorder(true, true, true, true, false, false, '#cccccc', SpreadsheetApp.BorderStyle.SOLID);
    aiCell.setWrap(true);
    aiCell.setVerticalAlignment('top');
    aiCell.setFontSize(10);
    sh.setRowHeight(s.row + 2, 100);
  });

  setCell(sh, 37, 1, '⚠️ Этот лист заполняется автоматически скриптом main.gs (Этап 5). Не редактируйте вручную.', '#f0f0f0', '#888888', 9, false, 2);
  mergeRange(sh, 37, 1, 37, 2);

  sh.setFrozenRows(4);
}

// ═══════════════════════════════════════════════════════════════
// ЛИСТ 7 — СЫРЫЕ ДАННЫЕ
// ═══════════════════════════════════════════════════════════════
function buildSheet7_Raw(ss) {
  const sh = getOrCreateSheet(ss, '07 | Сырые данные');
  sh.clear();
  sh.setTabColor(C.rawDark);

  sh.setColumnWidth(1, 200);
  sh.setColumnWidth(2, 700);

  setCell(sh, 1, 1, '⚙️ СЫРЫЕ ДАННЫЕ API — СЛУЖЕБНЫЙ ЛИСТ', C.rawDark, C.white, 12, true, 2);
  mergeRange(sh, 1, 1, 1, 2);
  setCell(sh, 2, 1, 'Обновлено:', C.rawDark, C.white, 10, true);
  setCell(sh, 2, 2, '', C.rawLight, C.textDark, 10, false);
  setCell(sh, 3, 1, '⚠️ Этот лист заполняется скриптами автоматически. Не редактируйте вручную.', '#fff9c4', '#7d6608', 9, false, 2);
  mergeRange(sh, 3, 1, 3, 2);

  // Travelline
  setCell(sh, 5, 1, '── TRAVELLINE API ──────────────────', C.rawDark, C.white, 10, true, 2);
  mergeRange(sh, 5, 1, 5, 2);
  sh.getRange(6, 1).setValue('Ключ (поле)').setFontWeight('bold').setBackground(C.rawLight);
  sh.getRange(6, 2).setValue('Значение / JSON').setFontWeight('bold').setBackground(C.rawLight);
  for (let i = 7; i <= 30; i++) {
    sh.getRange(i, 1, 1, 2).setBackground(i % 2 === 0 ? '#f8f8f8' : C.white);
  }

  // IIKO
  setCell(sh, 32, 1, '── IIKO API ────────────────────────', C.rawDark, C.white, 10, true, 2);
  mergeRange(sh, 32, 1, 32, 2);
  sh.getRange(33, 1).setValue('Ключ (поле)').setFontWeight('bold').setBackground(C.rawLight);
  sh.getRange(33, 2).setValue('Значение / JSON').setFontWeight('bold').setBackground(C.rawLight);
  for (let i = 34; i <= 60; i++) {
    sh.getRange(i, 1, 1, 2).setBackground(i % 2 === 0 ? '#f8f8f8' : C.white);
  }

  sh.setFrozenRows(6);
}

// ═══════════════════════════════════════════════════════════════
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ═══════════════════════════════════════════════════════════════

/** Получить существующий лист или создать новый */
function getOrCreateSheet(ss, name) {
  let sh = ss.getSheetByName(name);
  if (sh) {
    sh.clear();
    sh.clearFormats();
  } else {
    sh = ss.insertSheet(name);
  }
  return sh;
}

/** Удалить листы по умолчанию (Лист1, Sheet1 и т.п.) */
function cleanupDefaultSheets(ss) {
  const defaultNames = ['Лист1', 'Sheet1', 'Лист 1', 'Sheet 1'];
  ss.getSheets().forEach(sh => {
    if (defaultNames.includes(sh.getName())) {
      if (ss.getSheets().length > 1) ss.deleteSheet(sh);
    }
  });
}

/** Установить содержимое и форматирование одной ячейки */
function setCell(sh, row, col, value, bgColor, fontColor, fontSize, bold, mergeCount) {
  const cell = sh.getRange(row, col);
  cell.setValue(value);
  if (bgColor)   cell.setBackground(bgColor);
  if (fontColor) cell.setFontColor(fontColor);
  if (fontSize)  cell.setFontSize(fontSize);
  if (bold)      cell.setFontWeight('bold');
  cell.setVerticalAlignment('middle');
  cell.setWrap(true);
}

/** Объединить ячейки */
function mergeRange(sh, row1, col1, row2, col2) {
  try { sh.getRange(row1, col1, row2 - row1 + 1, col2 - col1 + 1).merge(); } catch(e) {}
}

/** Записать строку заголовков */
function writeHeaderRow(sh, row, headers, bg, fontColor, fontSize) {
  headers.forEach((h, i) => {
    const cell = sh.getRange(row, i + 1);
    cell.setValue(h)
        .setBackground(bg)
        .setFontColor(fontColor)
        .setFontSize(fontSize)
        .setFontWeight('bold')
        .setVerticalAlignment('middle')
        .setHorizontalAlignment('center')
        .setWrap(true);
  });
  sh.setRowHeight(row, 36);
}

/** Записать заголовок секции (строка на всю ширину) */
function writeSectionHeader(sh, row, title, bg, fontColor, colSpan) {
  const rng = sh.getRange(row, 1, 1, colSpan || 5);
  rng.merge()
     .setValue(title)
     .setBackground(bg)
     .setFontColor(fontColor)
     .setFontSize(10)
     .setFontWeight('bold')
     .setVerticalAlignment('middle');
  sh.setRowHeight(row, 28);
}

/** Записать блок строк данных */
function writeDataBlock(sh, startRow, rows, narrow) {
  rows.forEach((row, i) => {
    const absRow = startRow + i;
    const bg = i % 2 === 0 ? C.white : C.rowEven;
    row.forEach((val, j) => {
      const cell = sh.getRange(absRow, j + 1);
      cell.setValue(val).setBackground(bg).setFontSize(10).setVerticalAlignment('middle').setWrap(true);
      if (j === 0) cell.setFontColor(C.textDark);
      else         cell.setFontColor(C.textMid);
    });
    if (narrow) sh.setRowHeight(absRow, 24);
    else        sh.setRowHeight(absRow, 28);
  });
}
