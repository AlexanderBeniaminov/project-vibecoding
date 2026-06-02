/**
 * МОНБЛАН — ПОСТРОЕНИЕ ТРЕКИНГ-ЛИСТА
 *
 * Инструкция:
 *   1. Откройте вторую Google Таблицу
 *      https://docs.google.com/spreadsheets/d/1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI/edit
 *   2. Меню → Расширения → Apps Script
 *   3. Вставьте monblan_config.gs и monblan_build.gs в редактор
 *   4. Выберите функцию buildMonblanSheet и нажмите ▶ Выполнить
 *   5. При запросе — разрешите доступ
 *
 * ⚠️ Скрипт ПОЛНОСТЬЮ ПЕРЕЗАПИСЫВАЕТ лист трекинга.
 *    Убедитесь, что важные данные сохранены.
 *
 * Формат листа:
 *   Строки = метрики (96 строк)
 *   Столбцы = недели (столбец A — названия, B+ — данные)
 */

// ═══════════════════════════════════════════════════════════════
// ПАЛИТРА ЦВЕТОВ
// ═══════════════════════════════════════════════════════════════
const MB_C = {
  // Заголовочные строки (год, неделя, дата)
  yearBg:       '#1a3a5c',   // тёмно-синий
  yearText:     '#ffffff',
  weekBg:       '#2d6a9f',   // средний синий
  weekText:     '#ffffff',
  dateBg:       '#d0e4f7',   // светло-голубой
  dateText:     '#1a1a1a',

  // Строки данных (выручка, гости и т.д.)
  dataBg:       '#ffffff',
  dataBgAlt:    '#f8f9fa',
  dataText:     '#1a1a1a',

  // Строки процентов (расчётные)
  pctBg:        '#eef3fa',   // очень светло-голубой
  pctText:      '#2d5a8e',

  // Строки расчётных показателей (средний чек, оборачиваемость)
  formulaBg:    '#f0f4f0',   // очень светло-зелёный
  formulaText:  '#1a4a1a',

  // Заголовки разделов
  sectionBg:    '#3d3d3d',   // тёмно-серый
  sectionText:  '#ffffff',

  // Статичные строки (Столов, Мест)
  staticBg:     '#f5f5f0',
  staticText:   '#555555',

  // Столбец A (метки)
  colABg:       '#f0f0f0',

  white:        '#ffffff',
};

