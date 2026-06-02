/**
 * monblan_monthly_dashboard.gs
 * МОНБЛАН — МЕСЯЧНЫЙ ДАШБОРД
 *
 * Строки 1–4: заголовок, выбор месяца, шапка, инфо о данных
 * Строки 5+:  все показатели листа «ЕжеМесячный» (строки 3–100)
 * После:      Сигналы месяца (топ-5) + AI-блок
 *
 * Сравнение: месяц 2026 vs тот же месяц 2025 (год к году).
 * B2: название месяца из выпадающего списка или число 1–12.
 *
 * Пороги и правила цветов — идентичны еженедельному дашборду.
 */

var MD_DASH_GID    = 783715130;
var MD_SHEET_NAME  = 'ЕжеМесячный';

// ── Пороги (те же, что в еженедельном дашборде) ──────────────
var MD_RED    = -0.10;  var MD_YELLOW = -0.03;  var MD_GREEN  =  0.05;
var MD_RED_PP = -0.05;  var MD_YELLOW_PP = -0.01; var MD_GREEN_PP = 0.03;

// ── % строки листа «ЕжеМесячный» (1-based номера строк) ─────
var MD_PCT_ROWS = {
  5:1, 7:1, 10:1, 12:1, 14:1,
  17:1, 19:1, 21:1, 23:1, 25:1, 27:1, 29:1,
  31:1, 33:1, 35:1, 36:1, 37:1, 38:1, 39:1, 40:1, 41:1,
  44:1, 46:1, 48:1,
  73:1, 75:1, 77:1,
  80:1, 82:1, 84:1,
  87:1, 89:1, 91:1, 93:1, 95:1, 97:1
};

// ── Десятичные строки (1 знак после запятой) ─────────────────
var MD_DECIMAL_ROWS = {62:1, 63:1, 64:1, 65:1, 66:1, 67:1, 68:1, 69:1, 70:1, 78:1};

// ── Чистые разделители (нет числовых данных) ─────────────────
var MD_HEADER_ROWS = {8:1, 15:1, 71:1, 85:1};

// ── Строки с данными + коричневый фон (секционные "итого") ───
// Маржа итого(30), Наценка(36), Фудкост(39), Гости(42),
// Ср.чек на гостя(49), Чеков(53), Блюд(57), Оборот.стол(63),
// Оборот.мест(67), Лояльность(78)
var MD_SECTION_HIGHLIGHT_ROWS = {30:1, 36:1, 39:1, 42:1, 49:1, 53:1, 57:1, 63:1, 67:1, 78:1};

// ── Инвертированные строки: снижение = ХОРОШО (фудкост) ──────
// Фудкост итого(39), Фудкост кухня(40), Фудкост бар(41)
// Чем ниже фудкост — тем лучше: -delta → 🟢, +delta → 🔴
var MD_INVERTED_ROWS = {39:1, 40:1, 41:1};

// ── Пропускаемые строки (Столов, Мест, Дней в месяце) ───────
var MD_SKIP_ROWS = {98:1, 99:1, 100:1};

// ── Строки дашборда ──────────────────────────────────────────
var MD_R_TITLE = 1;
var MD_R_SEL   = 2;
var MD_R_HDR   = 3;
var MD_R_DATE  = 4;
var MD_R_DATA  = 5;

var MD_MONTHS_FULL  = ['январь','февраль','март','апрель','май','июнь',
                        'июль','август','сентябрь','октябрь','ноябрь','декабрь'];
var MD_MONTHS_SHORT = ['янв','фев','мар','апр','май','июн',
                        'июл','авг','сен','окт','ноя','дек'];


// ═══════════════════════════════════════════════════════════════
// УСТАНОВКА ТРИГГЕРА
// ═══════════════════════════════════════════════════════════════
function installMonthlyTrigger() {
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === 'onEditMonthlyDashboard') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('onEditMonthlyDashboard')
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onEdit().create();
  SpreadsheetApp.getUi().alert(
    '✅ Триггер месячного дашборда установлен!\n' +
    'При смене месяца в B2 дашборд обновляется автоматически.'
  );
}

function onEditMonthlyDashboard(e) {
  if (!e) return;
  var rng = e.range;
  if (rng.getSheet().getSheetId() !== MD_DASH_GID) return;
  if (rng.getRow() !== MD_R_SEL || rng.getColumn() !== 2) return;
  Utilities.sleep(300);
  refreshMonthlyDashboard();
}


