/**
 * MAIN.GS — Еженедельный сбор данных для отчёта Губаха
 *
 * Устанавливается в GAS-проект таблицы:
 *   https://docs.google.com/spreadsheets/d/1Ohm7tst750zDzSeIewJFj_cPC6vl0-5J0UiuNfZvY_k
 *
 * Что делает:
 *   1. Забирает данные из TravelLine API за прошедшую неделю
 *   2. Читает выручку Монблан из отдельной таблицы
 *   3. Записывает данные в новый столбец (одна колонка = одна неделя)
 *   4. Устанавливает формулы для расчётных строк (RevPAR, RevPAC, F&B % и др.)
 *
 * Перед первым запуском — установить Script Properties:
 *   TL_CLIENT_ID     → client id TravelLine
 *   TL_CLIENT_SECRET → client secret TravelLine
 *   TL_PROPERTY_ID   → 11931
 *
 * Запуск: функция collectWeeklyHotelReport() — вручную или по триггеру.
 * Триггер: installWeeklyTrigger() — один раз, создаёт пн 05:00 UTC.
 */

// ═══════════════════════════════════════════════════════════════
// КОНСТАНТЫ
// ═══════════════════════════════════════════════════════════════

var MONBLAN_SHEET_ID = '1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI';
var MONBLAN_GID      = 2051236241;
var HOTEL_SHEET_GID  = 2018226789;

var TL_AUTH_URL = 'https://partner.tlintegration.com/auth/token';
var TL_API_BASE = 'https://partner.tlintegration.com/api/read-reservation/v1';

// Классификация номеров по типам (из travelline_collector.py — проверено на реальных данных)
var COTTAGE_TYPES = {152774:1,183368:1,198656:1,152776:1,183367:1,213511:1,
                     296293:1,123405:1,183411:1,183414:1,183438:1,208986:1,208987:1};
var DANIEL_TYPES  = {84929:1,84928:1,84934:1,84939:1};
var ALEN_TYPES    = {82359:1,82361:1,82364:1,82365:1,82367:1,220392:1,220405:1};

// Ёмкость (единиц) — из rooms endpoint TravelLine
var UNITS_COTTAGE = 21;
var UNITS_DANIEL  = 15;
var UNITS_ALEN    = 58;

// Строки листа, которые заполняем автоматически
var ROWS = {
  TOTAL_REVENUE:  5,   // Доход общий НФ+Кафе
  WEEK_NUM:       1,   // Номера недель (строка 1)
  DATES:          2,   // Диапазоны дат (строка 2)
  PREV_YEAR_REV:  7,   // Выручка прошлого года за ту же неделю (из листа 2025)
  MB_REVENUE:     11,  // Выручка Монблан
  MB_CHECKS:      12,  // Чеков Монблан
  FB_PCT:         13,  // F&B % от оборота (формула)
  BREAKFASTS:     14,  // Кол-во завтраков
  PCT_PLAN_MO:    9,   // % к факту прошлого года (формула)
  FURAKO:         17,  // Фурако/бани
  BESEDKA:        18,  // Беседки/мангалы
  OTHER_SVC:      19,  // Прочие услуги
  GUESTS:         21,  // Гостей всего
  RETURNING_PCT:  22,  // % повторных гостей
  ADR:            23,  // ADR коттеджей
  REVPAR:         24,  // RevPAR (формула)
  REVPAC:         25,  // RevPAC (формула)
  AVG_LOS:        27,  // Ср. пребывание
  OCC_COTTAGE:    28,  // Загрузка коттеджей
  OCC_DANIEL:     29,  // Загрузка Даниэль
  OCC_ALEN:       30,  // Загрузка Ален
  CANCEL_PCT:     32,  // Доля отмен
  // Строка 33 (Доля прямых продаж) — не заполняем, ручной ввод
  PLAN_NEXT_MO:   35,  // План выручки след. мес. (ручной)
  BOOKED_NEXT_MO: 36,  // Забронировано след. мес. (из TravelLine)
  // Строка 37 (Динамика) — не заполняем, ручной ввод
  PCT_PLAN_NEXT:  38,  // % выполн. плана след. мес. (формула)
};


// ═══════════════════════════════════════════════════════════════
// ТОЧКА ВХОДА
// ═══════════════════════════════════════════════════════════════

