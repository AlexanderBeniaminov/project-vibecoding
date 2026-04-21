/**
 * МОНБЛАН — ДАШБОРД: ВСЕ ОТКЛОНЕНИЯ + AI-АНАЛИЗ
 *
 * Показывает ВСЕ метрики листа «Монблан» у которых есть отклонение:
 *   🔴 падение > 10%  |  🟡 падение 3–10%  |  🟢 рост > 5%
 *   ⚪ норма (−3% … +5%) — НЕ показывается.
 *
 * Если у недели 3 отклонения — показывает 3 строки.
 * Если 25 — показывает 25. Структура динамическая.
 *
 * Структура дашборда:
 *   Строка 1 — заголовок
 *   Строка 2 — B2: выбор недели (1–5)
 *   Строка 3 — шапка таблицы (Показатель | 2025 | 2026 | Δ% | ●)
 *   Строки 4+ — динамические строки отклонений (количество = факт)
 *   +2 строки отступ
 *   AI-блок: Причины / Рекомендации / Выводы
 *
 * Установка:
 *   1. Вставьте этот файл в Apps Script таблицы
 *   2. Выберите функцию installTrigger → запустите (один раз)
 *   3. Меню «🔶 Монблан» → «Обновить дашборд» — для первого заполнения
 */

var DASH_GID    = 1669207980;
var DASH_NAME   = 'Дашборд';
var MONBLAN_GID = 2051236241;  // лист «Монблан» (он же «Еженедельно»)

// ── Пороги отклонений ────────────────────────────────────────
var T_RED    = -0.10;  // 🔴 падение > 10%
var T_YELLOW = -0.03;  // 🟡 падение 3–10%
var T_GREEN  =  0.05;  // 🟢 рост > 5%

// ── Строки с процентным форматом в листе Монблан ─────────────
var PCT_ROWS_MB = {
  6:1, 8:1, 11:1, 13:1, 15:1, 18:1, 20:1, 22:1, 24:1, 26:1, 28:1, 30:1,
  33:1, 35:1, 37:1, 62:1, 64:1, 66:1, 69:1, 71:1, 73:1,
  76:1, 78:1, 80:1, 82:1, 84:1, 86:1
};

// ── Фиксированные строки дашборда ────────────────────────────
var R_TITLE = 1;
var R_SEL   = 2;   // B2 — выбор недели
var R_HDR   = 3;   // шапка колонок
var R_DATA  = 4;   // первая строка данных (количество динамическое)


// ═══════════════════════════════════════════════════════════════
// УСТАНОВКА ТРИГГЕРА — запустите один раз
// ═══════════════════════════════════════════════════════════════
function installTrigger() {
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === 'onEditDashboard') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('onEditDashboard')
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onEdit()
    .create();
  SpreadsheetApp.getUi().alert('✅ Триггер установлен!\nТеперь при смене недели в B2 дашборд обновляется автоматически.');
}


// ═══════════════════════════════════════════════════════════════
// КАСТОМНОЕ МЕНЮ
// ═══════════════════════════════════════════════════════════════
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('🔶 Монблан')
    .addItem('Обновить дашборд',   'refreshDashboard')
    .addItem('Обновить AI-анализ', 'runAiAnalysis')
    .addSeparator()
    .addItem('Установить триггер onEdit', 'installTrigger')
    .addToUi();
}


// ═══════════════════════════════════════════════════════════════
// ONEIT-ТРИГГЕР — срабатывает при изменении B2
// ═══════════════════════════════════════════════════════════════
function onEditDashboard(e) {
  if (!e) return;
  var rng = e.range;
  if (rng.getSheet().getSheetId() !== DASH_GID) return;
  if (rng.getRow() !== R_SEL || rng.getColumn() !== 2) return;
  Utilities.sleep(300);
  refreshDashboard();
}