// ═══════════════════════════════════════════════════════════════
// СТРУКТУРА СТРОК
//
// Типы строк:
//   'year'     — строка года (шапка)
//   'week'     — строка номера недели
//   'date'     — строка диапазона дат
//   'data'     — данные из IIKO (цифры)
//   'pct'      — расчётный процент: formula.num / formula.den
//   'calc'     — расчётный показатель (ср. чек, оборачиваемость)
//   'section'  — заголовок раздела (без данных)
//   'static'   — фиксированное значение (Столов=90, Мест=90)
//   'empty'    — пустая строка-разделитель
// ═══════════════════════════════════════════════════════════════
var MB_ROWS = [
  { r:1,  label:'Год',                                 type:'year'    },
  { r:2,  label:'Неделя',                              type:'week'    },
  { r:3,  label:'Монблан',                             type:'date'    },

  // ── ВЫРУЧКА ─────────────────────────────────────────────────
  { r:4,  label:'Выручка всего и по категориям',       type:'data'    },
  { r:5,  label:'Кухня',                               type:'data'    },
  { r:6,  label:'',                                    type:'pct',    formula:{num:5,  den:4}  },
  { r:7,  label:'Бар',                                 type:'data'    },
  { r:8,  label:'',                                    type:'pct',    formula:{num:7,  den:4}  },

  // ── ВЫРУЧКА ПО ВРЕМЕНИ СУТОК ─────────────────────────────────
  { r:9,  label:'Выручка день - вечер',                type:'section' },
  { r:10, label:'Утро (9:00 - 11:00)',                 type:'data'    },
  { r:11, label:'',                                    type:'pct',    formula:{num:10, den:4}  },
  { r:12, label:'День (11:00 - 17:00)',                type:'data'    },
  { r:13, label:'',                                    type:'pct',    formula:{num:12, den:4}  },
  { r:14, label:'Вечер (17:00 - 21:00)',               type:'data'    },
  { r:15, label:'',                                    type:'pct',    formula:{num:14, den:4}  },

  // ── ВЫРУЧКА ПО ДНЯМ НЕДЕЛИ ───────────────────────────────────
  { r:16, label:'Средняя выручка по дням недели',      type:'calc',   formula:{type:'div7', num:4}            },
  { r:17, label:'Понедельник',                         type:'data'    },
  { r:18, label:'',                                    type:'pct',    formula:{num:17, den:16} },
  { r:19, label:'Вторник',                             type:'data'    },
  { r:20, label:'',                                    type:'pct',    formula:{num:19, den:16} },
  { r:21, label:'Среда',                               type:'data'    },
  { r:22, label:'',                                    type:'pct',    formula:{num:21, den:16} },
  { r:23, label:'Четверг',                             type:'data'    },
  { r:24, label:'',                                    type:'pct',    formula:{num:23, den:16} },
  { r:25, label:'Пятница',                             type:'data'    },
  { r:26, label:'',                                    type:'pct',    formula:{num:25, den:16} },
  { r:27, label:'Суббота',                             type:'data'    },
  { r:28, label:'',                                    type:'pct',    formula:{num:27, den:16} },
  { r:29, label:'Воскресенье',                         type:'data'    },
  { r:30, label:'',                                    type:'pct',    formula:{num:29, den:16} },

  // ── ГОСТИ ────────────────────────────────────────────────────
  { r:31, label:'Кол-во гостей',                       type:'data'    },
  { r:32, label:'Утро (9:00 - 11:00)',                 type:'data'    },
  { r:33, label:'',                                    type:'pct',    formula:{num:32, den:31} },
  { r:34, label:'День (11:00 - 17:00)',                type:'data'    },
  { r:35, label:'',                                    type:'pct',    formula:{num:34, den:31} },
  { r:36, label:'Вечер (17:00 - 21:00)',               type:'data'    },
  { r:37, label:'',                                    type:'pct',    formula:{num:36, den:31} },

  // ── СРЕДНИЙ ЧЕК НА ГОСТЯ ─────────────────────────────────────
  { r:38, label:'Средний чек на гостя',                type:'calc',   formula:{type:'div', num:4,  den:31} },
  { r:39, label:'Утро (9:00 - 11:00)',                 type:'calc',   formula:{type:'div', num:10, den:32} },
  { r:40, label:'День (11:00 - 17:00)',                type:'calc',   formula:{type:'div', num:12, den:34} },
  { r:41, label:'Вечер (17:00 - 21:00)',               type:'calc',   formula:{type:'div', num:14, den:36} },

  // ── ЧЕКИ ─────────────────────────────────────────────────────
  { r:42, label:'Кол-во чеков',                        type:'data'    },
  { r:43, label:'Утро (9:00 - 11:00)',                 type:'data'    },
  { r:44, label:'День (11:00 - 17:00)',                type:'data'    },
  { r:45, label:'Вечер (17:00 - 21:00)',               type:'data'    },

  // ── БЛЮДА И СРЕДНИЕ ПОКАЗАТЕЛИ ──────────────────────────────
  { r:46, label:'Количество блюд',                     type:'data'    },
  { r:47, label:'Средний счет',                        type:'calc',   formula:{type:'div', num:4,  den:42} },
  { r:48, label:'Средний чек на блюдо',                type:'calc',   formula:{type:'div', num:4,  den:46} },
  { r:49, label:'Средний чек на гостя (кухня)',        type:'calc',   formula:{type:'div', num:5,  den:31} },
  { r:50, label:'Средний чек на гостя (бар)',          type:'calc',   formula:{type:'div', num:7,  den:31} },
  { r:51, label:'Ср. кол-во блюд на гостя',           type:'calc',   formula:{type:'div', num:46, den:31} },

  // ── ОБОРАЧИВАЕМОСТЬ СТОЛОВ ────────────────────────────────────
  // Формула: чеки / столов (строка 87) / 7 дней (итого за неделю)
  // Для слотов утро/день/вечер: чеки_слота / столов (без делителя 7)
  { r:52, label:'Оборачиваемость столов',              type:'calc',   formula:{type:'turn_total', checks:42, cap:87} },
  { r:53, label:'Утро (9:00 - 11:00)',                 type:'calc',   formula:{type:'turn_slot',  checks:43, cap:87} },
  { r:54, label:'День (11:00 - 17:00)',                type:'calc',   formula:{type:'turn_slot',  checks:44, cap:87} },
  { r:55, label:'Вечер (17:00 - 21:00)',               type:'calc',   formula:{type:'turn_slot',  checks:45, cap:87} },
  { r:56, label:'Оборачиваемость пос. мест',           type:'calc',   formula:{type:'turn_total', checks:42, cap:88} },
  { r:57, label:'Утро (9:00 - 11:00)',                 type:'calc',   formula:{type:'turn_slot',  checks:43, cap:88} },
  { r:58, label:'День (11:00 - 17:00)',                type:'calc',   formula:{type:'turn_slot',  checks:44, cap:88} },
  { r:59, label:'Вечер (17:00 - 21:00)',               type:'calc',   formula:{type:'turn_slot',  checks:45, cap:88} },

  // ── ВКЛАД ГРУПП ГОСТЕЙ ─────────────────────────────────────
  { r:60, label:'Вклад в выручку группы гостей',       type:'section' },
  { r:61, label:'Выручка по чекам 1 гость',            type:'data'    },
  { r:62, label:'',                                    type:'pct',    formula:{num:61, den:4}  },
  { r:63, label:'Выручка по чекам 2 гостя',            type:'data'    },
  { r:64, label:'',                                    type:'pct',    formula:{num:63, den:4}  },
  { r:65, label:'Выручка по чекам 3+ гостя',           type:'data'    },
  { r:66, label:'',                                    type:'pct',    formula:{num:65, den:4}  },
  // Коэффициент лояльности = выручка группами 2+ / общая выручка
  { r:67, label:'Коэффициент групповой лояльности',    type:'calc',   formula:{type:'loyalty'}  },
  { r:68, label:'Кол-во чеков 1 гость',                type:'data'    },
  { r:69, label:'',                                    type:'pct',    formula:{num:68, den:42} },
  { r:70, label:'Кол-во чеков 2 гостя',                type:'data'    },
  { r:71, label:'',                                    type:'pct',    formula:{num:70, den:42} },
  { r:72, label:'Кол-во чеков 3 + гостя',              type:'data'    },
  { r:73, label:'',                                    type:'pct',    formula:{num:72, den:42} },

  // ── ГРАДАЦИЯ ЧЕКОВ ────────────────────────────────────────────
  { r:74, label:'Градация чеков по сумме, выручка',    type:'section' },
  { r:75, label:'0-500 руб.',                          type:'data'    },
  { r:76, label:'',                                    type:'pct',    formula:{num:75, den:4}  },
  { r:77, label:'500-1000 руб.',                       type:'data'    },
  { r:78, label:'',                                    type:'pct',    formula:{num:77, den:4}  },
  { r:79, label:'1000-1500 руб.',                      type:'data'    },
  { r:80, label:'',                                    type:'pct',    formula:{num:79, den:4}  },
  { r:81, label:'1500-3000 руб.',                      type:'data'    },
  { r:82, label:'',                                    type:'pct',    formula:{num:81, den:4}  },
  { r:83, label:'3000-5000 руб.',                      type:'data'    },
  { r:84, label:'',                                    type:'pct',    formula:{num:83, den:4}  },
  { r:85, label:'5000 + руб',                          type:'data'    },
  { r:86, label:'',                                    type:'pct',    formula:{num:85, den:4}  },

  // ── СТАТИЧНЫЕ ПАРАМЕТРЫ ───────────────────────────────────────
  { r:87, label:'Столов',                              type:'static', value: MB_CONFIG.TABLES  },
  { r:88, label:'Посадочных мест',                     type:'static', value: MB_CONFIG.SEATS   },
  { r:89, label:'',                                    type:'empty'   },

  // ── МЕРОПРИЯТИЯ ───────────────────────────────────────────────
  { r:90, label:'Мероприятия',                         type:'section' },
  { r:91, label:'Завтраки (кол-во по гостям)',         type:'data'    },
  { r:92, label:'Количество мероприятий',              type:'data'    },
  { r:93, label:'Выручка мероприятий',                 type:'data'    },
  { r:94, label:'Количество гостей',                   type:'data'    },
  { r:95, label:'Средний чек на гостя',                type:'calc',   formula:{type:'div', num:93, den:94} },
  { r:96, label:'Средний чек на мероприятие',          type:'calc',   formula:{type:'div', num:93, den:92} },
];

