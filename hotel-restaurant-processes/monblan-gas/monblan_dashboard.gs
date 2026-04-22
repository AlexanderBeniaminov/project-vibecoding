/**
 * МОНБЛАН — ДАШБОРД
 *
 * Строки 1–4: заголовок, выбор недели, годы, даты
 * Строки 5+:  ВСЕ показатели листа «Монблан» (кроме Столов и Посадочных мест)
 *             включая процентные строки, заголовки секций
 * После:      Сигналы недели (топ-5) + AI-блок
 *
 * Цвета — абсолютные строки (относительное изменение):
 *   🔴 > 10% снижения  🟡 3–10%  ⚪ норма  🟢 > 5% роста
 * Цвета — % строки (процентные пункты):
 *   🔴 > 5 п.п. снижения  🟡 1–5 п.п.  ⚪ норма  🟢 > 3 п.п. роста
 * Цвет закрашивает ВСЮ строку по горизонтали.
 */

var DASH_GID    = 1669207980;
var DASH_NAME   = 'Дашборд';
var MONBLAN_GID = 2051236241;

// ── Пороги: абсолютные строки ────────────────────────────────
var T_RED    = -0.10;
var T_YELLOW = -0.03;
var T_GREEN  =  0.05;

// ── Пороги: процентные строки (п.п.) ─────────────────────────
var T_RED_PP    = -0.05;
var T_YELLOW_PP = -0.01;
var T_GREEN_PP  =  0.03;

// ── % строки листа «Монблан» ─────────────────────────────────
var PCT_ROWS_MB = {
  6:1, 8:1, 11:1, 13:1, 15:1, 18:1, 20:1, 22:1, 24:1, 26:1, 28:1, 30:1,
  33:1, 35:1, 37:1, 62:1, 64:1, 66:1, 69:1, 71:1, 73:1,
  76:1, 78:1, 80:1, 82:1, 84:1, 86:1
};

// ── Исключённые строки (Столов=87, Посадочных мест=88) ───────
var SKIP_ROWS_MB = {87:1, 88:1};

// ── Явные заголовки секций (никогда не имеют собственных данных) ──
var HEADER_ROWS_MB = {60:1, 74:1, 90:1};

// ── Строки с одним знаком после запятой (Оборачиваемость) ────
var DECIMAL_ROWS_MB = {52:1, 53:1, 54:1, 55:1, 56:1, 57:1, 58:1, 59:1};

// ── Строки дашборда ──────────────────────────────────────────
var R_TITLE = 1;
var R_SEL   = 2;
var R_HDR   = 3;
var R_DATE  = 4;
var R_DATA  = 5;

var MONTHS_RU = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];


// ═══════════════════════════════════════════════════════════════
// УСТАНОВКА ТРИГГЕРА
// ═══════════════════════════════════════════════════════════════
function installTrigger() {
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === 'onEditDashboard') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('onEditDashboard')
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onEdit().create();
  SpreadsheetApp.getUi().alert('✅ Триггер установлен!\nПри смене недели в B2 дашборд обновляется автоматически.');
}

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('🔶 Монблан')
    .addItem('Обновить дашборд',   'refreshDashboard')
    .addItem('Обновить AI-анализ', 'runAiAnalysis')
    .addSeparator()
    .addItem('Установить триггер onEdit', 'installTrigger')
    .addToUi();
}

function onEditDashboard(e) {
  if (!e) return;
  var rng = e.range;
  if (rng.getSheet().getSheetId() !== DASH_GID) return;
  if (rng.getRow() !== R_SEL || rng.getColumn() !== 2) return;
  Utilities.sleep(300);
  refreshDashboard();
}