function collectWeeklyHotelReport() {
  var props = PropertiesService.getScriptProperties();
  if (!props.getProperty('TL_CLIENT_ID')) {
    SpreadsheetApp.getUi().alert(
      '⚠️ Не заданы Script Properties!\n\n' +
      'Установите: TL_CLIENT_ID, TL_CLIENT_SECRET, TL_PROPERTY_ID\n' +
      'Меню: Проект → Script Properties'
    );
    return;
  }

  var week = getPrevWeek_();
  Logger.log('▶ Старт: неделя ' + week.num + ' ' + week.year +
             ' (' + week.dateLabel + ')');

  // Находим лист отчёта по GID
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = getSheetByGid_(ss, HOTEL_SHEET_GID);
  if (!sh) {
    Logger.log('❌ Лист с GID=' + HOTEL_SHEET_GID + ' не найден');
    return;
  }

  // Находим или создаём столбец для этой недели
  var col = findOrCreateWeekCol_(sh, week);
  Logger.log('  Столбец: ' + columnToLetter_(col) + ' (col ' + col + ')');

  // TravelLine: авторизация и сбор броней
  Logger.log('  TravelLine: получаем токен...');
  var token = getTLToken_();
  Logger.log('  TravelLine: сбор броней...');
  var collected = collectBookings_(token, week.start, week.end);
  Logger.log('  TravelLine: активных=' + collected.active.length +
             ', отменённых=' + collected.cancelled.length);

  Logger.log('  TravelLine: загружаем детали ' + collected.active.length + ' броней...');
  var bookings = fetchBookingDetails_(token, collected.active);
  Logger.log('  TravelLine: загружено ' + bookings.length + ' деталей');

  var tl = calcMetrics_(bookings, collected.cancelled.length, week.start, week.end);
  Logger.log('  Метрики: выручка НФ=' + tl.rev_nf + ', гостей=' + tl.guests +
             ', загрузка котт=' + Math.round(tl.occ_cottage * 100) + '%');

  // Монблан: читаем данные за ту же неделю
  Logger.log('  Монблан: читаем неделю ' + week.num + '/' + week.year + '...');
  var mb = readMonblan_(week.num, week.year);
  Logger.log('  Монблан: выручка=' + mb.revenue + ', чеков=' + mb.checks);

  // Находим название листа "2025" для формулы строки 7
  var prevSheetName = findPrevYearSheetName_(ss);
  Logger.log('  Лист ПГ: ' + (prevSheetName || 'не найден'));

  // Забронировано на следующий календарный месяц (из TravelLine)
  Logger.log('  Броней на следующий месяц...');
  var nextMonthRev = collectNextMonthBookings_(token);
  Logger.log('  Забронировано след. месяц: ' + nextMonthRev);

  // Записываем данные
  writeData_(sh, col, tl, mb, nextMonthRev);
  Logger.log('  Данные записаны');

  // Устанавливаем формулы (включая строки 6 и 7)
  setFormulas_(sh, col, prevSheetName);
  Logger.log('  Формулы установлены');

  SpreadsheetApp.flush();
  Logger.log('✅ Готово: неделя ' + week.num + ' (' + week.dateLabel +
             ') → столбец ' + columnToLetter_(col));
}


// ═══════════════════════════════════════════════════════════════
// ТРИГГЕР
// ═══════════════════════════════════════════════════════════════

/**
 * Создаёт еженедельный триггер: каждый понедельник в 05:00 UTC (10:00 UTC+5).
 * Запускать один раз вручную.
 */
function installWeeklyTrigger() {
  // Удаляем существующие триггеры для этой функции
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === 'collectWeeklyHotelReport') {
      ScriptApp.deleteTrigger(t);
    }
  });

  ScriptApp.newTrigger('collectWeeklyHotelReport')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.MONDAY)
    .atHour(5)   // 05:00 UTC = 10:00 UTC+5
    .create();

  Logger.log('✅ Триггер установлен: понедельник 05:00 UTC');
}


// ═══════════════════════════════════════════════════════════════
// TRAVELLINE: АВТОРИЗАЦИЯ
// ═══════════════════════════════════════════════════════════════

function getTLToken_() {
  var props = PropertiesService.getScriptProperties();
  var resp = UrlFetchApp.fetch(TL_AUTH_URL, {
    method: 'post',
    payload: {
      grant_type:    'client_credentials',
      client_id:     props.getProperty('TL_CLIENT_ID'),
      client_secret: props.getProperty('TL_CLIENT_SECRET'),
    },
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    muteHttpExceptions: true,
  });

  if (resp.getResponseCode() !== 200) {
    throw new Error('TravelLine auth failed: ' + resp.getResponseCode() +
                    ' ' + resp.getContentText().substring(0, 200));
  }

  return JSON.parse(resp.getContentText()).access_token;
}


// ═══════════════════════════════════════════════════════════════
// TRAVELLINE: СБОР НОМЕРОВ БРОНЕЙ
// ═══════════════════════════════════════════════════════════════

/**
 * Собирает номера активных и отменённых броней с заездом в целевую неделю.
 * Алгоритм: forged continueToken + постраничный обход.
 */