// ═══════════════════════════════════════════════════════════════
// ГЛАВНАЯ ФУНКЦИЯ
// ═══════════════════════════════════════════════════════════════
function refreshMonthlyDashboard() {
  var ss      = SpreadsheetApp.getActiveSpreadsheet();
  var dash    = getMdDashSheet_(ss);
  var monthly = getMdMonthlySheet_(ss);

  if (!dash) {
    SpreadsheetApp.getUi().alert('Лист «Дашборд месяц» не найден (GID=' + MD_DASH_GID + ')');
    return;
  }
  if (!monthly) {
    SpreadsheetApp.getUi().alert('Лист «' + MD_SHEET_NAME + '» не найден');
    return;
  }

  var rawVal   = dash.getRange(MD_R_SEL, 2).getValue();
  var monthNum = parseMdMonth_(rawVal);

  var col25 = monthNum ? findMdMonthCol_(monthly, 2025, monthNum) : null;
  var col26 = monthNum ? findMdMonthCol_(monthly, 2026, monthNum) : null;

  writeMdStaticRows_(dash, monthNum, col25, col26);
  clearMdDataRows_(dash);

  if (!monthNum || monthNum < 1 || monthNum > 12) {
    dash.getRange(MD_R_DATA, 1, 1, 5).merge()
      .setValue('⚠️ Выберите месяц в ячейке B2 (выпадающий список или число 1–12)')
      .setBackground('#fff3cd').setHorizontalAlignment('center')
      .setFontWeight('bold').setFontSize(13);
    return;
  }

  ss.toast('Загружаем данные...', '🔶 Монблан', 60);

  var lastDataRow = writeMdAllMetricRows_(dash, monthly, col25, col26);
  var signals     = computeMdSignals_(monthly, col25, col26);
  var signalsEnd  = writeMdSignalsSection_(dash, lastDataRow + 2, signals, monthNum);
  var aiRow       = signalsEnd + 2;
  saveMdAiStartRow_(aiRow);
  writeMdAiSkeleton_(dash, aiRow, monthNum);

  ss.toast(
    '✅ Дашборд обновлён — ' + MD_MONTHS_FULL[monthNum - 1] + ' 2026 vs 2025',
    '🔶 Монблан', 5
  );
}


// ═══════════════════════════════════════════════════════════════
// РАЗБОР МЕСЯЦА: число 1–12 или название (полное / краткое)
// ═══════════════════════════════════════════════════════════════
function parseMdMonth_(v) {
  if (!v) return null;
  var n = parseInt(v);
  if (!isNaN(n) && n >= 1 && n <= 12) return n;
  var s = String(v).toLowerCase().trim();
  for (var i = 0; i < MD_MONTHS_FULL.length; i++) {
    if (s === MD_MONTHS_FULL[i]) return i + 1;
    if (s === MD_MONTHS_SHORT[i]) return i + 1;
    if (MD_MONTHS_FULL[i].indexOf(s) === 0 && s.length >= 3) return i + 1;
  }
  return null;
}


// ═══════════════════════════════════════════════════════════════
// ПОИСК КОЛОНКИ: row 2 ищем строку "ГГГГ-ММ"
// ═══════════════════════════════════════════════════════════════
function findMdMonthCol_(sh, year, month) {
  var lastCol = sh.getLastColumn();
  if (lastCol < 2) return null;
  var dateRow = sh.getRange(2, 1, 1, lastCol).getValues()[0];
  var target  = year + '-' + (month < 10 ? '0' + month : String(month));
  for (var i = 1; i < dateRow.length; i++) {
    var v = dateRow[i];
    var s;
    if (v instanceof Date) {
      s = v.getFullYear() + '-' + (v.getMonth() + 1 < 10 ? '0' + (v.getMonth() + 1) : String(v.getMonth() + 1));
    } else {
      s = String(v || '').trim();
    }
    if (s === target) return i + 1;  // 1-based
  }
  return null;
}


