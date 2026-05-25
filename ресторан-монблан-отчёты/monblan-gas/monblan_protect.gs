/**
 * ЗАЩИТА СТРУКТУРЫ ЛИСТА МОНБЛАН
 *
 * Столбец A содержит названия метрик — их нельзя менять вручную.
 * Этот файл:
 *   1. protectColumnA()        — ставит защиту на столбец A через Sheets API
 *   2. onEdit(e)               — onEdit-триггер: восстанавливает ячейку A если её изменили
 *   3. restoreColumnAStructure() — ручной сброс всех меток в столбце A
 *   4. removeColumnAProtection() — снять защиту (нужна для пересборки листа)
 *
 * Инструкция:
 *   1. Откройте Apps Script целевой таблицы
 *   2. Вставьте этот файл рядом с monblan_config.gs и monblan_build.gs
 *   3. Запустите protectColumnA() один раз — защита сохранится навсегда
 *   4. Установите триггер onEdit вручную:
 *      Триггеры → Добавить триггер → onEdit → При изменении
 */

// ═══════════════════════════════════════════════════════════════
// ЭТАЛОННЫЕ МЕТКИ СТОЛБЦА A (96 строк, порядок совпадает с MB_ROWS)
// Хранятся отдельно, чтобы работать без MB_ROWS в контексте триггера
// ═══════════════════════════════════════════════════════════════
var MB_LABELS = [
  'Год',                               // 1
  'Неделя',                            // 2
  'Монблан',                           // 3
  'Выручка всего и по категориям',     // 4
  'Кухня',                             // 5
  '',                                  // 6  — % Кухня
  'Бар',                               // 7
  '',                                  // 8  — % Бар
  'Выручка день - вечер',              // 9
  'Утро (9:00 - 11:00)',               // 10
  '',                                  // 11 — % Утро
  'День (11:00 - 17:00)',              // 12
  '',                                  // 13 — % День
  'Вечер (17:00 - 21:00)',             // 14
  '',                                  // 15 — % Вечер
  'Средняя выручка по дням недели',    // 16
  'Понедельник',                       // 17
  '',                                  // 18
  'Вторник',                           // 19
  '',                                  // 20
  'Среда',                             // 21
  '',                                  // 22
  'Четверг',                           // 23
  '',                                  // 24
  'Пятница',                           // 25
  '',                                  // 26
  'Суббота',                           // 27
  '',                                  // 28
  'Воскресенье',                       // 29
  '',                                  // 30
  'Кол-во гостей',                     // 31
  'Утро (9:00 - 11:00)',               // 32
  '',                                  // 33
  'День (11:00 - 17:00)',              // 34
  '',                                  // 35
  'Вечер (17:00 - 21:00)',             // 36
  '',                                  // 37
  'Средний чек на гостя',              // 38
  'Утро (9:00 - 11:00)',               // 39
  'День (11:00 - 17:00)',              // 40
  'Вечер (17:00 - 21:00)',             // 41
  'Кол-во чеков',                      // 42
  'Утро (9:00 - 11:00)',               // 43
  'День (11:00 - 17:00)',              // 44
  'Вечер (17:00 - 21:00)',             // 45
  'Количество блюд',                   // 46
  'Средний счет',                      // 47
  'Средний чек на блюдо',              // 48
  'Средний чек на гостя (кухня)',      // 49
  'Средний чек на гостя (бар)',        // 50
  'Ср. кол-во блюд на гостя',         // 51
  'Оборачиваемость столов',            // 52
  'Утро (9:00 - 11:00)',               // 53
  'День (11:00 - 17:00)',              // 54
  'Вечер (17:00 - 21:00)',             // 55
  'Оборачиваемость пос. мест',         // 56
  'Утро (9:00 - 11:00)',               // 57
  'День (11:00 - 17:00)',              // 58
  'Вечер (17:00 - 21:00)',             // 59
  'Вклад в выручку группы гостей',     // 60
  'Выручка по чекам 1 гость',          // 61
  '',                                  // 62
  'Выручка по чекам 2 гостя',          // 63
  '',                                  // 64
  'Выручка по чекам 3+ гостя',         // 65
  '',                                  // 66
  'Коэффициент групповой лояльности',  // 67
  'Кол-во чеков 1 гость',              // 68
  '',                                  // 69
  'Кол-во чеков 2 гостя',              // 70
  '',                                  // 71
  'Кол-во чеков 3 + гостя',            // 72
  '',                                  // 73
  'Градация чеков по сумме, выручка',  // 74
  '0-500 руб.',                        // 75
  '',                                  // 76
  '500-1000 руб.',                     // 77
  '',                                  // 78
  '1000-1500 руб.',                    // 79
  '',                                  // 80
  '1500-3000 руб.',                    // 81
  '',                                  // 82
  '3000-5000 руб.',                    // 83
  '',                                  // 84
  '5000 + руб',                        // 85
  '',                                  // 86
  'Столов',                            // 87
  'Посадочных мест',                   // 88
  '',                                  // 89
  'Мероприятия',                       // 90
  'Завтраки (кол-во по гостям)',       // 91
  'Количество мероприятий',            // 92
  'Выручка мероприятий',               // 93
  'Количество гостей',                 // 94
  'Средний чек на гостя',              // 95
  'Средний чек на мероприятие',        // 96
];

