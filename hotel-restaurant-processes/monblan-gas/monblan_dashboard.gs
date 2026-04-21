/**
 * МОНБЛАН — ДАШБОРД: ОТКЛОНЕНИЯ + AI-АНАЛИЗ
 *
 * Логика сравнения:
 *   • Кухня и Бар — абсолютное сравнение (фиксированный верхний блок)
 *   • Метрики с % строкой ниже — сравнение по ПРОЦЕНТНЫМ ПУНКТАМ (п.п.):
 *       🔴 > 5 п.п. снижения   🟡 2–5 п.п. снижения
 *       ⚪ < 2 п.п. (показываем)  🟢 > 2 п.п. роста
 *   • Метрики без % строки — относительное сравнение (2026 vs 2025):
 *       🔴 > 10%   🟡 3–10%   ⚪ норма (не показываем)   🟢 > 5%
 *
 * Исключены: Столов, Посадочных мест, Мероприятия.
 * Завтраки — включены отдельной строкой.
 *
 * Установка:
 *   1. Вставьте этот файл в Apps Script таблицы
 *   2. installTrigger() — один раз
 *   3. Меню «🔶 Монблан» → «Обновить дашборд»
 */

var DASH_GID    = 1669207980;
var DASH_NAME   = 'Дашборд';
var MONBLAN_GID = 2051236241;

// ── Пороги: относительное изменение (для метрик без % строки) ──
var T_RED    = -0.10;
var T_YELLOW = -0.03;
var T_GREEN  =  0.05;

// ── Пороги: процентные пункты (для метрик с % строкой ниже) ───
var T_RED_PP    = -0.05;  // 🔴 > 5 п.п. снижения
var T_YELLOW_PP = -0.02;  // 🟡 2–5 п.п. снижения
var T_GREEN_PP  =  0.02;  // 🟢 > 2 п.п. роста

// ── Строки с процентным форматом в листе Монблан ─────────────
var PCT_ROWS_MB = {
  6:1, 8:1, 11:1, 13:1, 15:1, 18:1, 20:1, 22:1, 24:1, 26:1, 28:1, 30:1,
  33:1, 35:1, 37:1, 62:1, 64:1, 66:1, 69:1, 71:1, 73:1,
  76:1, 78:1, 80:1, 82:1, 84:1, 86:1
};

// ── Строки, исключённые из дашборда полностью ────────────────
// 87=Столов, 88-89=Посадочных мест, 90=Мероприятия (заголовок)
// 92-96=Количество/Выручка/Гости/Чеки мероприятий
// 91=Завтраки — НЕ исключается
var SKIP_ROWS_MB = (function() {
  var s = {};
  [87, 88, 89, 90, 92, 93, 94, 95, 96].forEach(function(r) { s[r] = 1; });
  return s;
}());

// ── Кухня (5) и Бар (7) — абсолютное сравнение (не п.п.) ─────
var FORCE_ABSOLUTE_MB = { 5:1, 7:1 };