// ═══════════════════════════════════════════════════════════════
// ГЛАВНАЯ ФУНКЦИЯ — вызывайте её из меню Apps Script
// ═══════════════════════════════════════════════════════════════
function buildMonblanSheet(opt_silent, opt_ss) {
  var ss = opt_ss || SpreadsheetApp.getActiveSpreadsheet();
  ss.setSpreadsheetTimeZone(MB_CONFIG.TIMEZONE);

  var sh = getMonblanSheet_(ss);
  if (!sh) {
    SpreadsheetApp.getUi().alert('Лист не найден!\nПроверьте MB_CONFIG.TRACKING_SHEET_NAME или GID.');
    return;
  }

  if (!opt_silent) {
    ss.toast('Строим структуру листа Монблан...', 'Монблан Трекинг', 60);
  }

  // Шаг 1 — очистка
  sh.clear();
  sh.clearFormats();

  // Шаг 1б — расширяем лист до нужного количества столбцов
  var neededCols = MB_CONFIG.WEEKS_TO_INIT + 1;  // +1 для столбца A
  var currentCols = sh.getMaxColumns();
  if (currentCols < neededCols) {
    sh.insertColumnsAfter(currentCols, neededCols - currentCols);
  }
  // Расширяем строки до 96 если нужно
  var neededRows = 96;
  var currentRows = sh.getMaxRows();
  if (currentRows < neededRows) {
    sh.insertRowsAfter(currentRows, neededRows - currentRows);
  }

  // Шаг 2 — ширина столбцов (одним вызовом вместо цикла)
  sh.setColumnWidth(1, 260);  // Столбец A — названия метрик
  sh.setColumnWidths(2, MB_CONFIG.WEEKS_TO_INIT, 90);

  // Шаг 3 — заголовки строк (Год, Неделя, Дата) + высоты строк
  buildHeaders_(sh);

  // Шаг 4 — метки в столбце A + форматирование строк
  buildColumnA_(sh);

  // Шаг 5 — формулы для всех столбцов данных
  buildFormulas_(sh);

  // Шаг 6 — статичные значения (Столов, Мест)
  buildStaticValues_(sh);

  // Шаг 7 — числовые форматы
  applyNumberFormats_(sh);

  // Шаг 8 — закрепить строки 1-3 и столбец A
  sh.setFrozenRows(3);
  sh.setFrozenColumns(1);

  if (!opt_silent) {
    SpreadsheetApp.getUi().alert(
      '✅ Лист Монблан построен!\n\n' +
      'Строк метрик: 96\n' +
      'Столбцов недель: ' + MB_CONFIG.WEEKS_TO_INIT + '\n' +
      'Первая неделя: ' + MB_CONFIG.START_YEAR + ' нед.' + MB_CONFIG.START_WEEK + '\n\n' +
      'Следующий шаг: запустите fillMonblanIiko() для загрузки данных из IIKO.'
    );
  }
}