function collectBookings_(token, weekStart, weekEnd) {
  var PROPERTY_ID = PropertiesService.getScriptProperties().getProperty('TL_PROPERTY_ID');
  var hdrs = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json'};

  // Префиксы дат для фильтрации: week_start-3 … week_end (stay-over гости)
  var prefixes = {};
  var d = new Date(weekStart.getTime());
  d.setDate(d.getDate() - 3);
  while (d <= weekEnd) {
    prefixes[formatDate_(d)] = true;
    d.setDate(d.getDate() + 1);
  }

  // Начало сканирования: неделя - 90 дней
  var scanFrom = new Date(weekStart.getTime());
  scanFrom.setDate(scanFrom.getDate() - 90);
  var scanEndStr = formatDate_(new Date(weekEnd.getTime() + 14 * 24 * 3600 * 1000));

  var ct = forgeToken_(scanFrom);
  var active = [], cancelled = [];
  var page = 0;

  while (page < 80) {
    var url = TL_API_BASE + '/properties/' + PROPERTY_ID +
              '/bookings?pageSize=100&continueToken=' + encodeURIComponent(ct);
    var resp = UrlFetchApp.fetch(url, {method: 'get', headers: hdrs, muteHttpExceptions: true});

    if (resp.getResponseCode() !== 200) {
      Logger.log('  ⚠️ Ошибка ' + resp.getResponseCode() + ': ' +
                 resp.getContentText().substring(0, 200));
      break;
    }

    var data = JSON.parse(resp.getContentText());
    var summaries = data.bookingSummaries || [];
    page++;

    summaries.forEach(function(s) {
      var num = s.number || '';
      if (prefixes[num.substring(0, 8)]) {
        if (s.status === 'Active') {
          active.push(num);
        } else {
          cancelled.push(num);
        }
      }
    });

    // Проверяем дату последней записи — если прошли нужный период, стоп
    if (summaries.length > 0) {
      var lastMod = (summaries[summaries.length - 1].modifiedDateTime || '').substring(0, 10);
      if (lastMod > scanEndStr) {
        Logger.log('  Страница ' + page + ': прошли ' + scanEndStr + ', стоп');
        break;
      }
    }

    ct = data.continueToken || '';
    if (!ct || !data.hasMoreData) break;

    Utilities.sleep(400);
  }

  return {active: active, cancelled: cancelled};
}


// ═══════════════════════════════════════════════════════════════
// TRAVELLINE: ЗАГРУЗКА ДЕТАЛЕЙ БРОНЕЙ
// ═══════════════════════════════════════════════════════════════

function fetchBookingDetails_(token, numbers) {
  var PROPERTY_ID = PropertiesService.getScriptProperties().getProperty('TL_PROPERTY_ID');
  var hdrs = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json'};
  var bookings = [];

  for (var i = 0; i < numbers.length; i++) {
    var url = TL_API_BASE + '/properties/' + PROPERTY_ID + '/bookings/' + numbers[i];
    var resp = UrlFetchApp.fetch(url, {method: 'get', headers: hdrs, muteHttpExceptions: true});

    if (resp.getResponseCode() === 200) {
      var bk = JSON.parse(resp.getContentText()).booking;
      if (bk) bookings.push(bk);
    }

    if ((i + 1) % 10 === 0) {
      Logger.log('  ' + (i + 1) + '/' + numbers.length + ' загружено');
    }
    Utilities.sleep(400);
  }

  return bookings;
}


// ═══════════════════════════════════════════════════════════════
// РАСЧЁТ МЕТРИК
// ═══════════════════════════════════════════════════════════════

/**
 * Вычисляет метрики из списка активных броней.
 * Логика полностью аналогична aihotel/travelline_collector.py :: calculate()
 */
