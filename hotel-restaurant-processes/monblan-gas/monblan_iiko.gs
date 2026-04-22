/**
 * МОНБЛАН — ЗАГРУЗКА ДАННЫХ ИЗ IIKO (iikoWeb OLAP)
 *
 * API:  https://kafe-monblan.iikoweb.ru
 * Auth: POST /api/auth/login {login, password} → JWT-токен
 * OLAP: POST /api/olap/init → GET /api/olap/fetch-status → POST /api/olap/fetch/DATA
 *
 * Основная функция: fillMonblanWeekFromIiko()
 *   — автоматически берёт прошедшую неделю (Пн–Вс)
 *   — запрашивает данные из iikoWeb OLAP
 *   — записывает в нужный столбец трекинг-листа
 *
 * Для ручного запуска за конкретный период:
 *   fillMonblanWeek('2025-01-06', '2025-01-12')
 */

// ═══════════════════════════════════════════════════════════════
// КОНСТАНТЫ IIKO
// ═══════════════════════════════════════════════════════════════
var IIKO_KITCHEN_KEYWORDS = ['кухн', 'kitchen', 'еда', 'food', 'блюд', 'горяч', 'десерт', 'завтрак', 'шеф'];
var IIKO_BAR_KEYWORDS     = ['бар', 'bar', 'напитк', 'drink', 'beverage', 'алкогол'];

// Кэш токена на время выполнения скрипта
var _iikoTokenCache_ = null;

// ═══════════════════════════════════════════════════════════════
// УСТАНОВКА ЕЖЕНЕДЕЛЬНОГО ТРИГГЕРА (запустить один раз вручную)
// Каждый понедельник в 9:00 автоматически загружает данные
// за прошедшую неделю (Пн–Вс) из iikoWeb.
// Часовой пояс триггера = часовой пояс проекта Apps Script.
// Убедитесь что в Настройках проекта стоит Asia/Yekaterinburg (UTC+5).
// ═══════════════════════════════════════════════════════════════
function installWeeklyTrigger() {
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === 'fillMonblanWeekFromIiko') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('fillMonblanWeekFromIiko')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.MONDAY)
    .atHour(9)
    .create();
  SpreadsheetApp.getUi().alert(
    '✅ Еженедельный триггер установлен!\n\n' +
    'Каждый понедельник в 9:00–10:00 данные за прошедшую\n' +
    'неделю (Пн–Вс) будут загружаться автоматически из iiko.\n\n' +
    'Часовой пояс: проверьте Настройки проекта → Asia/Yekaterinburg.'
  );
}

// ═══════════════════════════════════════════════════════════════
// ОСНОВНАЯ ТОЧКА ВХОДА (запускается триггером каждый понедельник)
// ═══════════════════════════════════════════════════════════════
function fillMonblanWeekFromIiko() {
  var today     = new Date();
  var dayOfWeek = today.getDay() || 7;
  var lastMon   = new Date(today.getTime() - (dayOfWeek - 1 + 7) * 86400000);
  var lastSun   = new Date(lastMon.getTime() + 6 * 86400000);

  var fmt = function(d) {
    return d.getFullYear() + '-' +
           ('0' + (d.getMonth() + 1)).slice(-2) + '-' +
           ('0' + d.getDate()).slice(-2);
  };

  fillMonblanWeek(fmt(lastMon), fmt(lastSun));
}

/**
 * Запрос данных iikoWeb за период dateFrom..dateTo и запись в таблицу.
 * @param {string} dateFrom  - 'YYYY-MM-DD' (понедельник)
 * @param {string} dateTo    - 'YYYY-MM-DD' (воскресенье)
 */