// ═══════════════════════════════════════════════════════════════
// СТРОКИ 1–4: ЗАГОЛОВОК / ВЫБОР / ШАПКА / ИНФО
// ═══════════════════════════════════════════════════════════════
function writeMdStaticRows_(dash, monthNum, col25, col26) {
  dash.getRange(MD_R_TITLE, 1, 4, 5).breakApart().clearContent().clearFormat();

  var mFull  = monthNum ? MD_MONTHS_FULL[monthNum - 1].toUpperCase() : '—';
  var mShort = monthNum ? MD_MONTHS_SHORT[monthNum - 1] : '—';

  // Строка 1 — заголовок (тёмно-коричневый, как у «ЕжеМесячный»)
  dash.getRange(MD_R_TITLE, 1, 1, 5).merge()
    .setValue('МЕСЯЧНЫЙ ДАШБОРД — МОНБЛАН — ' + mFull + ' 2026 / 2025')
    .setBackground('#5b2c00').setFontColor('#ffffff')
    .setFontWeight('bold').setFontSize(14)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  dash.setRowHeight(MD_R_TITLE, 44);

  // Строка 2 — выбор месяца
  dash.getRange(MD_R_SEL, 1)
    .setValue('Выберите месяц 2026 (список или 1–12):')
    .setBackground('#fdf0e0').setFontColor('#5b2c00')
    .setFontWeight('bold').setFontSize(14)
    .setHorizontalAlignment('left').setVerticalAlignment('middle');
  var b2 = dash.getRange(MD_R_SEL, 2);
  b2.setValue(monthNum ? MD_MONTHS_FULL[monthNum - 1] : 'апрель');
  b2.setBackground('#fdf0e0').setFontColor('#5b2c00')
    .setFontWeight('bold').setFontSize(14).setHorizontalAlignment('center');
  b2.setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(MD_MONTHS_FULL, true)
      .setAllowInvalid(true)
      .build()
  );
  dash.getRange(MD_R_SEL, 3, 1, 3).setBackground('#fdf0e0');
  dash.setRowHeight(MD_R_SEL, 36);

  // Строка 3 — шапка колонок
  dash.getRange(MD_R_HDR, 1, 1, 5)
    .setValues([['Показатель', mShort + '. 2025', mShort + '. 2026', 'Δ', '●']])
    .setBackground('#7d3c00').setFontColor('#ffffff')
    .setFontWeight('bold').setFontSize(14)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  dash.getRange(MD_R_HDR, 1).setHorizontalAlignment('left');
  dash.setRowHeight(MD_R_HDR, 32);

  // Строка 4 — наличие данных
  var info25 = col25 ? (mShort + ' 2025: колонка ' + mdColLetter_(col25)) : '⚠️ ' + mShort + ' 2025: нет данных';
  var info26 = col26 ? (mShort + ' 2026: колонка ' + mdColLetter_(col26)) : '⚠️ ' + mShort + ' 2026: нет данных';
  dash.getRange(MD_R_DATE, 1).setValue('Источник данных:')
    .setBackground('#fbe9d0').setFontColor('#5b2c00')
    .setFontStyle('italic').setFontSize(13).setVerticalAlignment('middle');
  dash.getRange(MD_R_DATE, 2).setValue(info25)
    .setBackground('#fbe9d0').setFontColor('#5b2c00')
    .setFontSize(12).setHorizontalAlignment('center').setVerticalAlignment('middle');
  dash.getRange(MD_R_DATE, 3).setValue(info26)
    .setBackground('#fbe9d0').setFontColor('#5b2c00')
    .setFontSize(12).setHorizontalAlignment('center').setVerticalAlignment('middle');
  dash.getRange(MD_R_DATE, 4, 1, 2).setBackground('#fbe9d0');
  dash.setRowHeight(MD_R_DATE, 28);

  dash.setFrozenRows(4);
  dash.setColumnWidth(1, 340);
  dash.setColumnWidth(2, 150);
  dash.setColumnWidth(3, 150);
  dash.setColumnWidth(4, 120);
  dash.setColumnWidth(5, 60);
}

function mdColLetter_(n) {
  var s = '';
  while (n > 0) { s = String.fromCharCode(65 + (n - 1) % 26) + s; n = Math.floor((n - 1) / 26); }
  return s;
}