// ═══════════════════════════════════════════════════════════════
// ГЛАВНАЯ ФУНКЦИЯ
// ═══════════════════════════════════════════════════════════════
function refreshDashboard() {
  var ss   = SpreadsheetApp.getActiveSpreadsheet();
  var dash = getDashSheet_(ss);
  var mb   = getMonblanSheet_(ss);

  if (!dash) { SpreadsheetApp.getUi().alert('Лист «Дашборд» не найден (GID=' + DASH_GID + ')'); return; }
  if (!mb)   { SpreadsheetApp.getUi().alert('Лист «Монблан» не найден (GID=' + MONBLAN_GID + ')'); return; }

  var week = parseInt(dash.getRange(R_SEL, 2).getValue());

  var col25 = week ? findWeekCol_(mb, 2025, week) : null;
  var col26 = week ? findWeekCol_(mb, 2026, week) : null;

  // Строки 1–4 (заголовок, выбор, года, даты)
  writeStaticRows_(dash, mb, col25, col26, week);

  if (!week || isNaN(week) || week < 1 || week > 5) {
    clearDataRows_(dash);
    dash.getRange(R_DATA, 1, 1, 5).merge()
      .setValue('⚠️ Выберите неделю в ячейке B2 (1–5)')
      .setBackground('#fff3cd').setHorizontalAlignment('center').setFontWeight('bold');
    return;
  }

  ss.toast('Загружаем данные...', '🔶 Монблан', 60);

  clearDataRows_(dash);

  // Все метрики (строки 5+)
  var lastDataRow = writeAllMetricRows_(dash, mb, col25, col26);

  // Сигналы недели
  var signals    = computeSignals_(mb, col25, col26);
  var signalsEnd = writeSignalsSection_(dash, lastDataRow + 2, signals);

  // AI-заглушка
  var aiRow = signalsEnd + 2;
  saveAiStartRow_(aiRow);
  writeAiSkeleton_(dash, aiRow, week);

  ss.toast('✅ Дашборд обновлён — неделя ' + week, '🔶 Монблан', 5);
}


// ═══════════════════════════════════════════════════════════════
// ПОИСК СТОЛБЦА ГОДА/НЕДЕЛИ
// ═══════════════════════════════════════════════════════════════
function findWeekCol_(sh, year, week) {
  var lastCol = sh.getLastColumn();
  if (lastCol < 2) return null;
  var yearRow = sh.getRange(1, 1, 1, lastCol).getValues()[0];
  var weekRow = sh.getRange(2, 1, 1, lastCol).getValues()[0];
  for (var i = 1; i < yearRow.length; i++) {
    if (parseInt(yearRow[i]) === year && parseInt(weekRow[i]) === week) return i + 1;
  }
  return null;
}


// ═══════════════════════════════════════════════════════════════
// СТРОКИ 1–4: ЗАГОЛОВОК / ВЫБОР НЕДЕЛИ / ГОДЫ / ДАТЫ
// ═══════════════════════════════════════════════════════════════
function writeStaticRows_(dash, mb, col25, col26, week) {
  // Очищаем строки 1–4
  dash.getRange(R_TITLE, 1, 4, 5).breakApart().clearContent().clearFormat();

  // Строка 1 — заголовок
  dash.getRange(R_TITLE, 1, 1, 5).merge()
    .setValue('ДАШБОРД — МОНБЛАН')
    .setBackground('#1a3a5c').setFontColor('#ffffff')
    .setFontWeight('bold').setFontSize(14)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  dash.setRowHeight(R_TITLE, 34);

  // Строка 2 — выбор недели
  dash.getRange(R_SEL, 1).setValue('Выберите неделю 2026 (1–5):')
    .setBackground('#e8f0fe').setFontColor('#1a3a5c')
    .setFontWeight('bold').setFontSize(10)
    .setHorizontalAlignment('left').setVerticalAlignment('middle');
  var b2 = dash.getRange(R_SEL, 2);
  if (!b2.getValue()) b2.setValue(1);
  b2.setBackground('#e8f0fe').setFontColor('#1a3a5c')
    .setFontWeight('bold').setFontSize(11).setHorizontalAlignment('center');
  if (!b2.getDataValidation()) {
    b2.setDataValidation(SpreadsheetApp.newDataValidation()
      .requireValueInList(['1','2','3','4','5'], true).build());
  }
  dash.getRange(R_SEL, 3, 1, 3).setBackground('#e8f0fe');
  dash.setRowHeight(R_SEL, 28);

  // Строка 3 — годы
  dash.getRange(R_HDR, 1, 1, 5).setValues([['Показатель', '2025', '2026', 'Δ', '●']])
    .setBackground('#2d6a9f').setFontColor('#ffffff')
    .setFontWeight('bold').setFontSize(10)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  dash.getRange(R_HDR, 1).setHorizontalAlignment('left');
  dash.setRowHeight(R_HDR, 24);

  // Строка 4 — даты
  var date25 = (col25 && week) ? weekDateRange_(mb, col25, 2025, week) : '—';
  var date26 = (col26 && week) ? weekDateRange_(mb, col26, 2026, week) : '—';
  dash.getRange(R_DATE, 1).setValue('Период:')
    .setBackground('#dce8fc').setFontColor('#1a3a5c')
    .setFontStyle('italic').setFontSize(9).setVerticalAlignment('middle');
  dash.getRange(R_DATE, 2).setValue(date25)
    .setBackground('#dce8fc').setFontColor('#1a3a5c')
    .setFontSize(9).setHorizontalAlignment('center').setVerticalAlignment('middle');
  dash.getRange(R_DATE, 3).setValue(date26)
    .setBackground('#dce8fc').setFontColor('#1a3a5c')
    .setFontSize(9).setHorizontalAlignment('center').setVerticalAlignment('middle');
  dash.getRange(R_DATE, 4, 1, 2).setBackground('#dce8fc');
  dash.setRowHeight(R_DATE, 20);

  // Заморозить строки 1–4
  dash.setFrozenRows(4);

  // Ширины колонок
  dash.setColumnWidth(1, 260);
  dash.setColumnWidth(2, 120);
  dash.setColumnWidth(3, 120);
  dash.setColumnWidth(4, 90);
  dash.setColumnWidth(5, 40);
}