function fillMonblanWeek(dateFrom, dateTo) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = getMonblanSheet_(ss);
  if (!sh) {
    Logger.log('Лист Монблан не найден. Запустите сначала buildMonblanSheet().');
    return;
  }

  var weekDate = new Date(dateFrom + 'T12:00:00');
  var isoYear  = getIsoYear_(weekDate);
  var isoWeek  = getIsoWeek_(weekDate);
  var col      = findWeekColumn_(sh, isoYear, isoWeek);

  if (!col) {
    Logger.log('Не найден столбец для недели ' + isoYear + '/' + isoWeek);
    return;
  }

  Logger.log('Записываем данные в столбец ' + col + ' (неделя ' + isoWeek + ' ' + isoYear + ')');

  var token = getIikoToken_();
  if (!token) {
    markColumnError_(sh, col, '⚠️ Ошибка авторизации iikoWeb');
    return;
  }

  var data = fetchIikoWeekData_(token, dateFrom, dateTo);
  if (!data) {
    markColumnError_(sh, col, '⚠️ Нет данных — ошибка OLAP API');
    return;
  }

  writeWeekData_(sh, col, data);
  Logger.log('✅ Данные за неделю ' + dateFrom + ' — ' + dateTo + ' записаны.');
}

// ═══════════════════════════════════════════════════════════════
// АВТОРИЗАЦИЯ — iikoWeb
// ═══════════════════════════════════════════════════════════════
function getIikoToken_() {
  if (_iikoTokenCache_) return _iikoTokenCache_;

  var cfg = MB_CONFIG.IIKO;
  var url = cfg.WEB_URL + '/api/auth/login';
  var options = {
    method:             'POST',
    contentType:        'application/json',
    payload:            JSON.stringify({login: cfg.LOGIN, password: cfg.PASSWORD}),
    muteHttpExceptions: true,
  };

  for (var attempt = 0; attempt < 3; attempt++) {
    if (attempt > 0) {
      Logger.log('iikoWeb: пауза 60 сек перед попыткой ' + (attempt + 1));
      Utilities.sleep(60000);
    }
    try {
      var resp = UrlFetchApp.fetch(url, options);
      if (resp.getResponseCode() === 200) {
        var data = JSON.parse(resp.getContentText());
        if (!data.error && data.token) {
          _iikoTokenCache_ = data.token;
          Logger.log('iikoWeb: авторизован');
          return data.token;
        }
        Logger.log('iikoWeb login error: ' + JSON.stringify(data));
      } else {
        Logger.log('iikoWeb HTTP ' + resp.getResponseCode() + ': ' + resp.getContentText().slice(0, 200));
      }
    } catch(e) {
      Logger.log('Ошибка авторизации iikoWeb: ' + e.message);
    }
  }
  return null;
}

// ═══════════════════════════════════════════════════════════════
// OLAP-ЗАПРОС
//
// Возвращает массив строк rawData или null при ошибке.
// olapType: 'SALES'
// ═══════════════════════════════════════════════════════════════
function olapQuery_(token, olapType, groupFields, dataFields, filters) {
  var cfg     = MB_CONFIG.IIKO;
  var headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'};

  // 1. Инициируем запрос
  var initBody = JSON.stringify({
    storeIds:    [cfg.STORE_ID],
    olapType:    olapType,
    groupFields: groupFields,
    dataFields:  dataFields,
    filters:     filters,
  });
  var initResp = UrlFetchApp.fetch(cfg.WEB_URL + '/api/olap/init', {
    method:             'POST',
    headers:            headers,
    payload:            initBody,
    muteHttpExceptions: true,
  });
  if (initResp.getResponseCode() !== 200) {
    Logger.log('olap/init HTTP ' + initResp.getResponseCode());
    return null;
  }
  var initData = JSON.parse(initResp.getContentText());
  if (initData.error) {
    Logger.log('olap/init error: ' + initData.errorMessage);
    return null;
  }
  var reqId = initData.data;
  if (!reqId) {
    Logger.log('olap/init: нет requestId');
    return null;
  }

  // 2. Ждём SUCCESS
  var status = '';
  for (var i = 0; i < 20; i++) {
    Utilities.sleep(3000);
    var statusResp = UrlFetchApp.fetch(cfg.WEB_URL + '/api/olap/fetch-status/' + reqId, {
      method:             'GET',
      headers:            headers,
      muteHttpExceptions: true,
    });
    if (statusResp.getResponseCode() === 200) {
      var statusData = JSON.parse(statusResp.getContentText());
      status = statusData.data || '';
      Logger.log('OLAP [' + olapType + '] статус: ' + status + ' (попытка ' + (i + 1) + ')');
      if (status === 'SUCCESS' || status === 'READY') break;
      if (status === 'ERROR') {
        Logger.log('OLAP вернул ERROR. groupFields=' + JSON.stringify(groupFields));
        return null;
      }
    }
  }
  if (status !== 'SUCCESS' && status !== 'READY') {
    Logger.log('OLAP timeout. groupFields=' + JSON.stringify(groupFields));
    return null;
  }

  // 3. Получаем данные
  var fetchResp = UrlFetchApp.fetch(cfg.WEB_URL + '/api/olap/fetch/' + reqId + '/DATA', {
    method:             'POST',
    headers:            headers,
    payload:            JSON.stringify({rowOffset: 0, rowCount: 10000}),
    muteHttpExceptions: true,
  });
  if (fetchResp.getResponseCode() !== 200) {
    Logger.log('olap/fetch HTTP ' + fetchResp.getResponseCode());
    return null;
  }
  var fetchData = JSON.parse(fetchResp.getContentText());
  if (fetchData.error) {
    Logger.log('olap/fetch error: ' + fetchData.errorMessage);
    return null;
  }
  var rawData = (fetchData.result || {}).rawData || [];
  Logger.log('OLAP [' + olapType + '] получено строк: ' + rawData.length +
             ', groupFields=' + JSON.stringify(groupFields));
  return rawData;
}