function calcMetrics_(bookings, cancelledCount, weekStart, weekEnd) {
  var revRooms = 0, revFurako = 0, revBesedka = 0, revOther = 0;
  var guests = 0, returningCount = 0, directCount = 0;
  var cottageNights = 0, danielNights = 0, alenNights = 0;
  var cottageRevenue = 0;
  var cottageLosList = [];
  var breakfastCount = 0;
  var total = bookings.length;

  bookings.forEach(function(bk) {
    // Повторный гость (есть карта лояльности)
    var loyalty = ((bk.guaranteeInfo || {}).loyalty) || {};
    if (loyalty.cards && loyalty.cards.length > 0) returningCount++;

    // Канал продаж: BookingEngine + PMS = прямые продажи
    var srcType = ((bk.source || {}).type) || '';
    if (srcType === 'BookingEngine' || srcType === 'PMS') directCount++;

    var bkFurako = 0, bkBesedka = 0, bkOther = 0, bkBreakfast = 0;

    (bk.roomStays || []).forEach(function(rs) {
      var arr = rs.stayDates.arrivalDateTime;
      var dep = rs.stayDates.departureDateTime;
      var ov  = overlapNights_(arr, dep, weekStart, weekEnd);
      if (ov === 0) return;

      var arrDate = new Date(arr.substring(0, 10) + 'T00:00:00Z');
      var depDate = new Date(dep.substring(0, 10) + 'T00:00:00Z');
      var totalNights = Math.max(1, (depDate - arrDate) / 86400000);
      var ratio = ov / totalNights;

      var rtId = parseInt(rs.roomType.id) || rs.roomType.id;

      // Классифицируем сервисы
      var svcToExtract = 0;
      (rs.services || []).forEach(function(svc) {
        var svcPrice = ((svc.total || {}).priceAfterTax) || 0;
        var cat = svcCategory_(svc.name || '', svc.mealPlanCode || '');
        if (cat === 'breakfast') {
          bkBreakfast++;
          // Завтрак остаётся в цене номера (не вычитаем)
        } else if (cat === 'furako') {
          svcToExtract += svcPrice;
          bkFurako += svcPrice * ratio;
        } else if (cat === 'besedka') {
          svcToExtract += svcPrice;
          bkBesedka += svcPrice * ratio;
        } else {
          svcToExtract += svcPrice;
          bkOther += svcPrice * ratio;
        }
      });

      // Выручка за размещение = цена roomStay минус извлечённые сервисы, пропорционально
      var rsPrice   = (rs.total.priceAfterTax || 0) - svcToExtract;
      var rsWeekRev = rsPrice * ratio;

      revRooms += rsWeekRev;
      guests   += (rs.guestCount.adultCount || 0) +
                  ((rs.guestCount.childAges || []).length);

      // Сегментация ночей и выручки
      if (COTTAGE_TYPES[rtId]) {
        cottageNights   += ov;
        cottageRevenue  += rsWeekRev;
        cottageLosList.push(totalNights);
      } else if (DANIEL_TYPES[rtId]) {
        danielNights += ov;
      } else if (ALEN_TYPES[rtId]) {
        alenNights += ov;
      }
    });

    revFurako  += bkFurako;
    revBesedka += bkBesedka;
    revOther   += bkOther;
    breakfastCount += bkBreakfast;
  });

  var W = 7; // дней в неделе
  var totalWithCancel = total + cancelledCount;

  var adr = (cottageNights > 0) ? Math.round(cottageRevenue / cottageNights) : 0;
  var avgLos = (cottageLosList.length > 0)
    ? round2_(cottageLosList.reduce(function(a, b) { return a + b; }, 0) / cottageLosList.length)
    : 0;

  return {
    rev_rooms:      Math.round(revRooms),
    rev_furako:     Math.round(revFurako),
    rev_besedka:    Math.round(revBesedka),
    rev_other:      Math.round(revOther),
    rev_nf:         Math.round(revRooms + revFurako + revBesedka + revOther),
    guests:         guests,
    returning_pct:  total > 0 ? round4_(returningCount / total) : 0,
    direct_pct:     total > 0 ? round4_(directCount    / total) : 0,
    cancel_pct:     totalWithCancel > 0 ? round4_(cancelledCount / totalWithCancel) : 0,
    adr:            adr,
    avg_los:        avgLos,
    occ_cottage:    round4_(cottageNights / (UNITS_COTTAGE * W)),
    occ_daniel:     round4_(danielNights  / (UNITS_DANIEL  * W)),
    occ_alen:       round4_(alenNights    / (UNITS_ALEN    * W)),
    breakfast_count: breakfastCount,
  };
}


// ═══════════════════════════════════════════════════════════════
// МОНБЛАН: ЧТЕНИЕ ДАННЫХ ЗА НЕДЕЛЮ
// ═══════════════════════════════════════════════════════════════

/**
 * Открывает трекинг-лист Монблан, находит столбец с нужной неделей,
 * возвращает выручку (строка 4) и кол-во чеков (строка 42).
 */
function readMonblan_(weekNum, year) {
  try {
    var mbSS = SpreadsheetApp.openById(MONBLAN_SHEET_ID);
    var mbSh = getSheetByGid_(mbSS, MONBLAN_GID);
    if (!mbSh) {
      Logger.log('  ⚠️ Монблан: лист GID=' + MONBLAN_GID + ' не найден');
      return {revenue: 0, checks: 0};
    }

    // Строки 1 и 2 — год и номер недели (данные начинаются со столбца B = col 2)
    var yearRow = mbSh.getRange(1, 2, 1, 200).getValues()[0];
    var weekRow = mbSh.getRange(2, 2, 1, 200).getValues()[0];

    var mbCol = -1;
    for (var i = 0; i < weekRow.length; i++) {
      if (Number(weekRow[i]) === weekNum && Number(yearRow[i]) === year) {
        mbCol = i + 2; // +2: начинаем с col B (1-based = 2)
        break;
      }
    }

    if (mbCol === -1) {
      Logger.log('  ⚠️ Монблан: неделя ' + weekNum + '/' + year + ' не найдена');
      return {revenue: 0, checks: 0};
    }

    var revenue = mbSh.getRange(4,  mbCol).getValue() || 0;  // Выручка всего
    var checks  = mbSh.getRange(42, mbCol).getValue() || 0;  // Кол-во чеков

    return {revenue: revenue, checks: checks};

  } catch(e) {
    Logger.log('  ❌ Ошибка чтения Монблан: ' + e.message);
    return {revenue: 0, checks: 0};
  }
}


// ═══════════════════════════════════════════════════════════════
// ПРОШЛЫЙ ГОД: ПОИСК ЛИСТА «2025»
// ═══════════════════════════════════════════════════════════════

/**
 * Возвращает название листа с «2025» в имени (или null если не найден).
 * Результат используется в setFormulas_ для построения INDEX/MATCH формулы.
 */
function findPrevYearSheetName_(ss) {
  var sheets = ss.getSheets();
  // Сначала ищем точное совпадение «2025»
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getName() === '2025') return '2025';
  }
  // Если нет — любое имя с «2025», кроме «старый»
  for (var j = 0; j < sheets.length; j++) {
    var n = sheets[j].getName();
    if (n.indexOf('2025') !== -1 && n.indexOf('старый') === -1) return n;
  }
  return null;
}