// ═══════════════════════════════════════════════════════════════
// ОЧИСТКА СТРОК ДАННЫХ (5+)
// ═══════════════════════════════════════════════════════════════
function clearMdDataRows_(dash) {
  var lastRow = dash.getLastRow();
  if (lastRow < MD_R_DATA) return;
  dash.getRange(MD_R_DATA, 1, lastRow - MD_R_DATA + 1, 5)
    .clearContent().clearFormat().breakApart();
}


// ═══════════════════════════════════════════════════════════════
// ВСЕ МЕТРИКИ (строки 5+ дашборда ← строки 3–100 «ЕжеМесячный»)
// ═══════════════════════════════════════════════════════════════
function writeMdAllMetricRows_(dash, monthly, col25, col26) {
  var N      = 100;
  var labels = monthly.getRange(1, 1, N, 1).getValues();
  var v25arr = col25 ? monthly.getRange(1, col25, N, 1).getValues() : null;
  var v26arr = col26 ? monthly.getRange(1, col26, N, 1).getValues() : null;

  var dashRow   = MD_R_DATA;
  var lastLabel = '';

  for (var i = 2; i < N; i++) {   // i=2 → строка 3; i=99 → строка 100
    var rowNum = i + 1;
    if (MD_SKIP_ROWS[rowNum]) continue;

    var label = String(labels[i][0] || '').trim();
    var isPct = !!MD_PCT_ROWS[rowNum];
    var v25   = v25arr ? (parseFloat(v25arr[i][0]) || 0) : 0;
    var v26   = v26arr ? (parseFloat(v26arr[i][0]) || 0) : 0;

    if (label) lastLabel = label;
    if (!isPct && !label) continue;

    // Заголовок секции
    if (!isPct && MD_HEADER_ROWS[rowNum]) {
      dash.getRange(dashRow, 1, 1, 5).merge()
        .setValue('  ' + label)
        .setBackground('#8B4513').setFontColor('#ffffff')
        .setFontWeight('bold').setFontSize(14)
        .setHorizontalAlignment('left').setVerticalAlignment('middle');
      dash.setRowHeight(dashRow, 28);
      dashRow++;
      continue;
    }

    var isDecimal = !!MD_DECIMAL_ROWS[rowNum];
    var isEmpty   = (v25 === 0 && v26 === 0);
    var isNoBase  = (!isPct && v25 === 0 && v26 !== 0);

    var delta    = null;
    var hasDelta = false;
    if (isPct) {
      delta = v26 - v25; hasDelta = true;
    } else if (!isEmpty && v25 !== 0) {
      delta = (v26 - v25) / Math.abs(v25); hasDelta = true;
    }

    var bg, dStr, eStr;
    if (isEmpty) {
      bg = null; dStr = '—'; eStr = '⚪';
    } else if (isNoBase) {
      bg = '#c3e6cb'; dStr = 'новое'; eStr = '🟢';
    } else {
      bg   = hasDelta ? getMdBgColor_(delta, isPct) : null;
      dStr = hasDelta ? fmtMdDelta_(delta, isPct)   : '';
      eStr = hasDelta ? getMdSignal_(delta, isPct)   : '';
    }

    var bStr     = fmtMdCell_(v25, isPct, isDecimal);
    var cStr     = fmtMdCell_(v26, isPct, isDecimal);
    var rowLabel = isPct ? ('  % ' + lastLabel) : label;

    var isSectionHL = !!MD_SECTION_HIGHLIGHT_ROWS[rowNum];
    var isInverted  = !!MD_INVERTED_ROWS[rowNum];

    if (hasDelta) {
      bg   = getMdBgColor_(delta, isPct, isInverted);
      dStr = fmtMdDelta_(delta, isPct);
      eStr = getMdSignal_(delta, isPct, isInverted);
    }

    dash.getRange(dashRow, 1, 1, 5).setValues([[rowLabel, bStr, cStr, dStr, eStr]]);

    var rowRng = dash.getRange(dashRow, 1, 1, 5);
    rowRng.setFontSize(14).setVerticalAlignment('middle');

    if (isSectionHL) {
      // Коричневый фон + белый жирный — как заголовок секции, но с данными
      rowRng.setBackground('#8B4513').setFontColor('#ffffff').setFontWeight('bold');
      rowRng.setFontStyle('normal');
    } else if (isPct) {
      rowRng.setFontStyle('italic').setFontColor('#555555').setFontWeight('normal');
      rowRng.setBackground(bg || '#f2f4f8');
    } else {
      rowRng.setBackground(bg || (dashRow % 2 === 0 ? '#f8f9fa' : '#ffffff'));
      dash.getRange(dashRow, 1).setFontColor('#000000').setFontStyle('normal').setFontWeight('normal');
    }

    dash.getRange(dashRow, 1).setHorizontalAlignment('left');
    dash.getRange(dashRow, 2, 1, 2).setHorizontalAlignment('right');
    dash.getRange(dashRow, 4, 1, 2).setHorizontalAlignment('center');
    if (!isSectionHL && hasDelta && bg) dash.getRange(dashRow, 4).setFontWeight('bold');

    dash.setRowHeight(dashRow, isSectionHL ? 30 : (isPct ? 24 : 28));
    dashRow++;
  }

  return dashRow;
}