// ═══════════════════════════════════════════════════════════════
// ФИЛЬТРЫ
// ═══════════════════════════════════════════════════════════════
function makeDateFilter_(dateFrom, dateTo) {
  return {
    field:         'OpenDate.Typed',
    filterType:    'date_range',
    dateFrom:      dateFrom,
    dateTo:        dateTo,
    valueMin:      null,
    valueMax:      null,
    valueList:     [],
    includeLeft:   true,
    includeRight:  true,
    inclusiveList: true,
  };
}

function makeNotDeletedFilters_() {
  return [
    {
      field:         'DeletedWithWriteoff',
      filterType:    'value_list',
      dateFrom:      null, dateTo: null,
      valueMin:      null, valueMax: null,
      valueList:     ['NOT_DELETED'],
      includeLeft:   true, includeRight: false, inclusiveList: true,
    },
    {
      field:         'OrderDeleted',
      filterType:    'value_list',
      dateFrom:      null, dateTo: null,
      valueMin:      null, valueMax: null,
      valueList:     ['NOT_DELETED'],
      includeLeft:   true, includeRight: false, inclusiveList: true,
    },
  ];
}

// ═══════════════════════════════════════════════════════════════
// СБОР ДАННЫХ ЗА НЕДЕЛЮ
// ═══════════════════════════════════════════════════════════════
function fetchIikoWeekData_(token, dateFrom, dateTo) {
  var baseFilters = [makeDateFilter_(dateFrom, dateTo)].concat(makeNotDeletedFilters_());

  var data = {
    totalRevenue:    0, kitchenRevenue:  0, barRevenue:      0,
    morningRevenue:  0, dayRevenue:      0, eveningRevenue:  0,
    monRevenue:      0, tueRevenue:      0, wedRevenue:      0,
    thuRevenue:      0, friRevenue:      0, satRevenue:      0, sunRevenue: 0,
    totalGuests:     0, morningGuests:   0, dayGuests:       0, eveningGuests:  0,
    totalChecks:     0, morningChecks:   0, dayChecks:       0, eveningChecks:  0,
    totalDishes:     0,
    // Ниже — недоступно через OLAP для роли buh, оставляем 0
    revenue1Guest:      0, revenue2Guests:     0, revenue3PlusGuests: 0,
    checks1Guest:       0, checks2Guests:      0, checks3PlusGuests:  0,
    revenue0to500:      0, revenue500to1000:   0, revenue1to1500:     0,
    revenue1500to3000:  0, revenue3000to5000:  0, revenue5000plus:    0,
    breakfastsGuests:   0, eventsCount:        0, eventsRevenue:      0, eventsGuests: 0,
  };

  // ── Запрос 1: сводка по датам (итого + по дням недели) ──────
  var summaryRows = olapQuery_(token, 'SALES', ['OpenDate.Typed'],
    ['DishDiscountSumInt', 'UniqOrderId.OrdersCount', 'GuestNum', 'DishAmountInt'],
    baseFilters);

  if (summaryRows) {
    var dayRevMap = {};
    for (var i = 0; i < summaryRows.length; i++) {
      var row   = summaryRows[i];
      var rev    = row['DishDiscountSumInt'] || 0;
      var checks = row['UniqOrderId.OrdersCount'] || 0;
      var guests = row['GuestNum'] || 0;
      var dishes = row['DishAmountInt'] || 0;
      var ds     = row['OpenDate.Typed'] || '';

      data.totalRevenue += rev;
      data.totalChecks  += checks;
      data.totalGuests  += guests;
      data.totalDishes  += dishes;
      if (ds) dayRevMap[ds] = rev;
    }

    // Раскладываем по дням недели: dateFrom — понедельник
    var DAY_KEYS  = ['monRevenue','tueRevenue','wedRevenue','thuRevenue',
                     'friRevenue','satRevenue','sunRevenue'];
    var monParts  = dateFrom.split('-');
    var monDate   = new Date(
      parseInt(monParts[0]), parseInt(monParts[1]) - 1, parseInt(monParts[2]), 12, 0, 0
    );
    for (var d = 0; d < 7; d++) {
      var dt = new Date(monDate.getTime() + d * 86400000);
      var ds = dt.getFullYear() + '-' +
               ('0' + (dt.getMonth() + 1)).slice(-2) + '-' +
               ('0' + dt.getDate()).slice(-2);
      data[DAY_KEYS[d]] = dayRevMap[ds] || 0;
    }
  }

  // ── Запрос 2: выручка по категориям (кухня / бар) ───────────
  var catRows = olapQuery_(token, 'SALES', ['DishCategory.Accounting'],
    ['DishDiscountSumInt'], baseFilters);

  if (catRows) {
    for (var i = 0; i < catRows.length; i++) {
      var cat = (catRows[i]['DishCategory.Accounting'] || '').toLowerCase();
      var rev = catRows[i]['DishDiscountSumInt'] || 0;
      if (containsKeyword_(cat, IIKO_KITCHEN_KEYWORDS)) {
        data.kitchenRevenue += rev;
      } else if (containsKeyword_(cat, IIKO_BAR_KEYWORDS)) {
        data.barRevenue += rev;
      }
    }
  }

  // ── Запрос 3: выручка/гости/чеки по часу закрытия ───────────
  var hourRows = olapQuery_(token, 'SALES', ['HourClose'],
    ['DishDiscountSumInt', 'GuestNum', 'UniqOrderId.OrdersCount'], baseFilters);

  if (hourRows) {
    for (var i = 0; i < hourRows.length; i++) {
      var hour   = parseInt(hourRows[i]['HourClose']) || 0;
      var rev    = hourRows[i]['DishDiscountSumInt'] || 0;
      var guests = hourRows[i]['GuestNum'] || 0;
      var checks = hourRows[i]['UniqOrderId.OrdersCount'] || 0;
      if (hour >= 9 && hour < 11) {
        data.morningRevenue += rev;
        data.morningGuests  += guests;
        data.morningChecks  += checks;
      } else if (hour >= 11 && hour < 17) {
        data.dayRevenue += rev;
        data.dayGuests  += guests;
        data.dayChecks  += checks;
      } else if (hour >= 17 && hour < 23) {
        data.eveningRevenue += rev;
        data.eveningGuests  += guests;
        data.eveningChecks  += checks;
      }
    }
  }

  return data;
}