// ═══════════════════════════════════════════════════════════════
// ГЛАВНАЯ ФУНКЦИЯ — обновить дашборд
// ═══════════════════════════════════════════════════════════════
function refreshDashboard() {
  var ss   = SpreadsheetApp.getActiveSpreadsheet();
  var dash = getDashSheet_(ss);
  var mb   = getMonblanSheet_(ss);

  if (!dash) { SpreadsheetApp.getUi().alert('Лист «Дашборд» не найден (GID=' + DASH_GID + ')'); return; }
  if (!mb)   { SpreadsheetApp.getUi().alert('Лист «Монблан» не найден (GID=' + MONBLAN_GID + ')'); return; }

  // Написать статичные заголовки (строки 1–3) если их нет
  writeStaticHeaders_(dash);

  var week = parseInt(dash.getRange(R_SEL, 2).getValue());
  if (!week || isNaN(week) || week < 1 || week > 5) {
    clearDataRows_(dash);
    dash.getRange(R_DATA, 1).setValue('⚠️ Выберите неделю в ячейке B2 (1–5)');
    return;
  }

  ss.toast('Читаем данные Монблан...', '🔶 Монблан', 30);

  // Найти столбцы года/недели
  var col25 = findWeekCol_(mb, 2025, week);
  var col26 = findWeekCol_(mb, 2026, week);

  // Посчитать все отклонения
  var deviations = getDeviations_(mb, col25, col26);

  // Очистить старые строки данных
  clearDataRows_(dash);

  if (deviations.length === 0) {
    dash.getRange(R_DATA, 1, 1, 5).merge()
      .setValue('✅ Все показатели недели ' + week + ' в норме — отклонений нет')
      .setBackground('#d9ead3').setFontWeight('bold');
    saveAiStartRow_(R_DATA + 4);
    ss.toast('✅ Отклонений нет — неделя ' + week, '🔶 Монблан', 5);
    return;
  }

  // Записать строки отклонений
  writeDeviationRows_(dash, deviations);

  // Записать блок «Сигналы недели» (🔴🟡🟢)
  var signalsEnd = writeSignalsSection_(dash, R_DATA + deviations.length + 2, deviations);

  // Сохранить строку начала AI-блока
  var aiRow = signalsEnd + 2;
  saveAiStartRow_(aiRow);

  ss.toast('✅ ' + deviations.length + ' отклонений — неделя ' + week, '🔶 Монблан', 5);
}


// ═══════════════════════════════════════════════════════════════
// ПОИСК СТОЛБЦА ГОДА/НЕДЕЛИ В ЛИСТЕ МОНБЛАН
// Строка 1 = год, строка 2 = номер недели
// ═══════════════════════════════════════════════════════════════
function findWeekCol_(sh, year, week) {
  var lastCol = sh.getLastColumn();
  if (lastCol < 2) return null;
  var yearRow = sh.getRange(1, 1, 1, lastCol).getValues()[0];
  var weekRow = sh.getRange(2, 1, 1, lastCol).getValues()[0];
  for (var i = 1; i < yearRow.length; i++) {
    if (parseInt(yearRow[i]) === year && parseInt(weekRow[i]) === week) {
      return i + 1;  // 1-based
    }
  }
  return null;
}


// ═══════════════════════════════════════════════════════════════
// ЧТЕНИЕ МЕТРИК И РАСЧЁТ ДЕЛЬТ
// Возвращает только строки с отклонением (не ⚪)
// ═══════════════════════════════════════════════════════════════
function getDeviations_(sh, col25, col26) {
  var N      = 96;
  var labels = sh.getRange(1, 1, N, 1).getValues();
  var vals25 = col25 ? sh.getRange(1, col25, N, 1).getValues() : null;
  var vals26 = col26 ? sh.getRange(1, col26, N, 1).getValues() : null;

  var result = [];
  for (var i = 3; i < N; i++) {  // строки 4–96 (0-based: 3–95)
    var label = String(labels[i][0] || '').trim();
    if (!label) continue;

    var v25 = vals25 ? (parseFloat(vals25[i][0]) || 0) : 0;
    var v26 = vals26 ? (parseFloat(vals26[i][0]) || 0) : 0;

    // Нет данных ни за один год — пропускаем
    if (v25 === 0 && v26 === 0) continue;

    // Дельта: (2026 − 2025) / |2025|
    if (v25 === 0) continue;  // нет базы для сравнения
    var delta = (v26 - v25) / Math.abs(v25);

    // Норма ⚪: −3% < delta ≤ +5% — не показываем
    if (delta > T_YELLOW && delta <= T_GREEN) continue;

    result.push({
      label: label,
      v2025: v25,
      v2026: v26,
      delta: delta,
      isPct: !!PCT_ROWS_MB[i + 1],  // i+1 = 1-based row number
    });
  }
  return result;
}