// ═══════════════════════════════════════════════════════════════
// СИГНАЛЫ МЕСЯЦА
// ═══════════════════════════════════════════════════════════════
function computeMdSignals_(monthly, col25, col26) {
  var N      = 100;
  var labels = monthly.getRange(1, 1, N, 1).getValues();
  var v25arr = col25 ? monthly.getRange(1, col25, N, 1).getValues() : null;
  var v26arr = col26 ? monthly.getRange(1, col26, N, 1).getValues() : null;

  var result       = [];
  var lastLabel    = '';
  var sectionLabel = '';

  for (var i = 2; i < N; i++) {
    var rowNum = i + 1;
    if (MD_SKIP_ROWS[rowNum]) continue;

    var label = String(labels[i][0] || '').trim();
    var isPct = !!MD_PCT_ROWS[rowNum];
    if (label) lastLabel = label;
    if ((MD_HEADER_ROWS[rowNum] || MD_SECTION_HIGHLIGHT_ROWS[rowNum]) && label) sectionLabel = label;

    var rawLabel = isPct ? ('% ' + lastLabel) : label;
    if (!rawLabel) continue;

    // Добавляем префикс секции, если текущая строка — не сама секция
    var isSection          = !!(MD_HEADER_ROWS[rowNum] || MD_SECTION_HIGHLIGHT_ROWS[rowNum]);
    var isDirectSectionPct = isPct && sectionLabel === lastLabel;
    var dispLabel = (sectionLabel && !isSection && !isDirectSectionPct)
      ? (sectionLabel + ': ' + rawLabel)
      : rawLabel;

    var v25 = v25arr ? (parseFloat(v25arr[i][0]) || 0) : 0;
    var v26 = v26arr ? (parseFloat(v26arr[i][0]) || 0) : 0;
    if (v25 === 0 && v26 === 0) continue;

    var delta;
    if (isPct) {
      delta = v26 - v25;
    } else {
      if (v25 === 0) continue;
      delta = (v26 - v25) / Math.abs(v25);
    }

    var isInverted = !!MD_INVERTED_ROWS[rowNum];
    var sig = getMdSignal_(delta, isPct, isInverted);
    if (sig === '⚪') continue;
    result.push({label: dispLabel, delta: delta, isPct: isPct, signal: sig, isInverted: isInverted});
  }
  return result;
}

function writeMdSignalsSection_(dash, startRow, signals, monthNum) {
  var mName  = monthNum ? MD_MONTHS_FULL[monthNum - 1].toUpperCase() : '?';
  var red    = signals.filter(function(d){return d.signal==='🔴';}).sort(function(a,b){return a.delta-b.delta;}).slice(0,5);
  var yellow = signals.filter(function(d){return d.signal==='🟡';}).sort(function(a,b){return a.delta-b.delta;}).slice(0,5);
  var green  = signals.filter(function(d){return d.signal==='🟢';}).sort(function(a,b){return b.delta-a.delta;}).slice(0,5);

  var row = startRow;
  dash.getRange(row,1,1,5).merge()
    .setValue('🚨  СИГНАЛЫ МЕСЯЦА: ' + mName + '  (топ-5 по каждой зоне)')
    .setBackground('#2c2c2c').setFontColor('#ffffff')
    .setFontWeight('bold').setFontSize(14)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  dash.setRowHeight(row, 34); row++;

  row = writeMdZone_(dash, row, '🔴  ПРОБЛЕМНЫЕ ЗОНЫ  (> 10% или > 5 п.п. снижения)',  '#b43232','#fdd',    '#c0392b', red);
  row = writeMdZone_(dash, row, '🟡  ТРЕБУЮТ ВНИМАНИЯ  (3–10% или 1–5 п.п. снижения)', '#9a6b00','#fff3cd', '#856404', yellow);
  row = writeMdZone_(dash, row, '🟢  РАБОТАЕТ ХОРОШО  (> 5% или > 3 п.п. роста)',      '#1e6641','#d4edda', '#155724', green);
  return row;
}