// ═══════════════════════════════════════════════════════════════
// ИМПОРТ ВСЕХ ДАННЫХ ИЗ ИСТОЧНИКА + ПОСТРОЕНИЕ СТРУКТУРЫ
//
// Запустите ЭТУ функцию — она сделает всё автоматически:
//   1. Находит все недели с 2024 года в исходном файле
//   2. Строит структуру целевого листа
//   3. Копирует все исторические данные
//   4. Продлевает заголовки и формулы до конца листа
// ═══════════════════════════════════════════════════════════════
function importAndBuildMonblan() {
  var SOURCE_SS_ID     = '1p5x1DXhtE9tzXFuMpVf-IOKDXWEJXGzs';
  var TARGET_SS_ID     = '1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI';
  var SOURCE_SHEET_GID = 1883848346;
  var TOTAL_ROWS       = 96;
  var SEARCH_MAX_COLS  = 160;

  // ── 1. Открываем источник ────────────────────────────────────
  // Скрипт должен быть запущен ОТКРЫТОГО файла-источника (не целевого).
  // openById для xlsx не работает — используем getActiveSpreadsheet().
  var sourceSs = SpreadsheetApp.getActiveSpreadsheet();
  Logger.log('Активная таблица: ' + sourceSs.getId() + ' / ' + sourceSs.getName());

  if (sourceSs.getId() === TARGET_SS_ID) {
    SpreadsheetApp.getUi().alert(
      '❌ Скрипт запущен из ЦЕЛЕВОЙ таблицы!\n\n' +
      'Нужно запустить его из ИСХОДНОЙ таблицы.\n\n' +
      'Шаги:\n' +
      '1. Откройте исходную таблицу (с историческими данными)\n' +
      '2. Расширения → Apps Script\n' +
      '3. Создайте два файла: monblan_config.gs и monblan_build.gs\n' +
      '   (вставьте содержимое из текущего редактора)\n' +
      '4. Выберите importAndBuildMonblan → ▶ Выполнить'
    );
    return;
  }

  // Ищем нужный лист по GID
  var sourceSheet = null;
  var allSheets = sourceSs.getSheets();
  for (var si = 0; si < allSheets.length; si++) {
    if (allSheets[si].getSheetId() === SOURCE_SHEET_GID) {
      sourceSheet = allSheets[si];
      break;
    }
  }
  if (!sourceSheet) {
    Logger.log('GID ' + SOURCE_SHEET_GID + ' не найден. Листы: ' +
      allSheets.map(function(s){return s.getName()+'('+s.getSheetId()+')'}).join(', '));
    sourceSheet = allSheets[0];
    Logger.log('Используем первый лист: ' + sourceSheet.getName());
  } else {
    Logger.log('Исходный лист: ' + sourceSheet.getName() + ' (GID ' + SOURCE_SHEET_GID + ')');
  }

  // Открываем целевую таблицу по ID
  var targetSs = SpreadsheetApp.openById(TARGET_SS_ID);
  targetSs.toast('Шаг 1/4: читаем заголовки источника...', 'Монблан', 180);

  // ── 2. Читаем строки «Год» и «Неделя» из B1:..2 ─────────────
  var hdrValues = sourceSheet.getRange(1, 2, 2, SEARCH_MAX_COLS).getValues();
  var yearRow   = hdrValues[0];
  var weekRow   = hdrValues[1];

  Logger.log('Год строка 1 (первые 10): ' + yearRow.slice(0,10).join(', '));
  Logger.log('Неделя строка 2 (первые 10): ' + weekRow.slice(0,10).join(', '));

  // Ищем первый и последний столбец с годом >= 2025
  var firstIdx = -1;
  var lastIdx  = -1;
  for (var i = 0; i < yearRow.length; i++) {
    var yr = Number(yearRow[i]);
    if (yr >= 2025) {
      if (firstIdx === -1) firstIdx = i;
      lastIdx = i;
    }
  }
  if (firstIdx === -1) {
    SpreadsheetApp.getUi().alert(
      '⚠️ Не найдено данных за 2025+ год в строке 1 источника.\n\n' +
      'Первые 5 значений строки 1 (с колонки B): ' + yearRow.slice(0,5).join(', ') + '\n\n' +
      'Проверьте: скрипт запущен из правильной таблицы?'
    );
    return;
  }

  var srcStartColNum = firstIdx + 2;
  var srcEndColNum   = lastIdx  + 2;
  var IMPORT_COLS    = lastIdx - firstIdx + 1;
  var startYear      = Number(yearRow[firstIdx]);
  var startWeek      = Number(weekRow[firstIdx]);

  Logger.log('Импорт: ' + IMPORT_COLS + ' нед. с ' + startYear + '/нед.' + startWeek +
             ' (столбцы ' + colNumToLetter_(srcStartColNum) + '–' + colNumToLetter_(srcEndColNum) + ')');

  // ── 3. Читаем все данные ─────────────────────────────────────
  targetSs.toast('Читаем ' + IMPORT_COLS + ' недель из источника...', 'Монблан', 180);
  var srcData = sourceSheet.getRange(1, srcStartColNum, TOTAL_ROWS, IMPORT_COLS).getValues();

  // Диагностика: проверяем первую колонку данных
  Logger.log('--- Диагностика: первый столбец данных (строки 1-15) ---');
  for (var di = 0; di < 15; di++) {
    Logger.log('  Строка ' + (di+1) + ': ' + srcData[di][0]);
  }

  // Проверяем что строка 4 (Выручка) содержит числа, а не 0
  var revenue4 = Number(srcData[3][0]);
  if (revenue4 === 0) {
    Logger.log('⚠️ Строка 4 (Выручка) в первом столбце = 0. Возможно несовпадение структуры.');
  } else {
    Logger.log('✓ Строка 4 (Выручка) = ' + revenue4);
  }

  // ── 4. Строим структуру целевого листа ───────────────────────
  targetSs.toast('Строим структуру листа...', 'Монблан', 180);
  MB_CONFIG.START_YEAR = startYear;
  MB_CONFIG.START_WEEK = startWeek;
  buildMonblanSheet(true, targetSs);

  // ── 5. Вставляем значения DATA-строк ─────────────────────────
  targetSs.toast('Копируем данные...', 'Монблан', 180);
  var sh = getMonblanSheet_(targetSs);

  var dataRows = [4,5,7,10,12,14,17,19,21,23,25,27,29,
                  31,32,34,36,42,43,44,45,46,
                  61,63,65,68,70,72,
                  75,77,79,81,83,85,
                  91,92,93,94];

  var nonZeroCount = 0;
  for (var ri = 0; ri < dataRows.length; ri++) {
    var rowNum  = dataRows[ri];
    var rowVals = srcData[rowNum - 1];
    sh.getRange(rowNum, 2, 1, IMPORT_COLS).setValues([rowVals]);
    // Считаем ненулевые строки для диагностики
    for (var ci = 0; ci < rowVals.length; ci++) {
      if (rowVals[ci] !== 0 && rowVals[ci] !== '') nonZeroCount++;
    }
  }
  SpreadsheetApp.flush();

  Logger.log('Записано ненулевых ячеек: ' + nonZeroCount + ' из ' + (dataRows.length * IMPORT_COLS));

  // ── 6. Синяя граница после последней импортированной недели ──
  targetSs.toast('Финальное форматирование...', 'Монблан', 60);
  var lastImportCol = 1 + IMPORT_COLS;
  sh.getRange(1, lastImportCol, TOTAL_ROWS, 1)
    .setBorder(null, null, null, true, null, null, '#2d6a9f', SpreadsheetApp.BorderStyle.SOLID_MEDIUM);

  var diagMsg = nonZeroCount === 0
    ? '\n\n⚠️ ВСЕ данные = 0 или пусто. Проверьте логи (Расширения → Apps Script → Выполнения).'
    : '\n\nЗаполнено ячеек: ' + nonZeroCount;

  SpreadsheetApp.getUi().alert(
    '✅ Готово!\n\n' +
    'Скопировано: ' + IMPORT_COLS + ' недель\n' +
    'С ' + startYear + ' нед. ' + startWeek + '\n' +
    'Источник: столбцы ' + colNumToLetter_(srcStartColNum) + '–' + colNumToLetter_(srcEndColNum) + '\n' +
    'Всего столбцов подготовлено: ' + MB_CONFIG.WEEKS_TO_INIT +
    diagMsg
  );
}