// ═══════════════════════════════════════════════════════════════
// ЗАПИСЬ СТРОК ОТКЛОНЕНИЙ
// ═══════════════════════════════════════════════════════════════
function writeDeviationRows_(dash, deviations) {
  var values = deviations.map(function(d) {
    var sign     = d.delta > 0 ? '+' : '';
    var deltaStr = sign + Math.round(d.delta * 1000) / 10 + '%';
    return [
      d.label,
      formatValue_(d.v2025, d.isPct),
      formatValue_(d.v2026, d.isPct),
      deltaStr,
      getSignal_(d.delta),
    ];
  });

  var dataRange = dash.getRange(R_DATA, 1, values.length, 5);
  dataRange.setValues(values);
  dataRange.setFontSize(9);
  dataRange.setVerticalAlignment('middle');

  // Форматирование по строкам
  for (var i = 0; i < deviations.length; i++) {
    var row    = R_DATA + i;
    var delta  = deviations[i].delta;
    var bg     = getBgColor_(delta);

    // Фон строки
    if (bg) dash.getRange(row, 1, 1, 5).setBackground(bg);

    // Выравнивание
    dash.getRange(row, 1).setHorizontalAlignment('left');
    dash.getRange(row, 2, 1, 2).setHorizontalAlignment('right');
    dash.getRange(row, 4, 1, 2).setHorizontalAlignment('center');

    // Чередование оттенка для читаемости
    if (!bg) {
      var altBg = (i % 2 === 0) ? '#ffffff' : '#f8f9fa';
      dash.getRange(row, 1, 1, 5).setBackground(altBg);
    }
  }
}


// ═══════════════════════════════════════════════════════════════
// СТАТИЧНЫЕ ЗАГОЛОВКИ (строки 1–3)
// Пишутся только если ещё не заполнены
// ═══════════════════════════════════════════════════════════════
function writeStaticHeaders_(dash) {
  if (dash.getRange(R_TITLE, 1).getValue() === 'ДАШБОРД — МОНБЛАН') return;

  // Строка 1 — заголовок
  dash.getRange(R_TITLE, 1, 1, 5).merge()
    .setValue('ДАШБОРД — МОНБЛАН')
    .setBackground('#1a3a5c')
    .setFontColor('#ffffff')
    .setFontWeight('bold')
    .setFontSize(13)
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle');

  // Строка 2 — выбор недели
  dash.getRange(R_SEL, 1).setValue('Выберите неделю 2026 (1–5):')
    .setFontWeight('bold').setBackground('#f0f0f0');
  dash.getRange(R_SEL, 2).setValue(1)
    .setBackground('#f0f0f0').setHorizontalAlignment('center');
  dash.getRange(R_SEL, 3, 1, 3).setBackground('#f0f0f0');

  // Dropdown 1–5 на B2
  var rule = SpreadsheetApp.newDataValidation()
    .requireValueInList(['1','2','3','4','5'], true)
    .build();
  dash.getRange(R_SEL, 2).setDataValidation(rule);

  // Строка 3 — шапка таблицы
  var hdr = dash.getRange(R_HDR, 1, 1, 5);
  hdr.setValues([['Показатель', '2025', '2026', 'Δ%', '●']]);
  hdr.setBackground('#2d6a9f')
    .setFontColor('#ffffff')
    .setFontWeight('bold')
    .setFontSize(9)
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle');
  dash.getRange(R_HDR, 1).setHorizontalAlignment('left');

  // Заморозить строки 1–3
  dash.setFrozenRows(3);

  // Ширины колонок
  dash.setColumnWidth(1, 250);
  dash.setColumnWidth(2, 120);
  dash.setColumnWidth(3, 120);
  dash.setColumnWidth(4, 80);
  dash.setColumnWidth(5, 50);
}