function writeMdZone_(dash, row, hdr, hdrBg, itemBg, valFg, items) {
  dash.getRange(row,1,1,5).merge().setValue(hdr)
    .setBackground(hdrBg).setFontColor('#ffffff')
    .setFontWeight('bold').setFontSize(14).setVerticalAlignment('middle');
  dash.setRowHeight(row, 30); row++;
  if (!items.length) {
    dash.getRange(row,1,1,5).merge().setValue('— нет')
      .setBackground(itemBg).setFontSize(14).setHorizontalAlignment('center');
    dash.setRowHeight(row, 28); row++;
  } else {
    items.forEach(function(d) {
      dash.getRange(row,1,1,4).merge().setValue(d.label)
        .setBackground(itemBg).setFontSize(14)
        .setHorizontalAlignment('left').setVerticalAlignment('middle');
      dash.getRange(row,5).setValue(fmtMdDelta_(d.delta, d.isPct))
        .setBackground(itemBg).setFontSize(14)
        .setHorizontalAlignment('center').setFontWeight('bold').setFontColor(valFg);
      dash.setRowHeight(row, 28); row++;
    });
  }
  return row;
}


// ═══════════════════════════════════════════════════════════════
// AI-ЗАГЛУШКА
// ═══════════════════════════════════════════════════════════════
function writeMdAiSkeleton_(dash, startRow, monthNum) {
  var mName = monthNum ? MD_MONTHS_FULL[monthNum - 1] : '?';
  var ph    = '← Нажмите «🔶 Монблан» → «Обновить AI-анализ (месяц)»';
  function sec(r, hdr) {
    dash.getRange(r,1,1,5).merge().setValue(hdr)
      .setBackground('#3d3d3d').setFontColor('#ffffff')
      .setFontWeight('bold').setFontSize(14).setVerticalAlignment('middle');
    dash.setRowHeight(r, 30);
    for (var i = 0; i < 3; i++) {
      dash.getRange(r+1+i,1,1,5).merge().setValue(ph)
        .setBackground('#f5f5f5').setFontColor('#888888')
        .setFontStyle('italic').setFontSize(14)
        .setWrap(true).setHorizontalAlignment('center').setVerticalAlignment('middle');
      dash.setRowHeight(r+1+i, 30);
    }
  }
  sec(startRow,      '🔍  ВОЗМОЖНЫЕ ПРИЧИНЫ  (AI — ' + mName + ' 2026 vs 2025)');
  sec(startRow + 5,  '💡  РЕКОМЕНДАЦИИ  (AI)');
  sec(startRow + 10, '📋  УПРАВЛЕНЧЕСКИЕ ВЫВОДЫ  (AI)');
}


// ═══════════════════════════════════════════════════════════════
// AI-АНАЛИЗ (Groq)
// ═══════════════════════════════════════════════════════════════
function runMonthlyAiAnalysis() {
  var ss      = SpreadsheetApp.getActiveSpreadsheet();
  var dash    = getMdDashSheet_(ss);
  var monthly = getMdMonthlySheet_(ss);
  if (!dash || !monthly) return;

  var monthNum = parseMdMonth_(dash.getRange(MD_R_SEL, 2).getValue());
  if (!monthNum) { SpreadsheetApp.getUi().alert('Выберите месяц в B2'); return; }

  var col25   = findMdMonthCol_(monthly, 2025, monthNum);
  var col26   = findMdMonthCol_(monthly, 2026, monthNum);
  var signals = computeMdSignals_(monthly, col25, col26);

  if (!signals.length) { SpreadsheetApp.getUi().alert('Нет значимых отклонений для анализа.'); return; }

  ss.toast('Запрашиваем AI (Groq)...', '🔶 Монблан', 120);

  var red    = signals.filter(function(d){return d.signal==='🔴';});
  var yellow = signals.filter(function(d){return d.signal==='🟡';});
  var green  = signals.filter(function(d){return d.signal==='🟢';});

  var aiText = callMdGroq_(buildMdPrompt_(monthNum, red, yellow, green));
  if (!aiText) return;

  var aiRow = getMdAiStartRow_() || (MD_R_DATA + 120);
  writeMdAiBlock_(dash, aiRow, monthNum, aiText);
  ss.toast('✅ AI-анализ готов', '🔶 Монблан', 5);
}

