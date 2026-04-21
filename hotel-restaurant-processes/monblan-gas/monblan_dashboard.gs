/**
 * МОНБЛАН — ДАШБОРД: ДИНАМИКА + AI-АНАЛИЗ
 *
 * ИНСТРУКЦИЯ ПО УСТАНОВКЕ:
 *
 * 1. Откройте таблицу Google Sheets.
 *    В верхнем меню нажмите «Расширения» → «Apps Script».
 *    Откроется редактор скриптов в новой вкладке браузера.
 *
 * 2. Создайте новый файл скрипта:
 *    В левой панели редактора нажмите «+» рядом с надписью «Файлы».
 *    Выберите «Скрипт». Назовите файл «monblan_dashboard» и нажмите Enter.
 *    В центральной области появится пустой файл с текстом «function myFunction() {}».
 *    Выделите весь этот текст (Ctrl+A) и удалите его.
 *    Скопируйте весь код из файла monblan_dashboard.gs и вставьте сюда (Ctrl+V).
 *    Нажмите значок дискеты 💾 (или Ctrl+S) — «Сохранить проект».
 *
 * 3. Получите бесплатный API-ключ Google Gemini:
 *    Откройте в браузере сайт: aistudio.google.com
 *    Войдите с вашим аккаунтом Google.
 *    Нажмите кнопку «Get API key» (синяя кнопка в левом меню).
 *    Нажмите «Create API key» → выберите проект → нажмите «Create API key in existing project».
 *    Скопируйте ключ (начинается с AIza...).
 *
 * 4. Добавьте API-ключ в скрипт:
 *    Вернитесь в редактор Apps Script.
 *    В левой панели редактора нажмите значок шестерёнки ⚙️ «Настройки проекта».
 *    Прокрутите вниз до раздела «Свойства скрипта».
 *    Нажмите «Добавить свойство».
 *    В поле «Свойство» напишите:  GEMINI_API_KEY
 *    В поле «Значение» вставьте ваш ключ:  AIza...
 *    Нажмите «Сохранить свойства скрипта».
 *    Вернитесь на вкладку редактора (стрелка назад или вкладка «Редактор»).
 *
 * 5. Установите триггер (один раз):
 *    В верхней панели редактора найдите выпадающий список функций
 *    (там написано «myFunction» или название последней запущенной функции).
 *    Нажмите на него и выберите «installTrigger».
 *    Нажмите кнопку ▶ «Выполнить» (треугольник).
 *    При первом запуске появится окно «Требуется авторизация» —
 *    нажмите «Проверить разрешения», выберите ваш аккаунт Google,
 *    нажмите «Дополнительно» → «Перейти на страницу monblan_dashboard»
 *    → «Разрешить». Скрипт запустится и покажет уведомление «✅ Триггер установлен».
 *
 * 6. Как пользоваться:
 *    Вернитесь в таблицу Google Sheets (вкладка браузера с таблицей).
 *    Обновите страницу (F5) — в верхнем меню появится пункт «🔶 Монблан».
 *    Выберите неделю в ячейке B2 листа «Дашборд» (выпадающий список 1–5).
 *    Нажмите «🔶 Монблан» → «Обновить AI-анализ».
 *    Подождите 10–20 секунд — блоки Причины / Рекомендации / Выводы заполнятся.
 *
 * Что делает:
 *   — При изменении B2 (выбор недели) обновляет заголовки колонок
 *   — По кнопке вызывает Google Gemini (бесплатно) для анализа
 *     отклонений и заполняет блоки Причины / Рекомендации / Выводы
 */

var DASH_GID   = 1669207980;
var DASH_NAME  = 'Дашборд';

// Строки дашборда
var R = {
  SEL:    2,   // ячейка B2 — выбор недели
  D0:     6,   // первая строка KPI
  DN:    17,   // последняя строка KPI
  COL_D: 4,    // колонка D (Δ%)
  COL_A: 1,    // колонка A (метки)

  C1: 34, C2: 35, C3: 36,  // Причины
  R1: 38, R2: 39, R3: 40,  // Рекомендации
  M1: 42, M2: 43, M3: 44,  // Выводы
};

// ═══════════════════════════════════════════════════════════════
// УСТАНОВКА ТРИГГЕРА — запустите один раз
// ═══════════════════════════════════════════════════════════════
function installTrigger() {
  // Удаляем старые триггеры onEdit если есть
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === 'onEditDashboard') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('onEditDashboard')
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onEdit()
    .create();
  SpreadsheetApp.getUi().alert('✅ Триггер установлен!\n\nТеперь при изменении B2 будут обновляться заголовки.');
}