// ═══════════════════════════════════════════════════════════════
// БЛОК «СИГНАЛЫ НЕДЕЛИ» — группировка отклонений по цветам
// Пишется сразу после таблицы отклонений
// ═══════════════════════════════════════════════════════════════
function writeSignalsSection_(dash, startRow, deviations) {
  var red    = deviations.filter(function(d) { return d.delta < T_RED; });
  var yellow = deviations.filter(function(d) { return d.delta >= T_RED && d.delta < T_YELLOW; });
  var green  = deviations.filter(function(d) { return d.delta > T_GREEN; });

  var row = startRow;

  function writeHeader(text, bg, fg) {
    dash.getRange(row, 1, 1, 5).merge()
      .setValue(text)
      .setBackground(bg)
      .setFontColor(fg || '#ffffff')
      .setFontWeight('bold')
      .setFontSize(9)
      .setHorizontalAlignment('left')
      .setVerticalAlignment('middle');
    row++;
  }

  function writeItems(items, bg) {
    if (items.length === 0) {
      dash.getRange(row, 1, 1, 5).merge()
        .setValue('—')
        .setBackground(bg)
        .setFontSize(9)
        .setVerticalAlignment('middle');
      row++;
    } else {
      items.forEach(function(d) {
        dash.getRange(row, 1, 1, 5).merge()
          .setValue(d.label)
          .setBackground(bg)
          .setFontSize(9)
          .setVerticalAlignment('middle');
        row++;
      });
    }
  }

  // Заголовок секции
  writeHeader('🚨  СИГНАЛЫ НЕДЕЛИ', '#333333');

  // 🔴 Проблемные зоны
  writeHeader('🔴  ПРОБЛЕМНЫЕ ЗОНЫ  (отклонение > −10%)', '#b43232');
  writeItems(red, '#ffcccc');

  // 🟡 Требуют внимания
  writeHeader('🟡  ТРЕБУЮТ ВНИМАНИЯ  (−10% до −3%)', '#997800');
  writeItems(yellow, '#fff2cc');

  // 🟢 Работает хорошо
  writeHeader('🟢  РАБОТАЕТ ХОРОШО  (рост > +5%)', '#19622a');
  writeItems(green, '#d9ead3');

  return row;  // возвращаем следующую свободную строку
}


// ═══════════════════════════════════════════════════════════════
// ОЧИСТКА ДИНАМИЧЕСКОЙ ЗОНЫ (строки 4 и ниже)
// ═══════════════════════════════════════════════════════════════
function clearDataRows_(dash) {
  var lastRow = dash.getLastRow();
  if (lastRow < R_DATA) return;
  var numRows = lastRow - R_DATA + 1;
  var zone = dash.getRange(R_DATA, 1, numRows, 5);
  zone.clearContent();
  zone.clearFormat();
  zone.breakApart();
}