// ═══════════════════════════════════════════════════════════════
// TRAVELLINE: БРОНИ НА СЛЕДУЮЩИЙ КАЛЕНДАРНЫЙ МЕСЯЦ
// ═══════════════════════════════════════════════════════════════

/**
 * Запрашивает TravelLine и возвращает суммарную выручку
 * активных броней с заездом в следующем календарном месяце.
 */
function collectNextMonthBookings_(token) {
  try {
    // Даты следующего месяца
    var now = new Date();
    var nextMonthStart = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    var nextMonthEnd   = new Date(now.getFullYear(), now.getMonth() + 2, 0); // последний день

    Logger.log('  Следующий месяц: ' +
               Utilities.formatDate(nextMonthStart, 'UTC', 'dd.MM.yyyy') + ' – ' +
               Utilities.formatDate(nextMonthEnd,   'UTC', 'dd.MM.yyyy'));

    // Собираем номера броней с заездом в следующем месяце
    var collected = collectBookings_(token, nextMonthStart, nextMonthEnd);
    Logger.log('  Активных броней на след. мес.: ' + collected.active.length);
    if (collected.active.length === 0) return 0;

    // Загружаем детали и суммируем полную стоимость проживания
    var bookings = fetchBookingDetails_(token, collected.active);
    var totalRevenue = 0;
    var nextMonthStartStr = Utilities.formatDate(nextMonthStart, 'UTC', 'yyyy-MM-dd');
    var nextMonthEndStr   = Utilities.formatDate(nextMonthEnd,   'UTC', 'yyyy-MM-dd');

    bookings.forEach(function(bk) {
      (bk.roomStays || []).forEach(function(rs) {
        // Берём только roomStays с заездом в следующем месяце
        var arr = (rs.stayDates.arrivalDateTime || '').substring(0, 10);
        if (arr >= nextMonthStartStr && arr <= nextMonthEndStr) {
          totalRevenue += ((rs.total || {}).priceAfterTax) || 0;
        }
      });
    });

    return Math.round(totalRevenue);

  } catch(e) {
    Logger.log('  ❌ Ошибка collectNextMonthBookings_: ' + e.message);
    return 0;
  }
}


// ═══════════════════════════════════════════════════════════════
// ТАБЛИЦА: НАЙТИ ИЛИ СОЗДАТЬ СТОЛБЕЦ НЕДЕЛИ
// ═══════════════════════════════════════════════════════════════

/**
 * Ищет столбец с номером week.num в строке 1.
 * Если не нашёл — добавляет новый столбец после последнего заполненного.
 * Возвращает номер столбца (1-based).
 */
function findOrCreateWeekCol_(sh, week) {
  var row1 = sh.getRange(1, 1, 1, 300).getValues()[0];

  // Ищем существующий столбец (данные начинаются с col C = index 2)
  for (var i = 2; i < row1.length; i++) {
    if (Number(row1[i]) === week.num) {
      var existingCol = i + 1; // 1-based
      // Всегда обновляем диапазон дат в строке 2
      sh.getRange(ROWS.DATES, existingCol).setValue(week.dateLabel);
      return existingCol;
    }
  }

  // Не нашли — определяем последний заполненный столбец
  var lastCol = 2; // минимум col B
  for (var j = 2; j < row1.length; j++) {
    if (row1[j] !== '' && row1[j] !== null && row1[j] !== undefined) {
      lastCol = j + 1; // 1-based
    }
  }
  var newCol = lastCol + 1;

  // Создаём заголовки нового столбца
  sh.getRange(ROWS.WEEK_NUM, newCol).setValue(week.num);
  sh.getRange(ROWS.DATES,    newCol).setValue(week.dateLabel);

  Logger.log('  Создан новый столбец ' + columnToLetter_(newCol) +
             ' для недели ' + week.num);
  return newCol;
}


// ═══════════════════════════════════════════════════════════════
// ТАБЛИЦА: ЗАПИСЬ ДАННЫХ
// ═══════════════════════════════════════════════════════════════

function writeData_(sh, col, tl, mb, nextMonthRev) {
  // Строка 5: Доход общий (НФ + Монблан)
  sh.getRange(ROWS.TOTAL_REVENUE, col).setValue(tl.rev_nf + mb.revenue);
  // Строка 7 — формула на лист «2025», ставится в setFormulas_

  // Монблан
  sh.getRange(ROWS.MB_REVENUE, col).setValue(mb.revenue);
  sh.getRange(ROWS.MB_CHECKS,  col).setValue(mb.checks);

  // Завтраки
  sh.getRange(ROWS.BREAKFASTS, col).setValue(tl.breakfast_count);

  // Дополнительные услуги
  sh.getRange(ROWS.FURAKO,   col).setValue(tl.rev_furako);
  sh.getRange(ROWS.BESEDKA,  col).setValue(tl.rev_besedka);
  sh.getRange(ROWS.OTHER_SVC,col).setValue(tl.rev_other);

  // Загрузка и продажи
  sh.getRange(ROWS.GUESTS,       col).setValue(tl.guests);
  sh.getRange(ROWS.RETURNING_PCT,col).setValue(tl.returning_pct);
  sh.getRange(ROWS.ADR,          col).setValue(tl.adr);
  sh.getRange(ROWS.AVG_LOS,      col).setValue(tl.avg_los);
  sh.getRange(ROWS.OCC_COTTAGE,  col).setValue(tl.occ_cottage);
  sh.getRange(ROWS.OCC_DANIEL,   col).setValue(tl.occ_daniel);
  sh.getRange(ROWS.OCC_ALEN,     col).setValue(tl.occ_alen);
  sh.getRange(ROWS.CANCEL_PCT,   col).setValue(tl.cancel_pct);
  // Строка 33 (DIRECT_PCT) — ручной ввод, не трогаем

  // Строка 36: Забронировано на следующий календарный месяц
  if (nextMonthRev > 0) {
    sh.getRange(ROWS.BOOKED_NEXT_MO, col).setValue(nextMonthRev);
  }
  // Строка 37 (DYNAMIC) — ручной ввод, не трогаем
}