// ═══════════════════════════════════════════════════════════════
// ЗАПИСЬ ДАННЫХ В СТОЛБЕЦ ТРЕКИНГ-ЛИСТА
// ═══════════════════════════════════════════════════════════════
function writeWeekData_(sh, col, data) {
  var rowToField = {
    4:  'totalRevenue',
    5:  'kitchenRevenue',
    7:  'barRevenue',
    10: 'morningRevenue',
    12: 'dayRevenue',
    14: 'eveningRevenue',
    17: 'monRevenue',
    19: 'tueRevenue',
    21: 'wedRevenue',
    23: 'thuRevenue',
    25: 'friRevenue',
    27: 'satRevenue',
    29: 'sunRevenue',
    31: 'totalGuests',
    32: 'morningGuests',
    34: 'dayGuests',
    36: 'eveningGuests',
    42: 'totalChecks',
    43: 'morningChecks',
    44: 'dayChecks',
    45: 'eveningChecks',
    46: 'totalDishes',
    61: 'revenue1Guest',
    63: 'revenue2Guests',
    65: 'revenue3PlusGuests',
    68: 'checks1Guest',
    70: 'checks2Guests',
    72: 'checks3PlusGuests',
    75: 'revenue0to500',
    77: 'revenue500to1000',
    79: 'revenue1to1500',
    81: 'revenue1500to3000',
    83: 'revenue3000to5000',
    85: 'revenue5000plus',
    91: 'breakfastsGuests',
    92: 'eventsCount',
    93: 'eventsRevenue',
    94: 'eventsGuests',
  };

  for (var row in rowToField) {
    var field = rowToField[row];
    var value = data[field];
    sh.getRange(parseInt(row), col).setValue(value !== undefined ? value : 0);
  }
}