// Дата-диапазон недели с русскими месяцами
function weekDateRange_(mb, col, year, week) {
  var stored = mb.getRange(3, col, 1, 1).getValue();
  if (stored && String(stored).trim()) return String(stored).trim();
  return isoWeekRu_(year, week);
}

function isoWeekRu_(year, week) {
  var d = new Date(year, 0, 4);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7) + (week - 1) * 7);
  var sun = new Date(d); sun.setDate(d.getDate() + 6);
  function f(x) { return x.getDate() + ' ' + MONTHS_RU[x.getMonth()]; }
  return f(d) + ' – ' + f(sun);
}


// ═══════════════════════════════════════════════════════════════
// ОЧИСТКА СТРОК ДАННЫХ (5+)
// ═══════════════════════════════════════════════════════════════
function clearDataRows_(dash) {
  var lastRow = dash.getLastRow();
  if (lastRow < R_DATA) return;
  dash.getRange(R_DATA, 1, lastRow - R_DATA + 1, 5)
    .clearContent().clearFormat().breakApart();
}


// ═══════════════════════════════════════════════════════════════
// ВСЕ МЕТРИКИ (строки 5+)
// Полная копия листа «Монблан», кроме Столов и Посадочных мест
// ═══════════════════════════════════════════════════════════════
function writeAllMetricRows_(dash, mb, col25, col26) {
  var N      = 96;
  var labels = mb.getRange(1, 1, N, 1).getValues();
  var v25arr = col25 ? mb.getRange(1, col25, N, 1).getValues() : null;
  var v26arr = col26 ? mb.getRange(1, col26, N, 1).getValues() : null;

  var dashRow   = R_DATA;
  var lastLabel = '';

  for (var i = 3; i < N; i++) {
    var rowNum = i + 1;
    if (SKIP_ROWS_MB[rowNum]) continue;

    var label = String(labels[i][0] || '').trim();
    var isPct = !!PCT_ROWS_MB[rowNum];
    var v25   = v25arr ? (parseFloat(v25arr[i][0]) || 0) : 0;
    var v26   = v26arr ? (parseFloat(v26arr[i][0]) || 0) : 0;

    if (label) lastLabel = label;

    if (!isPct && !label) continue;  // пустые разделители — пропускаем

    if (!isPct && HEADER_ROWS_MB[rowNum]) {
      // Явный заголовок секции (без данных)
      dash.getRange(dashRow, 1, 1, 5).merge()
        .setValue('  ' + label)
        .setBackground('#cfd8e8').setFontColor('#1a2a4a')
        .setFontWeight('bold').setFontSize(9)
        .setHorizontalAlignment('left').setVerticalAlignment('middle');
      dash.setRowHeight(dashRow, 20);
      dashRow++;
      continue;
    }

    var isDecimal = !!DECIMAL_ROWS_MB[rowNum];
    var isNoBase  = (!isPct && v25 === 0);  // нет базы 2025 → зелёный, дельта "0"

    // Вычисляем дельту
    var delta    = null;
    var hasDelta = false;
    if (isPct) {
      delta    = v26 - v25;
      hasDelta = true;
    } else if (!isNoBase) {
      var d = (v26 - v25) / Math.abs(v25);
      if (Math.abs(d) <= 3) { delta = d; hasDelta = true; }
    }

    var bg   = isNoBase ? '#c3e6cb' : (hasDelta ? getBgColor_(delta, isPct) : null);
    var dStr = isNoBase ? '0' : (hasDelta ? fmtDelta_(delta, isPct) : '');
    var eStr = isNoBase ? '🟢' : (hasDelta ? getSignal_(delta, isPct) : '');

    // Форматирование значений для ячеек
    var bStr = fmtCell_(v25, isPct, isDecimal);
    var cStr = fmtCell_(v26, isPct, isDecimal);
    var rowLabel = isPct ? ('  % ' + lastLabel) : label;

    dash.getRange(dashRow, 1, 1, 5).setValues([[rowLabel, bStr, cStr, dStr, eStr]]);

    var rowRng = dash.getRange(dashRow, 1, 1, 5);
    rowRng.setFontSize(9).setVerticalAlignment('middle');
    rowRng.setBackground(bg || (dashRow % 2 === 0 ? '#f8f9fa' : '#ffffff'));

    if (isPct) {
      rowRng.setFontStyle('italic').setFontColor('#555555');
      if (!bg) rowRng.setBackground('#f2f4f8');
    } else {
      dash.getRange(dashRow, 1).setFontColor('#000000').setFontStyle('normal');
    }

    dash.getRange(dashRow, 1).setHorizontalAlignment('left');
    dash.getRange(dashRow, 2, 1, 2).setHorizontalAlignment('right');
    dash.getRange(dashRow, 4, 1, 2).setHorizontalAlignment('center');
    if (hasDelta && bg) dash.getRange(dashRow, 4).setFontWeight('bold');

    dash.setRowHeight(dashRow, isPct ? 18 : 20);
    dashRow++;
  }

  return dashRow;
}