// ═══════════════════════════════════════════════════════════════
// AI-АНАЛИЗ (Groq API — бесплатно)
// ═══════════════════════════════════════════════════════════════
function runAiAnalysis() {
  var ss   = SpreadsheetApp.getActiveSpreadsheet();
  var dash = getDashSheet_(ss);
  var mb   = getMonblanSheet_(ss);
  if (!dash || !mb) return;

  var week = parseInt(dash.getRange(R_SEL, 2).getValue());
  if (!week || isNaN(week)) {
    SpreadsheetApp.getUi().alert('Выберите неделю в B2');
    return;
  }

  // Читаем отклонения напрямую из Монблан
  var col25      = findWeekCol_(mb, 2025, week);
  var col26      = findWeekCol_(mb, 2026, week);
  var deviations = getDeviations_(mb, col25, col26);

  if (!deviations.length) {
    SpreadsheetApp.getUi().alert('Нет отклонений для анализа.\nСначала нажмите «Обновить дашборд».');
    return;
  }

  ss.toast('Запрашиваем AI (Groq)...', '🔶 Монблан', 120);

  var red    = deviations.filter(function(d) { return d.delta < T_RED; });
  var yellow = deviations.filter(function(d) { return d.delta >= T_RED && d.delta < T_YELLOW; });
  var green  = deviations.filter(function(d) { return d.delta > T_GREEN; });

  var aiText = callGroq_(buildPrompt_(week, red, yellow, green));

  if (!aiText) {
    SpreadsheetApp.getUi().alert(
      'Ошибка Groq API.\n\n' +
      'Проверьте GROQ_API_KEY:\n' +
      'Настройки проекта → Свойства скрипта → GROQ_API_KEY\n\n' +
      'Получить бесплатный ключ: console.groq.com'
    );
    return;
  }

  var aiRow = getAiStartRow_() || (R_DATA + deviations.length + 2);
  writeAiBlock_(dash, aiRow, week, aiText);
  ss.toast('✅ AI-анализ готов', '🔶 Монблан', 5);
}


// ═══════════════════════════════════════════════════════════════
// ЗАПИСЬ AI-БЛОКА (3 секции × 3 строки)
// ═══════════════════════════════════════════════════════════════
function writeAiBlock_(dash, startRow, week, aiText) {
  var blocks = parseAiBlocks_(aiText);

  // Сначала очистить зону AI-блока
  var aiZone = dash.getRange(startRow, 1, 15, 5);
  aiZone.clearContent().clearFormat().breakApart();

  function writeSection(headerRow, headerText, items) {
    // Заголовок секции
    dash.getRange(headerRow, 1, 1, 5).merge()
      .setValue(headerText)
      .setBackground('#3d3d3d')
      .setFontColor('#ffffff')
      .setFontWeight('bold')
      .setFontSize(9)
      .setVerticalAlignment('middle');

    // 3 строки содержимого
    for (var i = 0; i < 3; i++) {
      dash.getRange(headerRow + 1 + i, 1, 1, 5).merge()
        .setValue(items[i] || '—')
        .setBackground('#f8f9fa')
        .setFontColor('#212529')
        .setFontSize(9)
        .setWrap(true)
        .setVerticalAlignment('middle');
    }
  }

  writeSection(startRow,      '🔍  ВОЗМОЖНЫЕ ПРИЧИНЫ  (AI-анализ — неделя ' + week + ')', blocks.causes);
  writeSection(startRow + 5,  '💡  РЕКОМЕНДАЦИИ  (AI)', blocks.recs);
  writeSection(startRow + 10, '📋  УПРАВЛЕНЧЕСКИЕ ВЫВОДЫ  (AI)', blocks.mgmt);
}


// ═══════════════════════════════════════════════════════════════
// ЗАПРОС К GROQ API
// ═══════════════════════════════════════════════════════════════
function callGroq_(prompt) {
  var key = PropertiesService.getScriptProperties().getProperty('GROQ_API_KEY');
  if (!key) return null;
  try {
    var resp = UrlFetchApp.fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'post',
      muteHttpExceptions: true,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + key,
      },
      payload: JSON.stringify({
        model:      'llama-3.3-70b-versatile',
        max_tokens: 800,
        messages:   [{ role: 'user', content: prompt }],
      }),
    });
    if (resp.getResponseCode() !== 200) {
      Logger.log('Groq ' + resp.getResponseCode() + ': ' + resp.getContentText());
      return null;
    }
    return JSON.parse(resp.getContentText()).choices[0].message.content;
  } catch (e) {
    Logger.log('Groq error: ' + e.message);
    return null;
  }
}