// ═══════════════════════════════════════════════════════════════
// 1. ПОСТАВИТЬ ЗАЩИТУ НА СТОЛБЕЦ A
// Запустите один раз из редактора Apps Script.
// ═══════════════════════════════════════════════════════════════
function protectColumnA() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = getMonblanSheetForProtect_(ss);
  if (!sh) { SpreadsheetApp.getUi().alert('Лист Монблан не найден'); return; }

  // Снимаем старую защиту столбца A (если была)
  var existing = sh.getProtections(SpreadsheetApp.ProtectionType.RANGE);
  for (var i = 0; i < existing.length; i++) {
    var desc = existing[i].getDescription();
    if (desc === 'MB_COLUMN_A_STRUCTURE') existing[i].remove();
  }

  // Ставим новую защиту на A1:A96
  var protection = sh.getRange('A1:A96').protect();
  protection.setDescription('MB_COLUMN_A_STRUCTURE');
  protection.setWarningOnly(false);

  // Убираем из редакторов всех, кроме владельца таблицы
  var owner = ss.getOwner();
  if (owner) {
    protection.addEditor(owner);
    var editors = protection.getEditors();
    for (var j = 0; j < editors.length; j++) {
      if (editors[j].getEmail() !== owner.getEmail()) {
        protection.removeEditor(editors[j]);
      }
    }
  }

  SpreadsheetApp.getUi().alert(
    '✅ Столбец A защищён!\n\n' +
    'Диапазон A1:A96 заблокирован от редактирования.\n' +
    'Редактор: только владелец таблицы.\n\n' +
    'Также установите триггер onEdit:\n' +
    'Триггеры → Добавить триггер → onEdit → При изменении'
  );
}

// ═══════════════════════════════════════════════════════════════
// 2. ONEIT-ТРИГГЕР — ВОССТАНАВЛИВАЕТ МЕТКУ ПРИ ИЗМЕНЕНИИ
// Установите вручную: Триггеры → onEdit → При изменении
// Срабатывает даже если защита была обойдена (например, владельцем).
// ═══════════════════════════════════════════════════════════════
function onEdit(e) {
  if (!e) return;
  var range = e.range;

  // Интересует только столбец A (номер 1)
  if (range.getColumn() !== 1) return;

  // Проверяем что это лист Монблан
  var sh = range.getSheet();
  if (sh.getSheetId() !== 2051236241 && sh.getName() !== 'Монблан') return;

  var startRow = range.getRow();
  var numRows  = range.getNumRows();

  // Восстанавливаем только строки в диапазоне 1–96
  var restoredValues = [];
  for (var i = 0; i < numRows; i++) {
    var rowIdx = startRow + i - 1;  // 0-based индекс в MB_LABELS
    if (rowIdx >= 0 && rowIdx < MB_LABELS.length) {
      restoredValues.push([MB_LABELS[rowIdx]]);
    } else {
      restoredValues.push([e.oldValue !== undefined ? e.oldValue : '']);
    }
  }

  // Записываем эталонные значения обратно
  sh.getRange(startRow, 1, numRows, 1).setValues(restoredValues);
}