// ── Фиксированные строки дашборда ────────────────────────────
var R_TITLE = 1;
var R_SEL   = 2;
var R_HDR   = 3;
var R_DATA  = 4;


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

  writeStaticHeaders_(dash);

  var week = parseInt(dash.getRange(R_SEL, 2).getValue());
  if (!week || isNaN(week) || week < 1 || week > 5) {
    clearDataRows_(dash);
    dash.getRange(R_DATA, 1).setValue('⚠️ Выберите неделю в ячейке B2 (1–5)');
    return;
  }

  ss.toast('Читаем данные Монблан...', '🔶 Монблан', 30);

  var col25 = findWeekCol_(mb, 2025, week);
  var col26 = findWeekCol_(mb, 2026, week);

  var deviations = getDeviations_(mb, col25, col26);

  clearDataRows_(dash);

  if (deviations.length === 0) {
    dash.getRange(R_DATA, 1, 1, 5).merge()
      .setValue('✅ Все показатели недели ' + week + ' в норме — отклонений нет')
      .setBackground('#d9ead3').setFontWeight('bold');
    saveAiStartRow_(R_DATA + 4);
    ss.toast('✅ Нет значимых отклонений — неделя ' + week, '🔶 Монблан', 5);
    return;
  }

  writeDeviationRows_(dash, deviations);

  var signalsEnd = writeSignalsSection_(dash, R_DATA + deviations.length + 2, deviations);

  var aiRow = signalsEnd + 2;
  saveAiStartRow_(aiRow);
  writeAiSkeleton_(dash, aiRow, week);

  ss.toast('✅ ' + deviations.length + ' показателей — неделя ' + week, '🔶 Монблан', 5);
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
// ЧТЕНИЕ МЕТРИК И РАСЧЁТ ОТКЛОНЕНИЙ
//
// Два режима для каждой метрики:
//   П.П.-режим: если ниже есть % строка (и не FORCE_ABSOLUTE)
//     → сравниваем доли, delta = pct26 - pct25 (в долях)
//     → показываем всегда (включая ⚪ < 2 п.п.)
//   Относительный режим: иначе
//     → delta = (v26 - v25) / |v25|
//     → норму ⚪ не показываем
// ═══════════════════════════════════════════════════════════════
function getDeviations_(sh, col25, col26) {
  var N      = 96;
  var labels = sh.getRange(1, 1, N, 1).getValues();
  var vals25 = col25 ? sh.getRange(1, col25, N, 1).getValues() : null;
  var vals26 = col26 ? sh.getRange(1, col26, N, 1).getValues() : null;

  var result = [];
  for (var i = 3; i < N; i++) {
    var rowNum = i + 1;  // 1-based

    // Пропускаем исключённые строки и % строки (обрабатываются с родителем)
    if (SKIP_ROWS_MB[rowNum] || PCT_ROWS_MB[rowNum]) continue;

    var label = String(labels[i][0] || '').trim();
    if (!label) continue;

    var v25 = vals25 ? (parseFloat(vals25[i][0]) || 0) : 0;
    var v26 = vals26 ? (parseFloat(vals26[i][0]) || 0) : 0;

    if (v25 === 0 && v26 === 0) continue;

    var hasPctBelow   = !!PCT_ROWS_MB[rowNum + 1];
    var forceAbsolute = !!FORCE_ABSOLUTE_MB[rowNum];

    if (hasPctBelow && !forceAbsolute) {
      // ── П.П.-РЕЖИМ: сравниваем доли (процентные пункты) ──────
      var pct25  = vals25 ? (parseFloat(vals25[i + 1][0]) || 0) : 0;
      var pct26  = vals26 ? (parseFloat(vals26[i + 1][0]) || 0) : 0;
      var ppDiff = pct26 - pct25;  // в долях: -0.05 = −5 п.п.

      result.push({
        label:     label,
        v2025:     v25,
        v2026:     v26,
        pct2025:   pct25,
        pct2026:   pct26,
        delta:     ppDiff,
        isPptMode: true,
      });
    } else {
      // ── ОТНОСИТЕЛЬНЫЙ РЕЖИМ: (v26 − v25) / |v25| ─────────────
      if (v25 === 0) continue;
      var delta = (v26 - v25) / Math.abs(v25);

      // Аномалия: база слишком мала
      if (Math.abs(delta) > 3) continue;

      // Норма ⚪ в относительном режиме — не показываем
      if (delta > T_YELLOW && delta <= T_GREEN) continue;

      result.push({
        label:     label,
        v2025:     v25,
        v2026:     v26,
        delta:     delta,
        isPptMode: false,
      });
    }
  }
  return result;
}