function buildPrompt_(week, red, yellow, green) {
  function fmtList(arr) {
    if (!arr.length) return '—';
    return arr.map(function(d) {
      var sign = d.delta > 0 ? '+' : '';
      return '• ' + d.label + ': ' + sign + Math.round(d.delta * 100) + '%' +
             ' (2025: ' + fmtNum_(d.v2025) + ', 2026: ' + fmtNum_(d.v2026) + ')';
    }).join('\n');
  }
  return 'Ты — аналитик ресторанного бизнеса. Ресторан «Монблан», горнолыжный курорт Губаха.\n\n' +
    'Неделя ' + week + ' / 2026 vs неделя ' + week + ' / 2025:\n\n' +
    '🔴 УПАЛИ > 10%:\n' + fmtList(red) + '\n\n' +
    '🟡 УПАЛИ 3–10%:\n' + fmtList(yellow) + '\n\n' +
    '🟢 ВЫРОСЛИ > 5%:\n' + fmtList(green) + '\n\n' +
    'Дай СТРОГО 3 блока по 3 пункта. Каждый пункт — одно предложение (макс 15 слов). Без вступлений.\n\n' +
    'БЛОК 1: ВОЗМОЖНЫЕ ПРИЧИНЫ ПРОБЛЕМ\n1. ...\n2. ...\n3. ...\n\n' +
    'БЛОК 2: РЕКОМЕНДАЦИИ\n1. ...\n2. ...\n3. ...\n\n' +
    'БЛОК 3: УПРАВЛЕНЧЕСКИЕ ВЫВОДЫ\n1. ...\n2. ...\n3. ...';
}

function parseAiBlocks_(text) {
  function extractItems(blockText) {
    var items = [];
    (blockText || '').split('\n').forEach(function(l) {
      l = l.trim();
      var m = l.match(/^[1-3][\.\)]\s*(.+)/) || l.match(/^[•\-\*]\s*(.+)/);
      if (m) { items.push(m[1]); return; }
      if (l.length > 5 && !/^(БЛОК|BLOCK|ВОЗМОЖНЫЕ|РЕКОМЕНДАЦИИ|УПРАВЛЕНЧЕСКИЕ)/i.test(l)) items.push(l);
    });
    return items.slice(0, 3);
  }
  var parts = text.split(/БЛОК\s*[123][\:\.]?\s*/i);
  if (parts.length >= 4) {
    return { causes: extractItems(parts[1]), recs: extractItems(parts[2]), mgmt: extractItems(parts[3]) };
  }
  var third = Math.floor(text.length / 3);
  return {
    causes: extractItems(text.slice(0, third)),
    recs:   extractItems(text.slice(third, 2 * third)),
    mgmt:   extractItems(text.slice(2 * third)),
  };
}


// ═══════════════════════════════════════════════════════════════
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ═══════════════════════════════════════════════════════════════
function getSignal_(delta) {
  if (delta < T_RED)    return '🔴';
  if (delta < T_YELLOW) return '🟡';
  if (delta > T_GREEN)  return '🟢';
  return '⚪';
}

function getBgColor_(delta) {
  if (delta < T_RED)    return '#ffcccc';
  if (delta < T_YELLOW) return '#fff2cc';
  if (delta > T_GREEN)  return '#d9ead3';
  return null;
}

function formatValue_(v, isPct) {
  if (isPct) return Math.round(v * 1000) / 10 + '%';
  if (!v) return '0';
  // Форматируем число с пробелами (1 234 567)
  return Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

function fmtNum_(v) {
  return Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

function saveAiStartRow_(row) {
  PropertiesService.getScriptProperties().setProperty('AI_START_ROW', String(row));
}

function getAiStartRow_() {
  var v = PropertiesService.getScriptProperties().getProperty('AI_START_ROW');
  return v ? parseInt(v) : null;
}

function getDashSheet_(ss) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === DASH_GID) return sheets[i];
  }
  return ss.getSheetByName(DASH_NAME);
}

function getMonblanSheet_(ss) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === MONBLAN_GID) return sheets[i];
  }
  return ss.getSheetByName('Монблан') || ss.getSheetByName('Еженедельно');
}