// ═══════════════════════════════════════════════════════════════
// СИГНАЛЫ: вычислить список отклонений для сигнальной секции
// ═══════════════════════════════════════════════════════════════
function computeSignals_(mb, col25, col26) {
  var N      = 96;
  var labels = mb.getRange(1, 1, N, 1).getValues();
  var v25arr = col25 ? mb.getRange(1, col25, N, 1).getValues() : null;
  var v26arr = col26 ? mb.getRange(1, col26, N, 1).getValues() : null;

  var result    = [];
  var lastLabel = '';

  for (var i = 3; i < N; i++) {
    var rowNum = i + 1;
    if (SKIP_ROWS_MB[rowNum]) continue;

    var label = String(labels[i][0] || '').trim();
    var isPct = !!PCT_ROWS_MB[rowNum];
    if (label) lastLabel = label;

    var dispLabel = isPct ? ('% ' + lastLabel) : label;
    if (!dispLabel) continue;

    var v25 = v25arr ? (parseFloat(v25arr[i][0]) || 0) : 0;
    var v26 = v26arr ? (parseFloat(v26arr[i][0]) || 0) : 0;
    if (v25 === 0 && v26 === 0) continue;

    var delta;
    if (isPct) {
      delta = v26 - v25;
    } else {
      if (v25 === 0) continue;
      delta = (v26 - v25) / Math.abs(v25);
      if (Math.abs(delta) > 3) continue;
    }

    var sig = getSignal_(delta, isPct);
    if (sig === '⚪') continue;

    result.push({label: dispLabel, delta: delta, isPct: isPct, signal: sig});
  }
  return result;
}