// ═══════════════════════════════════════════════════════════════
// ЗАПИСЬ СТРОК ОТКЛОНЕНИЙ
// ═══════════════════════════════════════════════════════════════
function writeDeviationRows_(dash, deviations) {
  var values = deviations.map(function(d) {
    return [
      d.label,
      formatValue_(d.v2025),
      formatValue_(d.v2026),
      formatDelta_(d),
      getSignal_(d),
    ];
  });

  var dataRange = dash.getRange(R_DATA, 1, values.length, 5);
  dataRange.setValues(values);
  dataRange.setFontSize(9);
  dataRange.setVerticalAlignment('middle');

  for (var i = 0; i < deviations.length; i++) {
    var row = R_DATA + i;
    var bg  = getBgColor_(deviations[i]);

    dash.getRange(row, 1).setHorizontalAlignment('left');
    dash.getRange(row, 2, 1, 2).setHorizontalAlignment('right');
    dash.getRange(row, 4, 1, 2).setHorizontalAlignment('center');

    if (bg) {
      dash.getRange(row, 1, 1, 5).setBackground(bg);
    } else {
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

  dash.getRange(R_TITLE, 1, 1, 5).merge()
    .setValue('ДАШБОРД — МОНБЛАН')
    .setBackground('#1a3a5c')
    .setFontColor('#ffffff')
    .setFontWeight('bold')
    .setFontSize(13)
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle');

  dash.getRange(R_SEL, 1).setValue('Выберите неделю 2026 (1–5):')
    .setFontWeight('bold').setBackground('#f0f0f0');
  dash.getRange(R_SEL, 2).setValue(1)
    .setBackground('#f0f0f0').setHorizontalAlignment('center');
  dash.getRange(R_SEL, 3, 1, 3).setBackground('#f0f0f0');

  var rule = SpreadsheetApp.newDataValidation()
    .requireValueInList(['1','2','3','4','5'], true)
    .build();
  dash.getRange(R_SEL, 2).setDataValidation(rule);

  var hdr = dash.getRange(R_HDR, 1, 1, 5);
  hdr.setValues([['Показатель', '2025', '2026', 'Δ', '●']]);
  hdr.setBackground('#2d6a9f')
    .setFontColor('#ffffff')
    .setFontWeight('bold')
    .setFontSize(9)
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle');
  dash.getRange(R_HDR, 1).setHorizontalAlignment('left');

  dash.setFrozenRows(3);

  dash.setColumnWidth(1, 250);
  dash.setColumnWidth(2, 110);
  dash.setColumnWidth(3, 110);
  dash.setColumnWidth(4, 90);
  dash.setColumnWidth(5, 50);
}


// ═══════════════════════════════════════════════════════════════
// БЛОК «СИГНАЛЫ НЕДЕЛИ» — топ-5 по каждой зоне
// Пишется сразу после таблицы отклонений
// ═══════════════════════════════════════════════════════════════
function writeSignalsSection_(dash, startRow, deviations) {
  var red = deviations
    .filter(function(d) { return getSignal_(d) === '🔴'; })
    .sort(function(a, b) { return a.delta - b.delta; })
    .slice(0, 5);

  var yellow = deviations
    .filter(function(d) { return getSignal_(d) === '🟡'; })
    .sort(function(a, b) { return a.delta - b.delta; })
    .slice(0, 5);

  var green = deviations
    .filter(function(d) { return getSignal_(d) === '🟢'; })
    .sort(function(a, b) { return b.delta - a.delta; })
    .slice(0, 5);

  var row = startRow;

  dash.getRange(row, 1, 1, 5).merge()
    .setValue('🚨  СИГНАЛЫ НЕДЕЛИ  (топ-5 по каждой зоне)')
    .setBackground('#333333').setFontColor('#ffffff')
    .setFontWeight('bold').setFontSize(10)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  row++;

  // 🔴 Проблемные зоны
  dash.getRange(row, 1, 1, 5).merge()
    .setValue('🔴  ПРОБЛЕМНЫЕ ЗОНЫ  (> 10% или > 5 п.п. снижения)')
    .setBackground('#b43232').setFontColor('#ffffff')
    .setFontWeight('bold').setFontSize(9).setVerticalAlignment('middle');
  row++;
  if (red.length === 0) {
    dash.getRange(row, 1, 1, 5).merge().setValue('— нет').setBackground('#ffcccc').setFontSize(9);
    row++;
  } else {
    red.forEach(function(d) {
      dash.getRange(row, 1, 1, 4).merge()
        .setValue(d.label).setBackground('#ffcccc').setFontSize(9).setVerticalAlignment('middle');
      dash.getRange(row, 5)
        .setValue(formatDelta_(d)).setBackground('#ffcccc').setFontSize(9)
        .setHorizontalAlignment('center').setFontWeight('bold').setFontColor('#b43232');
      row++;
    });
  }

  // 🟡 Требуют внимания
  dash.getRange(row, 1, 1, 5).merge()
    .setValue('🟡  ТРЕБУЮТ ВНИМАНИЯ  (3–10% или 2–5 п.п. снижения)')
    .setBackground('#997800').setFontColor('#ffffff')
    .setFontWeight('bold').setFontSize(9).setVerticalAlignment('middle');
  row++;
  if (yellow.length === 0) {
    dash.getRange(row, 1, 1, 5).merge().setValue('— нет').setBackground('#fff2cc').setFontSize(9);
    row++;
  } else {
    yellow.forEach(function(d) {
      dash.getRange(row, 1, 1, 4).merge()
        .setValue(d.label).setBackground('#fff2cc').setFontSize(9).setVerticalAlignment('middle');
      dash.getRange(row, 5)
        .setValue(formatDelta_(d)).setBackground('#fff2cc').setFontSize(9)
        .setHorizontalAlignment('center').setFontWeight('bold').setFontColor('#997800');
      row++;
    });
  }

  // 🟢 Работает хорошо
  dash.getRange(row, 1, 1, 5).merge()
    .setValue('🟢  РАБОТАЕТ ХОРОШО  (> 5% или > 2 п.п. роста)')
    .setBackground('#19622a').setFontColor('#ffffff')
    .setFontWeight('bold').setFontSize(9).setVerticalAlignment('middle');
  row++;
  if (green.length === 0) {
    dash.getRange(row, 1, 1, 5).merge().setValue('— нет').setBackground('#d9ead3').setFontSize(9);
    row++;
  } else {
    green.forEach(function(d) {
      dash.getRange(row, 1, 1, 4).merge()
        .setValue(d.label).setBackground('#d9ead3').setFontSize(9).setVerticalAlignment('middle');
      dash.getRange(row, 5)
        .setValue(formatDelta_(d)).setBackground('#d9ead3').setFontSize(9)
        .setHorizontalAlignment('center').setFontWeight('bold').setFontColor('#19622a');
      row++;
    });
  }

  return row;
}


// ═══════════════════════════════════════════════════════════════
// ОЧИСТКА ДИНАМИЧЕСКОЙ ЗОНЫ (строки 4 и ниже, 10 колонок)
// ═══════════════════════════════════════════════════════════════
function clearDataRows_(dash) {
  var lastRow = dash.getLastRow();
  if (lastRow < R_DATA) return;
  var numRows = lastRow - R_DATA + 1;
  var zone = dash.getRange(R_DATA, 1, numRows, 10);
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

  var col25      = findWeekCol_(mb, 2025, week);
  var col26      = findWeekCol_(mb, 2026, week);
  var deviations = getDeviations_(mb, col25, col26);

  if (!deviations.length) {
    SpreadsheetApp.getUi().alert('Нет отклонений для анализа.\nСначала нажмите «Обновить дашборд».');
    return;
  }

  ss.toast('Запрашиваем AI (Groq)...', '🔶 Монблан', 120);

  var red    = deviations.filter(function(d) { return getSignal_(d) === '🔴'; });
  var yellow = deviations.filter(function(d) { return getSignal_(d) === '🟡'; });
  var green  = deviations.filter(function(d) { return getSignal_(d) === '🟢'; });

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

  var aiRow = getAiStartRow_() || (R_DATA + deviations.length + 20);
  writeAiBlock_(dash, aiRow, week, aiText);
  ss.toast('✅ AI-анализ готов', '🔶 Монблан', 5);
}


// ═══════════════════════════════════════════════════════════════
// ЗАГЛУШКА AI-БЛОКА — пишется сразу при обновлении дашборда
// ═══════════════════════════════════════════════════════════════
function writeAiSkeleton_(dash, startRow, week) {
  var placeholder = '← Нажмите «🔶 Монблан» → «Обновить AI-анализ»';

  function writeSkeletonSection(headerRow, headerText) {
    dash.getRange(headerRow, 1, 1, 5).merge()
      .setValue(headerText)
      .setBackground('#3d3d3d').setFontColor('#ffffff')
      .setFontWeight('bold').setFontSize(9).setVerticalAlignment('middle');
    for (var i = 0; i < 3; i++) {
      dash.getRange(headerRow + 1 + i, 1, 1, 5).merge()
        .setValue(placeholder)
        .setBackground('#f0f0f0').setFontColor('#888888')
        .setFontStyle('italic').setFontSize(9)
        .setWrap(true).setVerticalAlignment('middle').setHorizontalAlignment('center');
    }
  }

  writeSkeletonSection(startRow,      '🔍  ВОЗМОЖНЫЕ ПРИЧИНЫ  (AI-анализ — неделя ' + week + ')');
  writeSkeletonSection(startRow + 5,  '💡  РЕКОМЕНДАЦИИ  (AI)');
  writeSkeletonSection(startRow + 10, '📋  УПРАВЛЕНЧЕСКИЕ ВЫВОДЫ  (AI)');
}


// ═══════════════════════════════════════════════════════════════
// ЗАПИСЬ AI-БЛОКА (3 секции × 3 строки)
// ═══════════════════════════════════════════════════════════════
function writeAiBlock_(dash, startRow, week, aiText) {
  var blocks = parseAiBlocks_(aiText);

  var aiZone = dash.getRange(startRow, 1, 15, 5);
  aiZone.clearContent().clearFormat().breakApart();

  function writeSection(headerRow, headerText, items) {
    dash.getRange(headerRow, 1, 1, 5).merge()
      .setValue(headerText)
      .setBackground('#3d3d3d').setFontColor('#ffffff')
      .setFontWeight('bold').setFontSize(9).setVerticalAlignment('middle');
    for (var i = 0; i < 3; i++) {
      dash.getRange(headerRow + 1 + i, 1, 1, 5).merge()
        .setValue(items[i] || '—')
        .setBackground('#f8f9fa').setFontColor('#212529')
        .setFontSize(9).setWrap(true).setVerticalAlignment('middle');
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
      return '• ' + d.label + ': ' + formatDelta_(d) +
             ' (2025: ' + fmtNum_(d.v2025) + ', 2026: ' + fmtNum_(d.v2026) + ')';
    }).join('\n');
  }
  return 'Ты — аналитик ресторанного бизнеса. Ресторан «Монблан», горнолыжный курорт Губаха.\n\n' +
    'Неделя ' + week + ' / 2026 vs неделя ' + week + ' / 2025:\n\n' +
    '🔴 ПРОБЛЕМЫ:\n' + fmtList(red) + '\n\n' +
    '🟡 ТРЕБУЮТ ВНИМАНИЯ:\n' + fmtList(yellow) + '\n\n' +
    '🟢 РАСТУТ:\n' + fmtList(green) + '\n\n' +
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

// Сигнал — принимает объект deviation (с полем isPptMode)
function getSignal_(d) {
  if (d.isPptMode) {
    if (d.delta < T_RED_PP)    return '🔴';
    if (d.delta < T_YELLOW_PP) return '🟡';
    if (d.delta > T_GREEN_PP)  return '🟢';
    return '⚪';
  }
  if (d.delta < T_RED)    return '🔴';
  if (d.delta < T_YELLOW) return '🟡';
  if (d.delta > T_GREEN)  return '🟢';
  return '⚪';
}

// Фон строки — принимает объект deviation
function getBgColor_(d) {
  if (d.isPptMode) {
    if (d.delta < T_RED_PP)    return '#ffcccc';
    if (d.delta < T_YELLOW_PP) return '#fff2cc';
    if (d.delta > T_GREEN_PP)  return '#d9ead3';
    return null;
  }
  if (d.delta < T_RED)    return '#ffcccc';
  if (d.delta < T_YELLOW) return '#fff2cc';
  if (d.delta > T_GREEN)  return '#d9ead3';
  return null;
}

// Форматирование значения Δ: п.п. или %
function formatDelta_(d) {
  var sign = d.delta > 0 ? '+' : '';
  if (d.isPptMode) {
    var pp = Math.round(d.delta * 1000) / 10;
    return sign + pp + ' п.п.';
  }
  var pct = Math.round(d.delta * 1000) / 10;
  return sign + pct + '%';
}

function formatValue_(v) {
  if (!v) return '0';
  return Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
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