// ═══════════════════════════════════════════════════════════════
// ПОИСК СТОЛБЦА ДЛЯ КОНКРЕТНОЙ НЕДЕЛИ
// ═══════════════════════════════════════════════════════════════
function findWeekColumn_(sh, year, week) {
  var firstDataCol = 2;
  var weeksCount   = MB_CONFIG.WEEKS_TO_INIT;

  var yearRow = sh.getRange(1, firstDataCol, 1, weeksCount).getValues()[0];
  var weekRow = sh.getRange(2, firstDataCol, 1, weeksCount).getValues()[0];

  for (var i = 0; i < weeksCount; i++) {
    if (yearRow[i] === year && weekRow[i] === week) {
      return firstDataCol + i;
    }
  }
  return null;
}

// ═══════════════════════════════════════════════════════════════
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ═══════════════════════════════════════════════════════════════

function markColumnError_(sh, col, message) {
  sh.getRange(4, col).setValue(message);
  Logger.log(message + ' (столбец ' + col + ')');
}

function containsKeyword_(str, keywords) {
  for (var i = 0; i < keywords.length; i++) {
    if (str.indexOf(keywords[i]) >= 0) return true;
  }
  return false;
}

function fetchWithRetry_(url, options, retries) {
  retries = retries || 3;
  for (var i = 0; i < retries; i++) {
    try {
      var resp = UrlFetchApp.fetch(url, options);
      if (resp.getResponseCode() === 200) return resp;
    } catch(e) {
      Logger.log('Попытка ' + (i + 1) + '/' + retries + ' не удалась: ' + e.message);
      if (i < retries - 1) Utilities.sleep(10 * 60 * 1000);
    }
  }
  return null;
}

function getIsoWeek_(date) {
  var d = new Date(date.getTime());
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + 3 - ((d.getDay() + 6) % 7));
  var week1 = new Date(d.getFullYear(), 0, 4);
  return 1 + Math.round(
    ((d.getTime() - week1.getTime()) / 86400000 - 3 + ((week1.getDay() + 6) % 7)) / 7
  );
}

function getIsoYear_(date) {
  var d = new Date(date.getTime());
  d.setDate(d.getDate() + 3 - ((d.getDay() + 6) % 7));
  return d.getFullYear();
}

// ═══════════════════════════════════════════════════════════════
// РАЗОВАЯ ЗАГРУЗКА КОНКРЕТНЫХ НЕДЕЛЬ (запустить вручную)
// ═══════════════════════════════════════════════════════════════
function loadWeek16_2026() {
  fillMonblanWeek('2026-04-13', '2026-04-19');
}