// ═══════════════════════════════════════════════════════════════
// СИГНАЛЫ НЕДЕЛИ (топ-5 по зоне)
// ═══════════════════════════════════════════════════════════════
function writeSignalsSection_(dash, startRow, signals) {
  var red = signals.filter(function(d){return d.signal==='🔴';})
    .sort(function(a,b){return a.delta-b.delta;}).slice(0,5);
  var yellow = signals.filter(function(d){return d.signal==='🟡';})
    .sort(function(a,b){return a.delta-b.delta;}).slice(0,5);
  var green = signals.filter(function(d){return d.signal==='🟢';})
    .sort(function(a,b){return b.delta-a.delta;}).slice(0,5);

  var row = startRow;

  dash.getRange(row,1,1,5).merge()
    .setValue('🚨  СИГНАЛЫ НЕДЕЛИ  (топ-5 по каждой зоне)')
    .setBackground('#2c2c2c').setFontColor('#ffffff')
    .setFontWeight('bold').setFontSize(10)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  dash.setRowHeight(row, 26); row++;

  row = writeZone_(dash, row,
    '🔴  ПРОБЛЕМНЫЕ ЗОНЫ  (> 10% или > 5 п.п. снижения)',
    '#b43232','#fdd','#c0392b', red);
  row = writeZone_(dash, row,
    '🟡  ТРЕБУЮТ ВНИМАНИЯ  (3–10% или 1–5 п.п. снижения)',
    '#9a6b00','#fff3cd','#856404', yellow);
  row = writeZone_(dash, row,
    '🟢  РАБОТАЕТ ХОРОШО  (> 5% или > 3 п.п. роста)',
    '#1e6641','#d4edda','#155724', green);

  return row;
}

function writeZone_(dash, row, hdr, hdrBg, itemBg, valFg, items) {
  dash.getRange(row,1,1,5).merge().setValue(hdr)
    .setBackground(hdrBg).setFontColor('#ffffff')
    .setFontWeight('bold').setFontSize(9).setVerticalAlignment('middle');
  dash.setRowHeight(row, 22); row++;

  if (!items.length) {
    dash.getRange(row,1,1,5).merge().setValue('— нет')
      .setBackground(itemBg).setFontSize(9).setHorizontalAlignment('center');
    dash.setRowHeight(row, 20); row++;
  } else {
    items.forEach(function(d) {
      dash.getRange(row,1,1,4).merge().setValue(d.label)
        .setBackground(itemBg).setFontSize(9)
        .setHorizontalAlignment('left').setVerticalAlignment('middle');
      dash.getRange(row,5).setValue(fmtDelta_(d.delta, d.isPct))
        .setBackground(itemBg).setFontSize(9)
        .setHorizontalAlignment('center').setFontWeight('bold').setFontColor(valFg);
      dash.setRowHeight(row, 20); row++;
    });
  }
  return row;
}


// ═══════════════════════════════════════════════════════════════
// AI-ЗАГЛУШКА
// ═══════════════════════════════════════════════════════════════
function writeAiSkeleton_(dash, startRow, week) {
  var ph = '← Нажмите «🔶 Монблан» → «Обновить AI-анализ»';
  function sec(r, hdr) {
    dash.getRange(r,1,1,5).merge().setValue(hdr)
      .setBackground('#3d3d3d').setFontColor('#ffffff')
      .setFontWeight('bold').setFontSize(9).setVerticalAlignment('middle');
    dash.setRowHeight(r, 22);
    for (var i=0;i<3;i++) {
      dash.getRange(r+1+i,1,1,5).merge().setValue(ph)
        .setBackground('#f5f5f5').setFontColor('#888888')
        .setFontStyle('italic').setFontSize(9)
        .setWrap(true).setHorizontalAlignment('center').setVerticalAlignment('middle');
      dash.setRowHeight(r+1+i, 22);
    }
  }
  sec(startRow,      '🔍  ВОЗМОЖНЫЕ ПРИЧИНЫ  (AI — неделя ' + week + ')');
  sec(startRow + 5,  '💡  РЕКОМЕНДАЦИИ  (AI)');
  sec(startRow + 10, '📋  УПРАВЛЕНЧЕСКИЕ ВЫВОДЫ  (AI)');
}