function buildMdPrompt_(monthNum, red, yellow, green) {
  var mName = MD_MONTHS_FULL[monthNum - 1];
  function lst(arr) {
    return arr.length
      ? arr.map(function(d){return '• ' + d.label + ': ' + fmtMdDelta_(d.delta, d.isPct);}).join('\n')
      : '—';
  }
  return 'Ты — аналитик ресторанного бизнеса. Ресторан «Монблан», горнолыжный курорт Губаха.\n\n' +
    '⚠️ ВАЖНО: для показателей «Фудкост» снижение = ХОРОШО (ниже затраты), рост = ПЛОХО. Учитывай это при анализе.\n\n' +
    mName + ' 2026 vs ' + mName + ' 2025 (год к году):\n\n' +
    '🔴 ПРОБЛЕМЫ:\n' + lst(red) + '\n\n🟡 ВНИМАНИЕ:\n' + lst(yellow) + '\n\n🟢 РАСТУТ:\n' + lst(green) + '\n\n' +
    'Дай СТРОГО 3 блока по 3 пункта. Каждый пункт — одно предложение (макс 15 слов). Без вступлений.\n\n' +
    'БЛОК 1: ВОЗМОЖНЫЕ ПРИЧИНЫ ПРОБЛЕМ\n1. ...\n2. ...\n3. ...\n\n' +
    'БЛОК 2: РЕКОМЕНДАЦИИ\n1. ...\n2. ...\n3. ...\n\n' +
    'БЛОК 3: УПРАВЛЕНЧЕСКИЕ ВЫВОДЫ\n1. ...\n2. ...\n3. ...';
}

function writeMdAiBlock_(dash, startRow, monthNum, aiText) {
  var mName  = MD_MONTHS_FULL[monthNum - 1];
  var blocks = parseMdAiBlocks_(aiText);
  dash.getRange(startRow, 1, 15, 5).clearContent().clearFormat().breakApart();
  function sec(r, hdr, items) {
    dash.getRange(r,1,1,5).merge().setValue(hdr)
      .setBackground('#3d3d3d').setFontColor('#ffffff')
      .setFontWeight('bold').setFontSize(14).setVerticalAlignment('middle');
    for (var i = 0; i < 3; i++) {
      dash.getRange(r+1+i,1,1,5).merge().setValue(items[i] || '—')
        .setBackground('#f8f9fa').setFontColor('#212529')
        .setFontSize(14).setWrap(true).setVerticalAlignment('middle');
    }
  }
  sec(startRow,      '🔍  ВОЗМОЖНЫЕ ПРИЧИНЫ  (AI — ' + mName + ' 2026 vs 2025)', blocks.causes);
  sec(startRow + 5,  '💡  РЕКОМЕНДАЦИИ  (AI)', blocks.recs);
  sec(startRow + 10, '📋  УПРАВЛЕНЧЕСКИЕ ВЫВОДЫ  (AI)', blocks.mgmt);
}

function callMdGroq_(prompt) {
  var key = PropertiesService.getScriptProperties().getProperty('ROUTERAI_API_KEY');
  if (!key) {
    SpreadsheetApp.getUi().alert('ROUTERAI_API_KEY не задан в Script Properties.');
    return null;
  }
  try {
    var resp = UrlFetchApp.fetch('https://routerai.ru/api/v1/chat/completions', {
      method: 'post', muteHttpExceptions: true,
      headers: {'Content-Type':'application/json','Authorization':'Bearer ' + key},
      payload: JSON.stringify({
        model: 'deepseek/deepseek-v4-pro', max_tokens: 1500,
        messages: [{role: 'user', content: prompt}]
      }),
    });
    var code = resp.getResponseCode();
    if (code !== 200) {
      var raw = resp.getContentText();
      Logger.log('RouterAI HTTP ' + code + ': ' + raw);
      SpreadsheetApp.getUi().alert(
        'RouterAI API вернул ошибку ' + code + '.\n' +
        (code === 429 ? 'Превышен лимит запросов — подождите 1–2 минуты.' :
         code === 401 ? 'Неверный ROUTERAI_API_KEY — проверьте Script Properties.' :
         'Подробности в Logs (Apps Script → Выполнение).')
      );
      return null;
    }
    return JSON.parse(resp.getContentText()).choices[0].message.content;
  } catch(e) {
    Logger.log('RouterAI exception: ' + e.message);
    SpreadsheetApp.getUi().alert('RouterAI: ошибка сети — ' + e.message);
    return null;
  }
}