// ═══════════════════════════════════════════════════════════════
// ЗАПОЛНЕНИЕ СТРОКИ 3 ДАТАМИ (Пн–Вс каждой недели)
// Читает год (строка 1) и номер недели (строка 2), пишет "DD-DD" в строку 3.
// Ничего кроме строки 3 не трогает.
// ═══════════════════════════════════════════════════════════════
function fillWeekDates() {
  var SHEET_GID = 2051236241;

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = null;
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === SHEET_GID) { sh = sheets[i]; break; }
  }
  if (!sh) sh = ss.getSheetByName('Монблан');
  if (!sh) { SpreadsheetApp.getUi().alert('Лист "Монблан" не найден'); return; }

  var lastCol = sh.getLastColumn();
  var numCols = lastCol - 1;  // столбцы B..lastCol
  if (numCols < 1) return;

  var years = sh.getRange(1, 2, 1, numCols).getValues()[0];
  var weeks = sh.getRange(2, 2, 1, numCols).getValues()[0];

  var dates = [];
  for (var col = 0; col < numCols; col++) {
    var yr = Number(years[col]);
    var wk = Number(weeks[col]);
    dates.push((yr > 0 && wk > 0) ? weekDateRange_(yr, wk) : '');
  }

  sh.getRange(3, 2, 1, numCols).setValues([dates]);
  SpreadsheetApp.getUi().alert('✅ Даты заполнены в строке 3: ' + numCols + ' колонок');
}