// ═══════════════════════════════════════════════════════════════
// КАСТОМНОЕ МЕНЮ
// ═══════════════════════════════════════════════════════════════
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('🔶 Монблан')
    .addItem('Обновить AI-анализ', 'runAiAnalysis')
    .addSeparator()
    .addItem('Установить триггер onEdit', 'installTrigger')
    .addToUi();
}

// ═══════════════════════════════════════════════════════════════
// ONEIT ТРИГГЕР — обновляет заголовки при смене недели
// ═══════════════════════════════════════════════════════════════
function onEditDashboard(e) {
  if (!e) return;
  var rng = e.range;
  if (rng.getSheet().getSheetId() !== DASH_GID) return;
  if (rng.getRow() !== R.SEL || rng.getColumn() !== 2) return;

  // Небольшая задержка чтобы formulas пересчитались
  Utilities.sleep(500);
}

// ═══════════════════════════════════════════════════════════════
// ГЛАВНАЯ ФУНКЦИЯ — AI-АНАЛИЗ
// ═══════════════════════════════════════════════════════════════
function runAiAnalysis() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = getDashSheet_(ss);
  if (!sh) { SpreadsheetApp.getUi().alert('Лист Дашборд не найден'); return; }

  var week = sh.getRange(R.SEL, 2).getValue();
  if (!week || isNaN(week)) {
    SpreadsheetApp.getUi().alert('Выберите неделю в ячейке B2 (1–5)');
    return;
  }

  ss.toast('Собираем данные...', 'AI-анализ', 60);

  // Читаем текущие отклонения
  var deviations = readDeviations_(sh);
  if (deviations.length === 0) {
    SpreadsheetApp.getUi().alert('Нет данных для анализа. Убедитесь что данные загружены.');
    return;
  }

  var red    = deviations.filter(function(d) { return d.delta < -0.1; });
  var yellow = deviations.filter(function(d) { return d.delta >= -0.1 && d.delta < -0.03; });
  var green  = deviations.filter(function(d) { return d.delta > 0.05; });

  ss.toast('Запрашиваем AI...', 'AI-анализ', 120);

  var prompt = buildPrompt_(week, red, yellow, green);
  var aiText = callGemini_(prompt);

  if (!aiText) {
    SpreadsheetApp.getUi().alert('Ошибка Groq API. Проверьте GROQ_API_KEY в свойствах скрипта.\n\nПолучить бесплатный ключ: console.groq.com');
    return;
  }

  writeAiResults_(sh, aiText);
  ss.toast('✅ Готово!', 'AI-анализ', 5);
}

// ═══════════════════════════════════════════════════════════════
// ЧТЕНИЕ ОТКЛОНЕНИЙ ИЗ КОЛОНОК A И D
// ═══════════════════════════════════════════════════════════════
function readDeviations_(sh) {
  var deviations = [];
  var numRows = R.DN - R.D0 + 1;
  var labelsRange  = sh.getRange(R.D0, R.COL_A, numRows, 1).getValues();
  var deltasRange  = sh.getRange(R.D0, R.COL_D, numRows, 1).getValues();
  var vals2025     = sh.getRange(R.D0, 2, numRows, 1).getValues();
  var vals2026     = sh.getRange(R.D0, 3, numRows, 1).getValues();

  for (var i = 0; i < numRows; i++) {
    var label = labelsRange[i][0];
    var delta = deltasRange[i][0];
    var v25   = vals2025[i][0];
    var v26   = vals2026[i][0];
    if (!label || delta === '—' || delta === '' || isNaN(delta)) continue;
    deviations.push({
      label: label,
      delta: parseFloat(delta),
      v2025: v25,
      v2026: v26,
    });
  }
  return deviations;
}

// ═══════════════════════════════════════════════════════════════
// ПОСТРОЕНИЕ ПРОМПТА
// ═══════════════════════════════════════════════════════════════
function buildPrompt_(week, red, yellow, green) {
  function fmtList(arr) {
    return arr.map(function(d) {
      var sign = d.delta > 0 ? '+' : '';
      return '• ' + d.label + ': ' + sign + Math.round(d.delta * 100) + '%' +
             ' (2025: ' + Math.round(d.v2025) + ', 2026: ' + Math.round(d.v2026) + ')';
    }).join('\n') || '—';
  }

  return 'Ты — аналитик ресторанного бизнеса. Ресторан «Монблан», горнолыжный курорт Губаха, Пермский край.\n\n' +
    'Неделя ' + week + ' / 2026 vs неделя ' + week + ' / 2025:\n\n' +
    '🔴 УПАЛИ > 10%:\n' + fmtList(red) + '\n\n' +
    '🟡 УПАЛИ 3-10%:\n' + fmtList(yellow) + '\n\n' +
    '🟢 ВЫРОСЛИ > 5%:\n' + fmtList(green) + '\n\n' +
    'Дай СТРОГО 3 блока по 3 пункта. Каждый пункт — одно предложение (макс 15 слов). Без вступлений.\n\n' +
    'БЛОК 1: ВОЗМОЖНЫЕ ПРИЧИНЫ ПРОБЛЕМ\n' +
    '1. ...\n2. ...\n3. ...\n\n' +
    'БЛОК 2: РЕКОМЕНДАЦИИ\n' +
    '1. ...\n2. ...\n3. ...\n\n' +
    'БЛОК 3: УПРАВЛЕНЧЕСКИЕ ВЫВОДЫ\n' +
    '1. ...\n2. ...\n3. ...';
}