function parseMdAiBlocks_(text) {
  function extract(t) {
    var items = [];
    (t||'').split('\n').forEach(function(l) {
      l = l.trim();
      var m = l.match(/^[1-3][\.\)]\s*(.+)/) || l.match(/^[•\-\*]\s*(.+)/);
      if (m) { items.push(m[1]); return; }
      if (l.length > 5 && !/^(БЛОК|BLOCK|ВОЗМОЖНЫЕ|РЕКОМЕНДАЦИИ|УПРАВЛЕНЧЕСКИЕ)/i.test(l)) items.push(l);
    });
    return items.slice(0, 3);
  }
  var parts = text.split(/БЛОК\s*[123][\:\.]?\s*/i);
  if (parts.length >= 4) return {causes: extract(parts[1]), recs: extract(parts[2]), mgmt: extract(parts[3])};
  var t = Math.floor(text.length / 3);
  return {causes: extract(text.slice(0,t)), recs: extract(text.slice(t,2*t)), mgmt: extract(text.slice(2*t))};
}


// ═══════════════════════════════════════════════════════════════
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ═══════════════════════════════════════════════════════════════
// isInverted=true для фудкоста: снижение = хорошо, рост = плохо
function getMdSignal_(delta, isPct, isInverted) {
  var d = isInverted ? -delta : delta;
  if (isPct) {
    if (d < MD_RED_PP)    return '🔴';
    if (d < MD_YELLOW_PP) return '🟡';
    if (d > MD_GREEN_PP)  return '🟢';
    return '⚪';
  }
  if (d < MD_RED)    return '🔴';
  if (d < MD_YELLOW) return '🟡';
  if (d > MD_GREEN)  return '🟢';
  return '⚪';
}

function getMdBgColor_(delta, isPct, isInverted) {
  var d = isInverted ? -delta : delta;
  if (isPct) {
    if (d < MD_RED_PP)    return '#f5c6cb';
    if (d < MD_YELLOW_PP) return '#ffeaa7';
    if (d > MD_GREEN_PP)  return '#c3e6cb';
    return null;
  }
  if (d < MD_RED)    return '#f5c6cb';
  if (d < MD_YELLOW) return '#ffeaa7';
  if (d > MD_GREEN)  return '#c3e6cb';
  return null;
}

function fmtMdDelta_(delta, isPct) {
  var sign = delta > 0 ? '+' : '';
  if (isPct) return sign + (Math.round(delta * 1000) / 10) + ' п.п.';
  return sign + (Math.round(delta * 1000) / 10) + '%';
}

function fmtMdCell_(v, isPct, isDecimal) {
  if (v === null || v === undefined) return '—';
  if (isPct) return (Math.round(v * 1000) / 10) + '%';
  if (!v) return '0';
  if (isDecimal) {
    var s = (Math.round(v * 10) / 10).toFixed(1).split('.');
    return s[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + '.' + s[1];
  }
  return Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

function saveMdAiStartRow_(row) {
  PropertiesService.getScriptProperties().setProperty('MD_AI_START_ROW', String(row));
}
function getMdAiStartRow_() {
  var v = PropertiesService.getScriptProperties().getProperty('MD_AI_START_ROW');
  return v ? parseInt(v) : null;
}
function getMdDashSheet_(ss) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === MD_DASH_GID) return sheets[i];
  }
  return ss.getSheetByName('Дашборд месяц') || ss.getSheetByName('Месяц');
}
function getMdMonthlySheet_(ss) {
  return ss.getSheetByName(MD_SHEET_NAME);
}