// ═══════════════════════════════════════════════════════════════
// ПРОДЛЕНИЕ ФОРМУЛ ИЗ КОЛОНКИ B ДО КОНЦА ЛИСТА
// Запустите из Apps Script целевой таблицы один раз.
// Формулы из pct/calc строк продлеваются, данные (числа) не трогаются.
// ═══════════════════════════════════════════════════════════════
function extendFormulasFromColumnB() {
  var SHEET_GID  = 2051236241;
  var FIRST_ROW  = 4;
  var LAST_ROW   = 96;

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = null;
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === SHEET_GID) { sh = sheets[i]; break; }
  }
  if (!sh) sh = ss.getSheetByName('Монблан');
  if (!sh) { SpreadsheetApp.getUi().alert('Лист "Монблан" не найден'); return; }

  var lastCol  = sh.getLastColumn();
  var numCols  = lastCol - 2;  // сколько столбцов после B (C..lastCol)
  if (numCols < 1) { SpreadsheetApp.getUi().alert('Нет столбцов после B'); return; }

  var numRows  = LAST_ROW - FIRST_ROW + 1;  // 93

  // Читаем формулы из колонки B (строки 4-96)
  var colBFormulas = sh.getRange(FIRST_ROW, 2, numRows, 1).getFormulas();

  var written = 0;
  for (var i = 0; i < numRows; i++) {
    var formula = colBFormulas[i][0];
    if (!formula) continue;  // нет формулы — строка с данными, пропускаем

    // Копируем ровно эту строку из B в C..lastCol (формулы сдвигаются автоматически)
    var srcRow = sh.getRange(FIRST_ROW + i, 2, 1, 1);
    var dstRow = sh.getRange(FIRST_ROW + i, 3, 1, numCols);
    srcRow.copyTo(dstRow, SpreadsheetApp.CopyPasteType.PASTE_FORMULA, false);
    written++;
  }

  SpreadsheetApp.getUi().alert('✅ Готово! Продлено строк с формулами: ' + written);
}

// ═══════════════════════════════════════════════════════════════
// ПОИСК ЛИСТА ТРЕКИНГА
// ═══════════════════════════════════════════════════════════════
function getMonblanSheet_(ss) {
  // Сначала ищем по GID
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === MB_CONFIG.TRACKING_SHEET_GID) {
      return sheets[i];
    }
  }
  // Запасной поиск по имени
  var byName = ss.getSheetByName(MB_CONFIG.TRACKING_SHEET_NAME);
  if (byName) return byName;

  // Создаём новый лист, если не нашли
  return ss.insertSheet(MB_CONFIG.TRACKING_SHEET_NAME);
}