// ═══════════════════════════════════════════════════════════════
// AI-АНАЛИЗ (Groq)
// ═══════════════════════════════════════════════════════════════
function runAiAnalysis() {
  var ss   = SpreadsheetApp.getActiveSpreadsheet();
  var dash = getDashSheet_(ss);
  var mb   = getMonblanSheet_(ss);
  if (!dash || !mb) return;

  var week = parseInt(dash.getRange(R_SEL, 2).getValue());
  if (!week || isNaN(week)) { SpreadsheetApp.getUi().alert('Выберите неделю в B2'); return; }

  var col25   = findWeekCol_(mb, 2025, week);
  var col26   = findWeekCol_(mb, 2026, week);
  var signals = computeSignals_(mb, col25, col26);

  if (!signals.length) { SpreadsheetApp.getUi().alert('Нет отклонений для анализа.'); return; }

  ss.toast('Запрашиваем AI (Groq)...', '🔶 Монблан', 120);

  var red    = signals.filter(function(d){return d.signal==='🔴';});
  var yellow = signals.filter(function(d){return d.signal==='🟡';});
  var green  = signals.filter(function(d){return d.signal==='🟢';});

  var aiText = callGroq_(buildPrompt_(week, red, yellow, green));
  if (!aiText) {
    SpreadsheetApp.getUi().alert('Ошибка Groq API.\n\nПроверьте GROQ_API_KEY:\nНастройки → Свойства скрипта → GROQ_API_KEY\nКлюч: console.groq.com');
    return;
  }

  var aiRow = getAiStartRow_() || (R_DATA + 110);
  writeAiBlock_(dash, aiRow, week, aiText);
  ss.toast('✅ AI-анализ готов', '🔶 Монблан', 5);
}

function writeAiBlock_(dash, startRow, week, aiText) {
  var blocks = parseAiBlocks_(aiText);
  dash.getRange(startRow, 1, 15, 5).clearContent().clearFormat().breakApart();

  function sec(r, hdr, items) {
    dash.getRange(r,1,1,5).merge().setValue(hdr)
      .setBackground('#3d3d3d').setFontColor('#ffffff')
      .setFontWeight('bold').setFontSize(9).setVerticalAlignment('middle');
    for (var i=0;i<3;i++) {
      dash.getRange(r+1+i,1,1,5).merge().setValue(items[i]||'—')
        .setBackground('#f8f9fa').setFontColor('#212529')
        .setFontSize(9).setWrap(true).setVerticalAlignment('middle');
    }
  }
  sec(startRow,      '🔍  ВОЗМОЖНЫЕ ПРИЧИНЫ  (AI — неделя ' + week + ')', blocks.causes);
  sec(startRow + 5,  '💡  РЕКОМЕНДАЦИИ  (AI)', blocks.recs);
  sec(startRow + 10, '📋  УПРАВЛЕНЧЕСКИЕ ВЫВОДЫ  (AI)', blocks.mgmt);
}

function callGroq_(prompt) {
  var key = PropertiesService.getScriptProperties().getProperty('GROQ_API_KEY');
  if (!key) return null;
  try {
    var resp = UrlFetchApp.fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'post', muteHttpExceptions: true,
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+key},
      payload: JSON.stringify({model:'llama-3.3-70b-versatile', max_tokens:800,
        messages:[{role:'user',content:prompt}]}),
    });
    if (resp.getResponseCode() !== 200) { Logger.log('Groq '+resp.getResponseCode()); return null; }
    return JSON.parse(resp.getContentText()).choices[0].message.content;
  } catch(e) { Logger.log('Groq: '+e.message); return null; }
}