// ═══════════════════════════════════════════════════════════════
// ЗАПРОС К GROQ API (бесплатно, без карты)
// Ключ получить на: console.groq.com → API Keys → Create API Key
// ═══════════════════════════════════════════════════════════════
function callGemini_(prompt) {
  var apiKey = PropertiesService.getScriptProperties().getProperty('GROQ_API_KEY');
  if (!apiKey) return null;

  try {
    var resp = UrlFetchApp.fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'post',
      muteHttpExceptions: true,
      headers: {
        'Content-Type':  'application/json',
        'Authorization': 'Bearer ' + apiKey,
      },
      payload: JSON.stringify({
        model:      'llama-3.3-70b-versatile',
        max_tokens: 800,
        messages:   [{ role: 'user', content: prompt }],
      }),
    });

    var code = resp.getResponseCode();
    if (code !== 200) {
      Logger.log('Groq API error ' + code + ': ' + resp.getContentText());
      return null;
    }

    var result = JSON.parse(resp.getContentText());
    return result.choices[0].message.content;
  } catch (e) {
    Logger.log('Groq call error: ' + e.message);
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════
// ЗАПИСЬ РЕЗУЛЬТАТОВ В ЯЧЕЙКИ ДАШБОРДА
// ═══════════════════════════════════════════════════════════════
function writeAiResults_(sh, text) {
  // Парсим 3 блока
  var blocks = parseBlocks_(text);

  var causeRows  = [R.C1, R.C2, R.C3];
  var recRows    = [R.R1, R.R2, R.R3];
  var mgmtRows   = [R.M1, R.M2, R.M3];

  function writeBlock(rows, items) {
    for (var i = 0; i < rows.length; i++) {
      var text = items[i] ? items[i] : '—';
      sh.getRange(rows[i], 1).setValue(text);
    }
  }

  writeBlock(causeRows, blocks.causes);
  writeBlock(recRows,   blocks.recs);
  writeBlock(mgmtRows,  blocks.mgmt);
}

function parseBlocks_(text) {
  function extractItems(blockText) {
    var lines = blockText.split('\n').map(function(l) { return l.trim(); });
    var items = [];
    for (var i = 0; i < lines.length; i++) {
      var l = lines[i];
      // Строки начинающиеся с 1., 2., 3. или •
      var m = l.match(/^[1-3\•\-\*][\.\)]\s*(.+)/) || l.match(/^[•\-\*]\s*(.+)/);
      if (m) items.push(m[1]);
      else if (l.length > 5 && !/^(БЛОК|BLOCK|ВОЗМОЖНЫЕ|РЕКОМЕНДАЦИИ|УПРАВЛЕНЧЕСКИЕ)/i.test(l)) {
        items.push(l);
      }
      if (items.length >= 3) break;
    }
    return items;
  }

  // Разбиваем по маркерам БЛОК
  var b1 = '', b2 = '', b3 = '';
  var parts = text.split(/БЛОК\s*[123][\:\.]?/i);
  if (parts.length >= 4) {
    b1 = parts[1]; b2 = parts[2]; b3 = parts[3];
  } else {
    // Запасной вариант: делим на трети
    var third = Math.floor(text.length / 3);
    b1 = text.slice(0, third);
    b2 = text.slice(third, 2 * third);
    b3 = text.slice(2 * third);
  }

  return {
    causes: extractItems(b1),
    recs:   extractItems(b2),
    mgmt:   extractItems(b3),
  };
}

// ═══════════════════════════════════════════════════════════════
// ВСПОМОГАТЕЛЬНАЯ — ПОИСК ЛИСТА
// ═══════════════════════════════════════════════════════════════
function getDashSheet_(ss) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === DASH_GID) return sheets[i];
  }
  return ss.getSheetByName(DASH_NAME);
}