// ═══════════════════════════════════════════════════════════════
// ШАГ 3 — СТРОКИ ЗАГОЛОВКА (Год / Неделя / Дата)
// ═══════════════════════════════════════════════════════════════
function buildHeaders_(sh) {
  var firstDataCol = 2;
  var weeksCount   = MB_CONFIG.WEEKS_TO_INIT;

  // Высоты заголовочных строк
  sh.setRowHeight(1, 24);  // Год
  sh.setRowHeight(2, 24);  // Неделя
  sh.setRowHeight(3, 28);  // Дата

  // Метки в столбце A для строк 1-3
  var hdrA = sh.getRange(1, 1, 3, 1);
  hdrA.setValues([['Год'], ['Неделя'], [MB_CONFIG.CAFE_NAME]]);
  hdrA.setBackground(MB_C.colABg);
  hdrA.setFontWeight('bold');
  hdrA.setFontSize(9);

  // Заполняем заголовки для каждой недели
  var yearRow  = [];
  var weekRow  = [];
  var dateRow  = [];

  var curYear = MB_CONFIG.START_YEAR;
  var curWeek = MB_CONFIG.START_WEEK;

  for (var i = 0; i < weeksCount; i++) {
    yearRow.push(curYear);
    weekRow.push(curWeek);
    dateRow.push(weekDateRange_(curYear, curWeek));

    // Переходим к следующей неделе
    var weeksInYear = isoWeeksInYear_(curYear);
    curWeek++;
    if (curWeek > weeksInYear) {
      curWeek = 1;
      curYear++;
    }
  }

  // Записываем одним вызовом
  var rng1 = sh.getRange(1, firstDataCol, 1, weeksCount);
  var rng2 = sh.getRange(2, firstDataCol, 1, weeksCount);
  var rng3 = sh.getRange(3, firstDataCol, 1, weeksCount);

  rng1.setValues([yearRow]);
  rng2.setValues([weekRow]);
  rng3.setValues([dateRow]);

  // Форматирование
  rng1.setBackground(MB_C.yearBg).setFontColor(MB_C.yearText).setFontWeight('bold').setFontSize(9).setHorizontalAlignment('center');
  rng2.setBackground(MB_C.weekBg).setFontColor(MB_C.weekText).setFontWeight('bold').setFontSize(9).setHorizontalAlignment('center');
  rng3.setBackground(MB_C.dateBg).setFontColor(MB_C.dateText).setFontSize(8).setHorizontalAlignment('center');

  // Выделяем переходы года (первая неделя каждого года жирной рамкой)
  curYear = MB_CONFIG.START_YEAR;
  curWeek = MB_CONFIG.START_WEEK;
  for (var j = 0; j < weeksCount; j++) {
    if (curWeek === 1) {
      var colIdx = firstDataCol + j;
      sh.getRange(1, colIdx, 3, 1).setBorder(null, true, null, null, null, null, '#ffffff', SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
    }
    var weeksInYearJ = isoWeeksInYear_(curYear);
    curWeek++;
    if (curWeek > weeksInYearJ) { curWeek = 1; curYear++; }
  }
}

// ═══════════════════════════════════════════════════════════════
// ШАГ 4 — СТОЛБЕЦ A + СТОЛБЕЦ B (эталон форматов)
//
// Стратегия: форматируем только столбец B (93 ячейки, строки 4-96).
// applyNumberFormats_ затем копирует его во все остальные недели
// одним вызовом copyTo(PASTE_FORMAT) — нативная операция Sheets.
// Строки 1-3 форматирует buildHeaders_.
// ═══════════════════════════════════════════════════════════════
function buildColumnA_(sh) {
  var firstDataCol = 2;
  var i, def, r, bg, fg, wg;

  // ── 1. Метки столбца A (все 96 строк, 1 вызов) ───────────────
  var labels = [];
  for (i = 0; i < MB_ROWS.length; i++) labels.push([MB_ROWS[i].label]);
  sh.getRange(1, 1, 96, 1).setValues(labels);
  sh.getRange(1, 1, 96, 1)
    .setBackground(MB_C.colABg).setFontSize(9).setWrap(true)
    .setVerticalAlignment('middle').setFontColor('#333333');

  // ── 2. Цвета для ВСЕХ столбцов данных (93×weeksCount матрица) ──
  // Пишем сразу все столбцы — без copyTo, который очень медленный
  var bgMatrix = [], fgMatrix = [], wgMatrix = [];
  for (i = 0; i < MB_ROWS.length; i++) {
    def = MB_ROWS[i]; r = def.r;
    if (r < 4) continue;
    switch (def.type) {
      case 'section': bg = MB_C.sectionBg; fg = MB_C.sectionText; wg = 'bold';   break;
      case 'pct':     bg = MB_C.pctBg;     fg = MB_C.pctText;     wg = 'normal'; break;
      case 'calc':    bg = MB_C.formulaBg; fg = MB_C.formulaText; wg = 'normal'; break;
      case 'static':  bg = MB_C.staticBg;  fg = MB_C.staticText;  wg = 'normal'; break;
      case 'empty':   bg = MB_C.white;     fg = MB_C.white;       wg = 'normal'; break;
      default:
        bg = (r % 2 === 0) ? MB_C.dataBgAlt : MB_C.dataBg;
        fg = MB_C.dataText; wg = 'normal'; break;
    }
    var bgRow = [], fgRow = [], wgRow = [];
    for (var col = 0; col < MB_CONFIG.WEEKS_TO_INIT; col++) {
      bgRow.push(bg); fgRow.push(fg); wgRow.push(wg);
    }
    bgMatrix.push(bgRow); fgMatrix.push(fgRow); wgMatrix.push(wgRow);
  }
  var dataRng = sh.getRange(4, firstDataCol, 93, MB_CONFIG.WEEKS_TO_INIT);
  dataRng.setBackgrounds(bgMatrix);
  dataRng.setFontColors(fgMatrix);
  dataRng.setFontWeights(wgMatrix);
  dataRng.setFontSize(9);

  // ── 3. Высоты строк ──────────────────────────────────────────
  sh.setRowHeights(1, 96, 22);
  sh.setRowHeight(1, 24); sh.setRowHeight(2, 24); sh.setRowHeight(3, 28);
  for (i = 0; i < MB_ROWS.length; i++) {
    def = MB_ROWS[i];
    if (def.type === 'pct')   sh.setRowHeight(def.r, 18);
    if (def.type === 'empty') sh.setRowHeight(def.r, 8);
  }

  // ── 4. Жирный шрифт в столбце A для section-строк ────────────
  for (i = 0; i < MB_ROWS.length; i++) {
    if (MB_ROWS[i].type === 'section') sh.getRange(MB_ROWS[i].r, 1).setFontWeight('bold');
  }
}

// ═══════════════════════════════════════════════════════════════
// ШАГ 5 — ФОРМУЛЫ ДЛЯ ВСЕХ СТОЛБЦОВ ДАННЫХ
// Строим полную матрицу 93×weeksCount и пишем одним setFormulas.
// Избегаем copyTo — он медленный на больших диапазонах.
// ═══════════════════════════════════════════════════════════════
function buildFormulas_(sh) {
  var firstDataCol = 2;
  var weeksCount   = MB_CONFIG.WEEKS_TO_INIT;
  var i, def, col;

  // Предвычисляем буквы столбцов один раз
  var colLetters = [];
  for (col = 0; col < weeksCount; col++) {
    colLetters.push(colNumToLetter_(firstDataCol + col));
  }

  // Строим полную матрицу 93×weeksCount
  var allFormulas = [];
  for (i = 0; i < MB_ROWS.length; i++) {
    def = MB_ROWS[i];
    if (def.r < 4) continue;
    var row = [];
    if (def.type === 'pct' || def.type === 'calc') {
      for (col = 0; col < weeksCount; col++) {
        row.push(buildFormulaStr_(colLetters[col], def));
      }
    } else {
      for (col = 0; col < weeksCount; col++) row.push('');
    }
    allFormulas.push(row);
  }

  sh.getRange(4, firstDataCol, 93, weeksCount).setFormulas(allFormulas);
}

// ═══════════════════════════════════════════════════════════════
// ШАГ 6 — СТАТИЧНЫЕ ЗНАЧЕНИЯ (Столов=90, Мест=90)
// ═══════════════════════════════════════════════════════════════
function buildStaticValues_(sh) {
  var firstDataCol = 2;
  var weeksCount   = MB_CONFIG.WEEKS_TO_INIT;

  for (var i = 0; i < MB_ROWS.length; i++) {
    var def = MB_ROWS[i];
    if (def.type === 'static') {
      var staticRow = [];
      for (var j = 0; j < weeksCount; j++) staticRow.push(def.value);
      sh.getRange(def.r, firstDataCol, 1, weeksCount).setValues([staticRow]);
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// ШАГ 7 — ЧИСЛОВЫЕ ФОРМАТЫ
// Строим полную матрицу 93×weeksCount и пишем одним setNumberFormats.
// Избегаем copyTo — он медленный на больших диапазонах.
// ═══════════════════════════════════════════════════════════════
function applyNumberFormats_(sh) {
  var firstDataCol = 2;
  var weeksCount   = MB_CONFIG.WEEKS_TO_INIT;

  var pctSet   = {6:1,8:1,11:1,13:1,15:1,18:1,20:1,22:1,24:1,26:1,28:1,30:1,
                  33:1,35:1,37:1,62:1,64:1,66:1,67:1,69:1,71:1,73:1,76:1,78:1,80:1,82:1,84:1,86:1};
  var rubleSet = {4:1,5:1,7:1,10:1,12:1,14:1,16:1,17:1,19:1,21:1,23:1,25:1,27:1,29:1,
                  38:1,39:1,40:1,41:1,47:1,48:1,49:1,50:1,
                  61:1,63:1,65:1,75:1,77:1,79:1,81:1,83:1,85:1,93:1,95:1,96:1};
  var countSet = {31:1,32:1,34:1,36:1,42:1,43:1,44:1,45:1,46:1,
                  51:1,52:1,53:1,54:1,55:1,56:1,57:1,58:1,59:1,
                  68:1,70:1,72:1,87:1,88:1,91:1,92:1,94:1};

  var i, rNum, fmt, col;
  var allFormats = [];
  for (i = 0; i < MB_ROWS.length; i++) {
    rNum = MB_ROWS[i].r;
    if (rNum < 4) continue;
    if      (pctSet[rNum])   fmt = '0%';
    else if (rubleSet[rNum]) fmt = '# ##0';
    else if (countSet[rNum]) fmt = '0.##';
    else                     fmt = 'General';
    var row = [];
    for (col = 0; col < weeksCount; col++) row.push(fmt);
    allFormats.push(row);
  }

  sh.getRange(4, firstDataCol, 93, weeksCount).setNumberFormats(allFormats);
}

// ═══════════════════════════════════════════════════════════════
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ═══════════════════════════════════════════════════════════════

/**
 * Строит строку формулы для данной колонки и определения строки
 */
function buildFormulaStr_(c, def) {
  if (def.type === 'pct') {
    // Простой процент: num / den
    return '=IFERROR(' + c + def.formula.num + '/' + c + def.formula.den + ',"")';
  }

  // Расчётные строки (calc)
  var f = def.formula;
  switch (f.type) {
    case 'div':
      // Деление двух строк: num / den
      return '=IFERROR(' + c + f.num + '/' + c + f.den + ',"")';

    case 'div7':
      // Среднее за 7 дней: num / 7
      return '=IFERROR(' + c + f.num + '/7,"")';

    case 'turn_total':
      // Оборачиваемость за неделю: чеки / столы / 7 дней
      return '=IFERROR(' + c + f.checks + '/' + c + f.cap + '/7,"")';

    case 'turn_slot':
      // Оборачиваемость за слот (утро/день/вечер): чеки / столы
      return '=IFERROR(' + c + f.checks + '/' + c + f.cap + ',"")';

    case 'loyalty':
      // Коэффициент групповой лояльности: (выручка 2 + выручка 3+) / общая выручка
      return '=IFERROR((' + c + '63+' + c + '65)/' + c + '4,"")';

    default:
      return '';
  }
}

/**
 * Преобразует номер столбца (1-based) в буквенное обозначение A, B, ..., Z, AA, AB, ...
 */
function colNumToLetter_(n) {
  var s = '';
  while (n > 0) {
    var rem = (n - 1) % 26;
    s = String.fromCharCode(65 + rem) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

/**
 * Возвращает диапазон дат ISO-недели в формате "DD-DD"
 * Пример: неделя 48 2024 = "25-01" (ноября 25 — декабря 1)
 */
function weekDateRange_(year, isoWeek) {
  // Понедельник ISO-недели
  var jan4    = new Date(year, 0, 4);
  var dayJan4 = jan4.getDay() || 7;           // 1=Пн ... 7=Вс
  var monday  = new Date(jan4.getTime() - (dayJan4 - 1) * 86400000 + (isoWeek - 1) * 7 * 86400000);
  var sunday  = new Date(monday.getTime() + 6 * 86400000);

  var pad = function(n) { return n < 10 ? '0' + n : '' + n; };
  return pad(monday.getDate()) + '-' + pad(sunday.getDate());
}

/**
 * Количество ISO-недель в году (52 или 53)
 */
function isoWeeksInYear_(year) {
  // Год имеет 53 недели, если 1 января — четверг,
  // или если это високосный год и 1 января — среда
  var jan1  = new Date(year, 0, 1).getDay() || 7;  // 1=Пн...7=Вс
  var dec31 = new Date(year, 11, 31).getDay() || 7;
  return (jan1 === 4 || dec31 === 4) ? 53 : 52;
}