function buildPrompt_(week, red, yellow, green) {
  function lst(arr) {
    return arr.length ? arr.map(function(d){return '• '+d.label+': '+fmtDelta_(d.delta,d.isPct);}).join('\n') : '—';
  }
  return 'Ты — аналитик ресторанного бизнеса. Ресторан «Монблан», горнолыжный курорт Губаха.\n\n' +
    'Неделя '+week+' / 2026 vs 2025:\n\n' +
    '🔴 ПРОБЛЕМЫ:\n'+lst(red)+'\n\n🟡 ВНИМАНИЕ:\n'+lst(yellow)+'\n\n🟢 РАСТУТ:\n'+lst(green)+'\n\n' +
    'Дай СТРОГО 3 блока по 3 пункта. Каждый пункт — одно предложение (макс 15 слов). Без вступлений.\n\n' +
    'БЛОК 1: ВОЗМОЖНЫЕ ПРИЧИНЫ ПРОБЛЕМ\n1. ...\n2. ...\n3. ...\n\n' +
    'БЛОК 2: РЕКОМЕНДАЦИИ\n1. ...\n2. ...\n3. ...\n\n' +
    'БЛОК 3: УПРАВЛЕНЧЕСКИЕ ВЫВОДЫ\n1. ...\n2. ...\n3. ...';
}

function parseAiBlocks_(text) {
  function extract(t) {
    var items = [];
    (t||'').split('\n').forEach(function(l){
      l = l.trim();
      var m = l.match(/^[1-3][\.\)]\s*(.+)/) || l.match(/^[•\-\*]\s*(.+)/);
      if (m) { items.push(m[1]); return; }
      if (l.length > 5 && !/^(БЛОК|BLOCK|ВОЗМОЖНЫЕ|РЕКОМЕНДАЦИИ|УПРАВЛЕНЧЕСКИЕ)/i.test(l)) items.push(l);
    });
    return items.slice(0,3);
  }
  var parts = text.split(/БЛОК\s*[123][\:\.]?\s*/i);
  if (parts.length >= 4) return {causes:extract(parts[1]),recs:extract(parts[2]),mgmt:extract(parts[3])};
  var t = Math.floor(text.length/3);
  return {causes:extract(text.slice(0,t)),recs:extract(text.slice(t,2*t)),mgmt:extract(text.slice(2*t))};
}


// ═══════════════════════════════════════════════════════════════
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ═══════════════════════════════════════════════════════════════
function getSignal_(delta, isPct) {
  if (isPct) {
    if (delta < T_RED_PP)    return '🔴';
    if (delta < T_YELLOW_PP) return '🟡';
    if (delta > T_GREEN_PP)  return '🟢';
    return '⚪';
  }
  if (delta < T_RED)    return '🔴';
  if (delta < T_YELLOW) return '🟡';
  if (delta > T_GREEN)  return '🟢';
  return '⚪';
}

function getBgColor_(delta, isPct) {
  if (isPct) {
    if (delta < T_RED_PP)    return '#f5c6cb';
    if (delta < T_YELLOW_PP) return '#ffeaa7';
    if (delta > T_GREEN_PP)  return '#c3e6cb';
    return null;
  }
  if (delta < T_RED)    return '#f5c6cb';
  if (delta < T_YELLOW) return '#ffeaa7';
  if (delta > T_GREEN)  return '#c3e6cb';
  return null;
}

function fmtDelta_(delta, isPct) {
  var sign = delta > 0 ? '+' : '';
  if (isPct) return sign + (Math.round(delta * 1000) / 10) + ' п.п.';
  return sign + (Math.round(delta * 1000) / 10) + '%';
}

function fmtCell_(v, isPct, isDecimal) {
  if (v === null || v === undefined) return '—';
  if (isPct) return (Math.round(v * 1000) / 10) + '%';
  if (!v) return '0';
  if (isDecimal) {
    var s = (Math.round(v * 10) / 10).toFixed(1).split('.');
    return s[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + '.' + s[1];
  }
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
  for (var i=0;i<sheets.length;i++) if (sheets[i].getSheetId()===DASH_GID) return sheets[i];
  return ss.getSheetByName(DASH_NAME);
}
function getMonblanSheet_(ss) {
  var sheets = ss.getSheets();
  for (var i=0;i<sheets.length;i++) if (sheets[i].getSheetId()===MONBLAN_GID) return sheets[i];
  return ss.getSheetByName('Монблан') || ss.getSheetByName('Еженедельно');
}