// ═══════════════════════════════════════════════════════════════
// ТАБЛИЦА: ФОРМУЛЫ ДЛЯ РАСЧЁТНЫХ СТРОК
// ═══════════════════════════════════════════════════════════════

/**
 * Устанавливает формулы в расчётные строки нового столбца.
 * Вызывается каждый раз (идемпотентно — setFormula перезаписывает).
 *
 * Проверено по данным недели 1:
 *   Row 13 (F&B %):  C11/C5  = 2651440/8162691 = 32% ✓
 *   Row 24 (RevPAR): C23*C28 = 8531 × 87% = 7422 ✓
 *   Row 25 (RevPAC): C5/C21  = 8162691/728 = 11212 ✓
 *   Row 9  (% ПГ):   C8/C7   = 22738580/21135971 = 108% ✓
 *   Row 38 (% плана): C36/C35
 */
function setFormulas_(sh, col, prevSheetName) {
  var X = columnToLetter_(col);

  // Строка 6: доля нарастающего к недельной выручке
  sh.getRange(6, col).setFormula('=' + X + '8/' + X + '5');

  // Строка 7: выручка прошлого года (INDEX/MATCH по номеру недели из строки 1)
  if (prevSheetName) {
    var esc = "'" + prevSheetName.replace(/'/g, "''") + "'";
    sh.getRange(ROWS.PREV_YEAR_REV, col).setFormula(
      '=IFERROR(INDEX(' + esc + '!5:5,MATCH(' + X + '1,' + esc + '!1:1,0)),0)'
    );
  }

  // F&B % от оборота
  sh.getRange(ROWS.FB_PCT, col).setFormula('=' + X + '11/' + X + '5');

  // RevPAR = ADR × Загрузка коттеджей
  sh.getRange(ROWS.REVPAR, col).setFormula('=' + X + '23*' + X + '28');

  // RevPAC = Доход общий / Гостей всего
  sh.getRange(ROWS.REVPAC, col).setFormula('=' + X + '5/'  + X + '21');

  // % к факту прошлого года = Нарастающий итог / Выручка ПГ
  sh.getRange(ROWS.PCT_PLAN_MO, col).setFormula('=' + X + '8/' + X + '7');

  // % выполнения плана след. месяца = Забронировано / План
  sh.getRange(ROWS.PCT_PLAN_NEXT, col).setFormula('=' + X + '36/' + X + '35');

  // Строка 37 (Динамика) — ручной ввод, формулу не ставим
}


// ═══════════════════════════════════════════════════════════════
// ПЕРЕНОС ДАННЫХ ИЗ «2026 СТАРЫЙ» → «2026» (строки 40+)
// ═══════════════════════════════════════════════════════════════

/**
 * Копирует данные строк 40 и ниже из листа «2026 старый» в лист «2026».
 * Логика: если в «2026» ячейка пуста — берём значение из «2026 старый».
 * Непустые ячейки в «2026» не трогаем.
 * Совпадение столбцов — по номеру недели в строке 1.
 * Запускать один раз вручную из GAS-редактора.
 */
function copyRowsFromOldSheet() {
  var ss    = SpreadsheetApp.getActiveSpreadsheet();
  var newSh = getSheetByGid_(ss, HOTEL_SHEET_GID);

  // Ищем лист «2026 старый»
  var oldSh = null;
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getName() === '2026 старый') { oldSh = sheets[i]; break; }
  }
  if (!oldSh) {
    Logger.log('❌ Лист «2026 старый» не найден');
    return;
  }
  Logger.log('▶ Перенос из «2026 старый», строки 40+');

  var START_ROW = 40;
  var END_ROW   = Math.max(oldSh.getLastRow(), newSh.getLastRow());
  var NUM_ROWS  = END_ROW - START_ROW + 1;
  if (NUM_ROWS <= 0) { Logger.log('Нет строк от 40'); return; }
  Logger.log('  Строк для переноса: ' + NUM_ROWS + ' (строки ' + START_ROW + '–' + END_ROW + ')');

  // Карта номер недели → столбец в «2026 старый»
  var oldRow1 = oldSh.getRange(1, 1, 1, 300).getValues()[0];
  var oldColByWeek = {};
  for (var j = 0; j < oldRow1.length; j++) {
    var wn = Number(oldRow1[j]);
    if (wn) oldColByWeek[wn] = j + 1; // 1-based
  }

  // Проходим по столбцам нового листа (недели с col C = index 2)
  var newRow1 = newSh.getRange(1, 1, 1, 300).getValues()[0];
  var totalCopied = 0;

  for (var c = 2; c < newRow1.length; c++) {
    var weekNum = Number(newRow1[c]);
    if (!weekNum) continue;

    var oldCol = oldColByWeek[weekNum];
    if (!oldCol) {
      Logger.log('  ⚠️ Нед.' + weekNum + ' не найдена в «2026 старый»');
      continue;
    }
    var newCol = c + 1; // 1-based

    var oldVals = oldSh.getRange(START_ROW, oldCol, NUM_ROWS, 1).getValues();
    var newVals = newSh.getRange(START_ROW, newCol, NUM_ROWS, 1).getValues();

    // Мерж: в пустые ячейки «2026» кладём значение из «2026 старый»
    var merged = [];
    var rowsCopied = 0;
    for (var r = 0; r < NUM_ROWS; r++) {
      var ov = oldVals[r][0];
      var nv = newVals[r][0];
      var newEmpty = (nv === '' || nv === null || nv === undefined);
      var oldHasValue = (ov !== '' && ov !== null && ov !== undefined);
      if (newEmpty && oldHasValue) {
        merged.push([ov]);
        rowsCopied++;
      } else {
        merged.push([nv]); // оставляем как есть
      }
    }

    if (rowsCopied > 0) {
      newSh.getRange(START_ROW, newCol, NUM_ROWS, 1).setValues(merged);
      Logger.log('  Нед.' + weekNum + ' (кол.' + columnToLetter_(newCol) + '): ' +
                 rowsCopied + ' ячеек скопировано');
      totalCopied += rowsCopied;
    } else {
      Logger.log('  Нед.' + weekNum + ': всё уже заполнено, пропуск');
    }
  }

  SpreadsheetApp.flush();
  Logger.log('✅ Перенос завершён. Всего скопировано ячеек: ' + totalCopied);
}