// ═══════════════════════════════════════════════════════════════
// 3. РУЧНОЕ ВОССТАНОВЛЕНИЕ ВСЕЙ СТРУКТУРЫ СТОЛБЦА A
// Используйте если что-то сломалось — сбрасывает все 96 меток.
// ═══════════════════════════════════════════════════════════════
function restoreColumnAStructure() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = getMonblanSheetForProtect_(ss);
  if (!sh) { SpreadsheetApp.getUi().alert('Лист Монблан не найден'); return; }

  var labels = MB_LABELS.map(function(l) { return [l]; });
  sh.getRange(1, 1, 96, 1).setValues(labels);

  SpreadsheetApp.getUi().alert('✅ Структура столбца A восстановлена (96 строк)');
}

// ═══════════════════════════════════════════════════════════════
// 4. СНЯТЬ ЗАЩИТУ (нужна перед buildMonblanSheet)
// ═══════════════════════════════════════════════════════════════
function removeColumnAProtection() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = getMonblanSheetForProtect_(ss);
  if (!sh) return;

  var protections = sh.getProtections(SpreadsheetApp.ProtectionType.RANGE);
  var removed = 0;
  for (var i = 0; i < protections.length; i++) {
    if (protections[i].getDescription() === 'MB_COLUMN_A_STRUCTURE') {
      protections[i].remove();
      removed++;
    }
  }
  SpreadsheetApp.getUi().alert('Защита снята (' + removed + ' правило). Теперь можно запустить buildMonblanSheet().');
}

// ═══════════════════════════════════════════════════════════════
// 5. ВОССТАНОВЛЕНИЕ ЧИСЛОВЫХ ФОРМАТОВ ЛИСТА МОНБЛАН
// Запустите из редактора Apps Script если форматы сбились.
// Применяет: # ##0 для числовых строк, 0% для процентных строк.
// ═══════════════════════════════════════════════════════════════
function fixFormatsMonblan() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = getMonblanSheetForProtect_(ss);
  if (!sh) { SpreadsheetApp.getUi().alert('Лист Монблан не найден'); return; }

  var sheetId = sh.getSheetId();

  // Строки с форматом 0% (остальные 4-96 → # ##0)
  var pctRows = [6,8,11,13,15,18,20,22,24,26,28,30,
                 33,35,37,62,64,66,69,71,73,76,78,80,82,84,86];
  var pctSet = {};
  pctRows.forEach(function(r) { pctSet[r] = true; });

  var fmtNumber  = { numberFormat: { type: 'NUMBER',  pattern: '#,##0'   } };
  var fmtDecimal = { numberFormat: { type: 'NUMBER',  pattern: '#,##0.0' } };
  var fmtPercent = { numberFormat: { type: 'PERCENT', pattern: '0%'      } };

  // Строки с одним знаком после запятой (Оборачиваемость столов/мест)
  var decimalSet = {52:1, 53:1, 54:1, 55:1, 56:1, 57:1, 58:1, 59:1};

  var requests = [];
  for (var row = 4; row <= 96; row++) {
    var fmt = pctSet[row] ? fmtPercent : (decimalSet[row] ? fmtDecimal : fmtNumber);
    requests.push({
      repeatCell: {
        range: {
          sheetId:          sheetId,
          startRowIndex:    row - 1,
          endRowIndex:      row,
          startColumnIndex: 1,        // столбец B
          endColumnIndex:   500,
        },
        cell: { userEnteredFormat: fmt },
        fields: 'userEnteredFormat.numberFormat',
      }
    });
  }

  // Шлём по 50 запросов
  for (var i = 0; i < requests.length; i += 50) {
    Sheets.Spreadsheets.batchUpdate(
      { requests: requests.slice(i, i + 50) },
      ss.getId()
    );
  }

  SpreadsheetApp.getUi().alert(
    '✅ Форматы восстановлены!\n\n' +
    '• Числовые строки (4–96): # ##0  (1 000 000)\n' +
    '• Процентные строки: 0%  (' + pctRows.join(', ') + ')'
  );
}

// ═══════════════════════════════════════════════════════════════
// 6. ПОЛНОЕ ВОССТАНОВЛЕНИЕ — столбец A + форматы за один клик
// ═══════════════════════════════════════════════════════════════
function restoreAll() {
  restoreColumnAStructure();
  fixFormatsMonblan();
}

// ═══════════════════════════════════════════════════════════════
// ВСПОМОГАТЕЛЬНАЯ — ПОИСК ЛИСТА
// ═══════════════════════════════════════════════════════════════
function getMonblanSheetForProtect_(ss) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === 2051236241) return sheets[i];
  }
  return ss.getSheetByName('Монблан');
}
