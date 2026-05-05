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
 *   — записывает в нужный столбец листа «Монблан» (96 строк)
 *
 * Для ручного запуска за конкретный период:
 *   fillMonblanWeek('2025-01-06', '2025-01-12')
 */

// ═══════════════════════════════════════════════════════════════
// КОНСТАНТЫ IIKO
// ═══════════════════════════════════════════════════════════════
// Ключевые слова для категоризации Кухня/Бар (поле DishCategory).
// Также применяются к DishName для позиций без категории.
var IIKO_KITCHEN_KEYWORDS = ['кухн', 'kitchen', 'еда', 'food', 'блюд', 'горяч', 'десерт', 'завтрак', 'шеф',
                             'комплекс', 'суп', 'блин', 'наполеон', 'пицц', 'бургер', 'салат',
                             'стейк', 'шашлык', 'омлет', 'каша', 'чизкейк', 'торт', 'мороженое'];
var IIKO_BAR_KEYWORDS     = ['бар', 'bar', 'напитк', 'drink', 'beverage', 'алкогол', 'настойк', 'пиво', 'глинтвейн', 'вино'];

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
  var initResp = null;
  for (var a = 0; a < 3; a++) {
    if (a > 0) { Logger.log('olap/init retry ' + (a + 1) + ', пауза 15 сек'); Utilities.sleep(15000); }
    try {
      initResp = UrlFetchApp.fetch(cfg.WEB_URL + '/api/olap/init', {
        method: 'POST', headers: headers, payload: initBody, muteHttpExceptions: true,
      });
      if (initResp.getResponseCode() === 200) break;
      Logger.log('olap/init HTTP ' + initResp.getResponseCode());
    } catch(e) { Logger.log('olap/init exception: ' + e.message); initResp = null; }
  }
  if (!initResp || initResp.getResponseCode() !== 200) {
    Logger.log('olap/init: не удалось после 3 попыток');
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
    try {
      var statusResp = UrlFetchApp.fetch(cfg.WEB_URL + '/api/olap/fetch-status/' + reqId, {
        method: 'GET', headers: headers, muteHttpExceptions: true,
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
    } catch(e) { Logger.log('olap/fetch-status exception: ' + e.message); }
  }
  if (status !== 'SUCCESS' && status !== 'READY') {
    Logger.log('OLAP timeout. groupFields=' + JSON.stringify(groupFields));
    return null;
  }

  // 3. Получаем данные (с retry при Bandwidth quota exceeded)
  var fetchResp = null;
  for (var b = 0; b < 3; b++) {
    if (b > 0) { Logger.log('olap/fetch/DATA retry ' + (b + 1) + ', пауза 30 сек'); Utilities.sleep(30000); }
    try {
      fetchResp = UrlFetchApp.fetch(cfg.WEB_URL + '/api/olap/fetch/' + reqId + '/DATA', {
        method: 'POST', headers: headers,
        payload: JSON.stringify({rowOffset: 0, rowCount: 10000}),
        muteHttpExceptions: true,
      });
      if (fetchResp.getResponseCode() === 200) break;
      Logger.log('olap/fetch HTTP ' + fetchResp.getResponseCode());
    } catch(e) { Logger.log('olap/fetch/DATA exception: ' + e.message); fetchResp = null; }
  }
  if (!fetchResp || fetchResp.getResponseCode() !== 200) {
    Logger.log('olap/fetch/DATA: не удалось после 3 попыток, groupFields=' + JSON.stringify(groupFields));
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
  // Группируем по DishCategory + DishName, чтобы позиции с пустой категорией
  // определялись по названию блюда, а не уходили все в Бар
  Utilities.sleep(15000);
  var catRows = olapQuery_(token, 'SALES', ['DishCategory', 'DishName'],
    ['DishDiscountSumInt'], baseFilters);

  if (catRows) {
    for (var i = 0; i < catRows.length; i++) {
      var cat  = (catRows[i]['DishCategory'] || '').toLowerCase().trim();
      var name = (catRows[i]['DishName']     || '').toLowerCase().trim();
      var rev  = catRows[i]['DishDiscountSumInt'] || 0;
      if (containsKeyword_(cat, IIKO_KITCHEN_KEYWORDS)) {
        data.kitchenRevenue += rev;
      } else if (!cat) {
        // Пустая категория: определяем по названию блюда
        if (containsKeyword_(name, IIKO_KITCHEN_KEYWORDS)) {
          data.kitchenRevenue += rev;
        } else {
          data.barRevenue += rev;
        }
      } else {
        // Известная барная категория или нераспознанное → Бар
        data.barRevenue += rev;
      }
    }
  }

  // ── Запрос 3: выручка/гости/чеки по часу закрытия ───────────
  Utilities.sleep(15000);
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

  // ── Запрос 4: выручка и чеки по кол-ву гостей в чеке ────────
  Utilities.sleep(15000);
  var guestGroupRows = olapQuery_(token, 'SALES', ['GuestNum'],
    ['DishDiscountSumInt', 'UniqOrderId.OrdersCount'], baseFilters);

  if (guestGroupRows) {
    for (var i = 0; i < guestGroupRows.length; i++) {
      var gn  = parseInt(guestGroupRows[i]['GuestNum']) || 0;
      var rev = guestGroupRows[i]['DishDiscountSumInt'] || 0;
      var chk = guestGroupRows[i]['UniqOrderId.OrdersCount'] || 0;
      if (gn === 1) {
        data.revenue1Guest  += rev;
        data.checks1Guest   += chk;
      } else if (gn === 2) {
        data.revenue2Guests += rev;
        data.checks2Guests  += chk;
      } else if (gn >= 3) {
        data.revenue3PlusGuests += rev;
        data.checks3PlusGuests  += chk;
      }
    }
  }

  // ── Запрос 5: градация чеков по сумме (на заказ) ─────────────
  // OrderNum — рабочее поле (подтверждено diagnoseOrderFields: 233 строки = число чеков)
  Utilities.sleep(60000);
  var orderRows = olapQuery_(token, 'SALES', ['OrderNum'],
    ['DishDiscountSumInt'], baseFilters);

  Logger.log('Запрос 5 (OrderNum): ' + (orderRows === null ? 'null (ошибка OLAP)' : orderRows.length + ' строк'));
  if (orderRows && orderRows.length > 0) {
    for (var i = 0; i < orderRows.length; i++) {
      var amt = orderRows[i]['DishDiscountSumInt'] || 0;
      if      (amt <= 500)  data.revenue0to500     += amt;
      else if (amt <= 1000) data.revenue500to1000  += amt;
      else if (amt <= 1500) data.revenue1to1500    += amt;
      else if (amt <= 3000) data.revenue1500to3000 += amt;
      else if (amt <= 5000) data.revenue3000to5000 += amt;
      else                  data.revenue5000plus   += amt;
    }
  } else {
    Logger.log('⚠️ Градация чеков не заполнена. Запустите loadGradationOnly_() отдельно через 5 мин.');
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
// Запускать повторно при ошибке "Bandwidth quota exceeded":
// подождать 5–10 минут и запустить снова.
// ═══════════════════════════════════════════════════════════════

// Нед. 16 / 2026: 13–19 апреля (восстановить после ошибки авторизации)
function loadWeek16_2026() {
  fillMonblanWeek('2026-04-13', '2026-04-19');
}

// Нед. 17 / 2026: 20–26 апреля
function loadWeek17_2026() {
  fillMonblanWeek('2026-04-20', '2026-04-26');
}

// ═══════════════════════════════════════════════════════════════
// ДИАГНОСТИКА: найти рабочее поле для группировки по заказу
// Запустить один раз — смотреть Журнал выполнения.
// Выведет: какие поля дают ненулевые строки → то поле и использовать.
// ═══════════════════════════════════════════════════════════════
function diagnoseOrderGroupField_() {
  var token = getIikoToken_();
  if (!token) { Logger.log('Auth failed'); return; }

  var filters = [makeDateFilter_('2026-04-20', '2026-04-26')].concat(makeNotDeletedFilters_());

  var candidates = [
    'UniqOrderId', 'OrderId', 'ExternalId',
    'FiscalNumber', 'FiscalChequeNumber', 'OrderNumber',
    'ChequeNumber', 'CheckId', 'OrderNum',
  ];

  for (var i = 0; i < candidates.length; i++) {
    Utilities.sleep(15000);
    var rows = olapQuery_(token, 'SALES', [candidates[i]], ['DishDiscountSumInt'], filters);
    var info = rows === null
      ? 'ОШИБКА OLAP (поле не поддерживается)'
      : rows.length + ' строк';
    Logger.log('Field [' + candidates[i] + ']: ' + info);
    if (rows && rows.length > 0) {
      Logger.log('  ✅ РАБОЧЕЕ ПОЛЕ! Первая строка: ' + JSON.stringify(rows[0]));
    }
  }
  Logger.log('Диагностика завершена. Скопируйте вывод выше разработчику.');
}

// ═══════════════════════════════════════════════════════════════
// ГРАДАЦИЯ ЧЕКОВ — загрузка в строки 75–85
// orderGroupField — имя поля из diagnoseOrderGroupField_, которое вернуло строки
// ═══════════════════════════════════════════════════════════════
function loadGradationOnly_(dateFrom, dateTo, orderGroupField) {
  orderGroupField = orderGroupField || 'OrderNum';

  var ss  = SpreadsheetApp.getActiveSpreadsheet();
  var sh  = getMonblanSheet_(ss);
  if (!sh) { Logger.log('Лист Монблан не найден'); return; }

  var weekDate = new Date(dateFrom + 'T12:00:00');
  var col      = findWeekColumn_(sh, getIsoYear_(weekDate), getIsoWeek_(weekDate));
  if (!col) { Logger.log('Столбец недели не найден: ' + dateFrom); return; }

  var token = getIikoToken_();
  if (!token) { Logger.log('Ошибка авторизации'); return; }

  var filters = [makeDateFilter_(dateFrom, dateTo)].concat(makeNotDeletedFilters_());
  var rows    = olapQuery_(token, 'SALES', [orderGroupField], ['DishDiscountSumInt'], filters);
  Logger.log('loadGradationOnly_ [' + orderGroupField + ']: ' +
             (rows === null ? 'null (ошибка OLAP)' : rows.length + ' строк'));

  if (!rows || rows.length === 0) {
    Logger.log('⚠️ Поле [' + orderGroupField + '] вернуло 0 строк. Запустите diagnoseOrderGroupField_().');
    return;
  }

  var b = {r0:0, r500:0, r1000:0, r1500:0, r3000:0, r5000:0};
  for (var i = 0; i < rows.length; i++) {
    var amt = rows[i]['DishDiscountSumInt'] || 0;
    if      (amt <= 500)  b.r0    += amt;
    else if (amt <= 1000) b.r500  += amt;
    else if (amt <= 1500) b.r1000 += amt;
    else if (amt <= 3000) b.r1500 += amt;
    else if (amt <= 5000) b.r3000 += amt;
    else                  b.r5000 += amt;
  }

  sh.getRange(75, col).setValue(b.r0);
  sh.getRange(77, col).setValue(b.r500);
  sh.getRange(79, col).setValue(b.r1000);
  sh.getRange(81, col).setValue(b.r1500);
  sh.getRange(83, col).setValue(b.r3000);
  sh.getRange(85, col).setValue(b.r5000);
  Logger.log('✅ Градация чеков записана в столбец ' + col);
}

// Ярлыки для ручного запуска
function loadGradationWeek16_2026() { loadGradationOnly_('2026-04-13', '2026-04-19'); }
function loadGradationWeek17_2026() { loadGradationOnly_('2026-04-20', '2026-04-26'); }

// Публичная обёртка — видна в списке функций Apps Script
function diagnoseOrderFields() { diagnoseOrderGroupField_(); }