// ═══════════════════════════════════════════════════════════════
// БЭКФИЛЛ: ЗАПОЛНЕНИЕ ПРОШЕДШИХ НЕДЕЛЬ
// ═══════════════════════════════════════════════════════════════

/**
 * Заполняет данные для недель 17–21 (2026).
 * Запускать один раз вручную из GAS-редактора.
 * Строка 36 (забронировано) НЕ перезаписывается — там могут быть ручные данные.
 */
function backfillFromWeek17() {
  var ss    = SpreadsheetApp.getActiveSpreadsheet();
  var sh    = getSheetByGid_(ss, HOTEL_SHEET_GID);
  var prevSheetName = findPrevYearSheetName_(ss);
  var token = getTLToken_();
  var year  = 2026;
  var START_WEEK = 17;
  var END_WEEK   = 21;

  Logger.log('▶ Бэкфилл недель ' + START_WEEK + '–' + END_WEEK + ' (' + year + ')');

  for (var weekNum = START_WEEK; weekNum <= END_WEEK; weekNum++) {
    Logger.log('  ──── Неделя ' + weekNum + ' ────');
    var dates = getWeekDates_(weekNum, year);
    var dateLabel = Utilities.formatDate(dates.start, 'UTC', 'dd.MM') + '-' +
                    Utilities.formatDate(dates.end,   'UTC', 'dd.MM');

    var week = {num: weekNum, year: year,
                start: dates.start, end: dates.end, dateLabel: dateLabel};

    var col = findOrCreateWeekCol_(sh, week);
    Logger.log('  Столбец: ' + columnToLetter_(col));

    // TravelLine
    var collected = collectBookings_(token, week.start, week.end);
    Logger.log('  TL: активных=' + collected.active.length +
               ', отменённых=' + collected.cancelled.length);
    var bookings = fetchBookingDetails_(token, collected.active);
    var tl = calcMetrics_(bookings, collected.cancelled.length, week.start, week.end);
    Logger.log('  НФ выручка=' + tl.rev_nf + ', гостей=' + tl.guests);

    // Монблан
    var mb = readMonblan_(weekNum, year);
    Logger.log('  Монблан: выручка=' + mb.revenue);

    // Записываем (nextMonthRev=0 — не трогаем ручные данные в строке 36)
    writeData_(sh, col, tl, mb, 0);
    setFormulas_(sh, col, prevSheetName);

    Logger.log('  ✅ Неделя ' + weekNum + ' записана → ' + columnToLetter_(col));
    Utilities.sleep(1500); // пауза между неделями
  }

  SpreadsheetApp.flush();
  Logger.log('✅ Бэкфилл завершён: недели ' + START_WEEK + '–' + END_WEEK);
}


// ═══════════════════════════════════════════════════════════════
// УТИЛИТЫ — ДАТЫ И НЕДЕЛИ
// ═══════════════════════════════════════════════════════════════

/**
 * Возвращает предыдущую ISO-неделю.
 * При запуске в понедельник берёт неделю -1.
 */
function getPrevWeek_() {
  var now = new Date();
  var dayOfWeek = now.getDay(); // 0=вс, 1=пн, ..., 6=сб

  // Начало прошлой недели (понедельник)
  var daysBack = (dayOfWeek === 0) ? 6 : dayOfWeek + 6;
  var weekStart = new Date(now);
  weekStart.setDate(now.getDate() - daysBack);
  weekStart.setHours(0, 0, 0, 0);

  var weekEnd = new Date(weekStart);
  weekEnd.setDate(weekStart.getDate() + 6);
  weekEnd.setHours(23, 59, 59, 0);

  var weekNum = getISOWeekNumber_(weekStart);
  var year    = weekStart.getFullYear();

  // Проверка перехода года (неделя 52/53 → 1)
  // ISO: если 29, 30, 31 декабря в воскресенье/пятницу — могут быть в неделе 1 след. года
  var isoYear = getISOYear_(weekStart);

  var dateLabel = Utilities.formatDate(weekStart, 'UTC', 'dd.MM') + '-' +
                  Utilities.formatDate(weekEnd,   'UTC', 'dd.MM');

  return {
    num:       weekNum,
    year:      isoYear,  // ISO-год (может отличаться от calendar year)
    start:     weekStart,
    end:       weekEnd,
    dateLabel: dateLabel,
  };
}

/** Номер ISO-недели для даты */
function getISOWeekNumber_(date) {
  var d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  var dayNum = d.getUTCDay() || 7; // воскресенье = 7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  var yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
}

/** ISO-год (первый четверг недели определяет год) */
function getISOYear_(date) {
  var d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  var dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  return d.getUTCFullYear();
}

/**
 * Возвращает {start, end} для ISO-недели weekNum в году year.
 * start = понедельник, end = воскресенье.
 */
function getWeekDates_(weekNum, year) {
  // 4 января всегда в первой ISO-неделе
  var jan4    = new Date(Date.UTC(year, 0, 4));
  var jan4Day = jan4.getUTCDay() || 7; // пн=1 ... вс=7
  var monday  = new Date(jan4.getTime());
  monday.setUTCDate(jan4.getUTCDate() - jan4Day + 1 + (weekNum - 1) * 7);
  monday.setHours(0, 0, 0, 0);

  var sunday = new Date(monday.getTime());
  sunday.setDate(monday.getDate() + 6);
  sunday.setHours(23, 59, 59, 0);

  return {start: monday, end: sunday};
}


/**
 * Создаёт forged continueToken для TravelLine API.
 * Позволяет начать сканирование с произвольной даты.
 * Аналог Python: forge_token() в travelline_collector.py
 */
function forgeToken_(date) {
  var utcMs = Date.UTC(date.getFullYear(), date.getMonth(), date.getDate());
  var payload = JSON.stringify({'BookingIds': [], 'MillisecondsFrom': utcMs});
  return Utilities.base64Encode(payload).replace(/\n/g, '');
}

/** Количество ночей брони, попадающих в диапазон [weekStart, weekEnd] */
function overlapNights_(arrStr, depStr, weekStart, weekEnd) {
  var arr   = new Date(arrStr.substring(0, 10) + 'T00:00:00Z');
  var dep   = new Date(depStr.substring(0, 10) + 'T00:00:00Z');
  var wEnd1 = new Date(weekEnd.getTime() + 86400000); // weekEnd+1 день

  var start = arr > weekStart ? arr : weekStart;
  var end   = dep < wEnd1    ? dep  : wEnd1;

  return Math.max(0, (end - start) / 86400000);
}

/** Классификация сервиса по имени и коду тарифа */
function svcCategory_(name, mealCode) {
  if (mealCode === 'BreakFast' || name.toLowerCase().indexOf('завтрак') !== -1) {
    return 'breakfast';
  }
  var n = name.toLowerCase();
  if (n.indexOf('фурако') !== -1 || n.indexOf('баня') !== -1 ||
      n.indexOf('бани')   !== -1 || n.indexOf('банн') !== -1) {
    return 'furako';
  }
  if (n.indexOf('беседк') !== -1 || n.indexOf('мангал') !== -1) {
    return 'besedka';
  }
  return 'other';
}

/** Форматирует дату как 'YYYYMMDD' */
function formatDate_(date) {
  return Utilities.formatDate(date, 'UTC', 'yyyyMMdd');
}


// ═══════════════════════════════════════════════════════════════
// УТИЛИТЫ — ТАБЛИЦА
// ═══════════════════════════════════════════════════════════════

/** Находит лист по Sheet ID (GID) */
function getSheetByGid_(ss, gid) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === gid) return sheets[i];
  }
  return null;
}

/** Конвертирует номер столбца (1-based) в буквенное обозначение: 1→A, 27→AA */
function columnToLetter_(col) {
  var result = '';
  var n = col;
  while (n > 0) {
    n--;
    result = String.fromCharCode(65 + (n % 26)) + result;
    n = Math.floor(n / 26);
  }
  return result;
}

/** Округление до 2 знаков */
function round2_(x) { return Math.round(x * 100) / 100; }

/** Округление до 4 знаков (для хранения долей, напр. 0.8745) */
function round4_(x) { return Math.round(x * 10000) / 10000; }
