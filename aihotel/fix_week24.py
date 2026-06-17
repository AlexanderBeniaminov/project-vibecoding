#!/usr/bin/env python3
"""
Заполняет лист «2026» финансового отчёта за неделю 24 из трёх источников:
  1. TravelLine — метрики отеля (строки 5,14,17–19,21–23,27–30,32,33,72,74)
  2. Монблан — выручка (строка 11) и кол-во чеков (строка 12)
  3. Воронка «2026 ✓» — сегменты гостей (строки 40–52)

Логика полностью соответствует GAS main.gs :: backfillWeeks().
"""
import base64, json, os, re, time
from datetime import date, datetime, timedelta

import gspread
import requests
from google.oauth2.service_account import Credentials

# ─── ПАРАМЕТРЫ ───────────────────────────────────────────────
WEEK_NUMBER = 24
YEAR        = 2026

# Идентификаторы внешних таблиц (из main.gs)
MONBLAN_SHEET_ID = '1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI'
MONBLAN_GID      = 2051236241
SEG_SHEET_ID     = '1CdeyCx0VlzqNpUSDhmIdJPZYuR_1nv33bHu5FLnHX_8'
SEG_SHEET_NAME   = '2026 ✓'

# Маппинг строк сегментов: [строка в «2026 ✓», строка в финансовом отчёте]
SEG_MAPPING = [
    (6,  51),   # Физики: Бронь
    (9,  52),   # Физики: Сумма
    (14, 40),   # ДР: Бронь
    (16, 41),   # ДР: Проживания
    (17, 42),   # ДР: Сумма
    (22, 44),   # Группы: Бронь
    (24, 45),   # Группы: Проживания
    (25, 46),   # Группы: Сумма
    (30, 48),   # Корп: Бронь
    (33, 49),   # Корп: Сумма
]

# Типы номеров (из travelline_collector.py)
COTTAGE_TYPES = {152774,183368,198656,152776,183367,213511,296293,
                 123405,183411,183414,183438,208986,208987}
DANIELLE_TYPES = {84929,84928,84934,84939}
ALEN_TYPES     = {82359,82361,82364,82365,82367,220392,220405}
TOTAL_COTTAGES, TOTAL_DANIELLE, TOTAL_ALEN = 21, 15, 58

TL_AUTH_URL = 'https://partner.tlintegration.com/auth/token'
TL_API_BASE = 'https://partner.tlintegration.com/api/read-reservation/v1'

# ─── ЗАГРУЗКА .env ────────────────────────────────────────────
def _load_env(path='.env'):
    if not os.path.exists(path):
        return
    content = open(path).read()
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith('#') or '=' not in line:
            i += 1
            continue
        key, val = line.split('=', 1)
        key, val = key.strip(), val.strip()
        if val.startswith('{'):
            jlines = [val]
            depth = val.count('{') - val.count('}')
            i += 1
            while depth > 0 and i < len(lines):
                jlines.append(lines[i])
                depth += lines[i].count('{') - lines[i].count('}')
                i += 1
            os.environ.setdefault(key, '\n'.join(jlines))
        else:
            os.environ.setdefault(key, val)
            i += 1

_load_env()

def _env(k):
    v = os.environ.get(k, '').strip()
    if not v: raise RuntimeError(f'{k} не задана')
    return v

CLIENT_ID        = _env('TL_CLIENT_ID')
CLIENT_SECRET    = _env('TL_CLIENT_SECRET')
PROPERTY_ID      = _env('TL_PROPERTY_ID')
FINANCE_SHEET_ID = _env('FINANCE_SHEET_ID')
GOOGLE_CREDS     = json.loads(_env('GOOGLE_CREDS_JSON'))


# ─── GOOGLE SHEETS КЛИЕНТ ─────────────────────────────────────
def gs_client():
    creds = Credentials.from_service_account_info(
        GOOGLE_CREDS, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.Client(auth=creds)


def col_letter(n):
    r = ''
    while n > 0:
        n, rem = divmod(n - 1, 26)
        r = chr(65 + rem) + r
    return r


def find_week_col(ws, week_num):
    """Находит 1-based номер колонки с данной неделей в строке 1."""
    row1 = ws.row_values(1)
    for i, v in enumerate(row1):
        if str(v).strip() == str(week_num):
            return i + 1
    return None


# ─── TRAVELLINE ───────────────────────────────────────────────
def tl_token():
    r = requests.post(TL_AUTH_URL, data={
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET},
        headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=30)
    r.raise_for_status()
    return r.json()['access_token']


def forge_token(dt):
    ts = int(datetime(dt.year, dt.month, dt.day).timestamp() * 1000)
    return base64.b64encode(json.dumps({'BookingIds': [], 'MillisecondsFrom': ts},
                                       separators=(',', ':')).encode()).decode()


def overlap_nights(arr_s, dep_s, w_start, w_end):
    arr = date.fromisoformat(arr_s[:10])
    dep = date.fromisoformat(dep_s[:10])
    return max(0, (min(dep, w_end + timedelta(1)) - max(arr, w_start)).days)


def svc_cat(name, meal_code):
    if meal_code == 'BreakFast' or 'завтрак' in name.lower(): return 'breakfast'
    n = name.lower()
    if any(k in n for k in ('фурако','баня','бани','банн')): return 'furako'
    if any(k in n for k in ('беседк','мангал')): return 'besedka'
    return 'other'


def collect_travelline(week_start, week_end):
    token = tl_token()
    print('✅ TravelLine: токен получен')
    hdrs = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    prefixes = set()
    d = week_start - timedelta(21)
    while d <= week_end:
        prefixes.add(d.strftime('%Y%m%d'))
        d += timedelta(1)

    scan_from = week_start - timedelta(90)
    scan_end  = week_end   + timedelta(14)
    ct = forge_token(scan_from)
    active, cancelled = [], []
    page = 0

    print(f'Сканируем брони {scan_from} – {scan_end}...')
    while page < 80:
        r = requests.get(f'{TL_API_BASE}/properties/{PROPERTY_ID}/bookings',
            headers=hdrs, params={'pageSize': 100, 'continueToken': ct}, timeout=30)
        if r.status_code != 200:
            print(f'  ❌ {r.status_code}: {r.text[:200]}'); break

        data = r.json()
        summaries = data.get('bookingSummaries', [])
        page += 1

        for s in summaries:
            num = s.get('number', '')
            if num[:8] in prefixes:
                (active if s['status'] == 'Active' else cancelled).append(num)

        last_mod = summaries[-1]['modifiedDateTime'][:10] if summaries else '?'
        print(f'  Стр.{page}: {len(summaries)} броней, '
              f'активных={len(active)}, отменённых={len(cancelled)}, до={last_mod}')

        if last_mod.replace('-', '') > scan_end.strftime('%Y%m%d'):
            print('  Период пройден.'); break

        ct = data.get('continueToken', '')
        if not ct or not data.get('hasMoreData', False): break
        time.sleep(0.4)

    print(f'Итого: {len(active)} активных, {len(cancelled)} отменённых\n')
    if not active and not cancelled:
        print('⚠️ Брони не найдены.'); return None

    # Загружаем детали
    print(f'Загружаем детали {len(active)} броней...')
    bookings = []
    for i, num in enumerate(active, 1):
        r = requests.get(f'{TL_API_BASE}/properties/{PROPERTY_ID}/bookings/{num}',
            headers=hdrs, timeout=30)
        if r.status_code == 200:
            bk = r.json().get('booking')
            if bk: bookings.append(bk)
        if i % 10 == 0 or i == len(active):
            print(f'  {i}/{len(active)} загружено')
        time.sleep(0.4)

    # Считаем метрики
    rev_rooms = rev_furako = rev_besedka = rev_other = 0.0
    guests = returning = direct_count = breakfast_count = 0
    cottage_nights = danielle_nights = alen_nights = 0
    cottage_los = []
    cottage_departures = hostel_departures = 0
    rt_stats = {}

    for bk in bookings:
        loyalty = ((bk.get('guaranteeInfo') or {}).get('loyalty') or {})
        if loyalty.get('cards'): returning += 1
        src = ((bk.get('source') or {}).get('type') or '')
        if src in ('BookingEngine', 'PMS'): direct_count += 1

        bk_bre = bk_fur = bk_bes = bk_oth = 0.0
        for rs in bk.get('roomStays', []):
            arr = rs['stayDates']['arrivalDateTime']
            dep = rs['stayDates']['departureDateTime']
            rt_id_str = rs['roomType']['id']
            rt_id = int(rt_id_str) if rt_id_str.isdigit() else rt_id_str
            rt_name = rs['roomType']['name']
            ov = overlap_nights(arr, dep, week_start, week_end)

            dep_d = date.fromisoformat(dep[:10])
            if week_start <= dep_d <= week_end:
                if rt_id in COTTAGE_TYPES: cottage_departures += 1
                elif rt_id in DANIELLE_TYPES or rt_id in ALEN_TYPES: hostel_departures += 1

            if ov == 0: continue

            total_n = max(1, (date.fromisoformat(dep[:10]) - date.fromisoformat(arr[:10])).days)
            ratio = ov / total_n
            svc_extract = 0.0
            for svc in rs.get('services', []):
                sp = (svc.get('total') or {}).get('priceAfterTax', 0.0)
                cat = svc_cat(svc.get('name', ''), svc.get('mealPlanCode', ''))
                if cat == 'breakfast':   bk_bre += 1
                elif cat == 'furako':    svc_extract += sp; bk_fur += sp * ratio
                elif cat == 'besedka':   svc_extract += sp; bk_bes += sp * ratio
                else:                    svc_extract += sp; bk_oth += sp * ratio

            rs_rev = (rs['total']['priceAfterTax'] - svc_extract) * ratio
            rev_rooms += rs_rev
            guests += rs['guestCount']['adultCount'] + len(rs['guestCount']['childAges'])

            if rt_id not in rt_stats:
                rt_stats[rt_id] = {'name': rt_name, 'nights': 0, 'revenue': 0.0}
            rt_stats[rt_id]['nights']  += ov
            rt_stats[rt_id]['revenue'] += rs_rev

            if rt_id in COTTAGE_TYPES:
                cottage_nights += ov; cottage_los.append(total_n)
            elif rt_id in DANIELLE_TYPES:
                danielle_nights += ov
            elif rt_id in ALEN_TYPES:
                alen_nights += ov

        rev_furako  += bk_fur; rev_besedka += bk_bes
        rev_other   += bk_oth; breakfast_count += int(bk_bre)

    total = len(bookings)
    cottage_rev = sum(v['revenue'] for k, v in rt_stats.items() if k in COTTAGE_TYPES)
    total_wc = total + len(cancelled)

    metrics = {
        5:  round(rev_rooms),
        14: breakfast_count,
        17: round(rev_furako),
        18: round(rev_besedka),
        19: round(rev_other),
        21: guests,
        28: round(cottage_nights / (TOTAL_COTTAGES * 7), 4),
        29: round(danielle_nights / (TOTAL_DANIELLE * 7), 4),
        30: round(alen_nights    / (TOTAL_ALEN     * 7), 4),
        72: cottage_departures,
        74: hostel_departures,
    }
    if total > 0:
        metrics[22] = round(returning / total, 4)
        metrics[33] = round(direct_count / total, 4)
    if total_wc > 0:
        metrics[32] = round(len(cancelled) / total_wc, 4)
    if cottage_nights > 0:
        metrics[23] = round(cottage_rev / cottage_nights)
        metrics[27] = round(sum(cottage_los) / len(cottage_los), 1)

    return metrics


# ─── МОНБЛАН ──────────────────────────────────────────────────
def read_monblan(client, week_num, year):
    """Читает строки 4 (выручка) и 42 (чеки) из Монблан-трекинга."""
    try:
        mb_ss = client.open_by_key(MONBLAN_SHEET_ID)
        sheets = mb_ss.worksheets()
        mb_sh = next((s for s in sheets if s.id == MONBLAN_GID), None)
        if not mb_sh:
            print(f'  ⚠️ Монблан: лист GID={MONBLAN_GID} не найден')
            return 0, 0

        year_row = mb_sh.row_values(1)
        week_row = mb_sh.row_values(2)

        # Попытка 1: точное совпадение год+неделя
        mb_col = None
        for i, (yr_v, wk_v) in enumerate(zip(year_row[1:], week_row[1:]), start=2):
            yr = int(re.sub(r'\D', '', str(yr_v))) if re.sub(r'\D', '', str(yr_v)) else 0
            wk = int(str(wk_v).strip()) if str(wk_v).strip().isdigit() else 0
            if wk == week_num and yr == year:
                mb_col = i
                break

        # Попытка 2: последняя заполненная колонка
        if mb_col is None:
            print(f'  ⚠️ Монблан: неделя {week_num}/{year} не найдена, берём последнюю')
            for i in range(len(week_row) - 1, 0, -1):
                if str(week_row[i]).strip():
                    mb_col = i + 1
                    print(f'  ℹ️ Монблан: колонка {mb_col} (нед.{week_row[i]})')
                    break

        if mb_col is None:
            print('  ⚠️ Монблан: данные не найдены')
            return 0, 0

        def clean_num(v):
            return str(v).replace('\xa0', '').replace(' ', '').replace(',', '.').strip()

        revenue = mb_sh.cell(4,  mb_col).value or 0
        checks  = mb_sh.cell(42, mb_col).value or 0
        return float(clean_num(revenue) or 0), int(float(clean_num(checks) or 0))
    except Exception as e:
        print(f'  ❌ Монблан ошибка: {e}')
        return 0, 0


# ─── ВОРОНКА (сегменты) ───────────────────────────────────────
def read_segments(client, week_num):
    """Читает строки сегментов из листа «2026 ✓» файла Евгении/Надежды."""
    try:
        seg_ss = client.open_by_key(SEG_SHEET_ID)
        seg_sh = seg_ss.worksheet(SEG_SHEET_NAME)

        # Строка 1 листа воронки: недели начиная с колонки C (col 3)
        row1 = seg_sh.row_values(1)
        seg_col = None
        for i, v in enumerate(row1[2:], start=3):  # col C = index 2 → 1-based 3
            if str(v).strip() == str(week_num):
                seg_col = i
                break

        if seg_col is None:
            print(f'  ⚠️ Воронка: неделя {week_num} не найдена в строке 1')
            return {}

        def clean_num(v):
            return str(v).replace('\xa0', '').replace(' ', '').replace(',', '.').strip()

        result = {}
        for seg_row, fin_row in SEG_MAPPING:
            v = seg_sh.cell(seg_row, seg_col).value
            c = clean_num(v) if v not in (None, '') else ''
            result[fin_row] = float(c) if c else 0
        return result
    except Exception as e:
        print(f'  ❌ Воронка ошибка: {e}')
        return {}


# ─── ЗАПИСЬ В ТАБЛИЦУ ─────────────────────────────────────────
def write_all(client, week_num, week_start, week_end, tl_metrics, mb_revenue, mb_checks, seg_metrics):
    ss = client.open_by_key(FINANCE_SHEET_ID)
    ws = ss.worksheet('2026')

    col = find_week_col(ws, week_num)
    if col is None:
        row1 = ws.row_values(1)
        col = len(row1) + 1
        ws.update_cell(1, col, week_num)
        date_label = f"{week_start.strftime('%d.%m')}–{week_end.strftime('%d.%m')}"
        ws.update_cell(2, col, date_label)
        print(f'  Создана новая колонка {col_letter(col)} для недели {week_num}')
    else:
        print(f'  Используем колонку {col_letter(col)} для недели {week_num}')

    cl = col_letter(col)
    updates = []

    # TravelLine метрики
    for row, val in tl_metrics.items():
        updates.append({'range': f'{cl}{row}', 'values': [[val]]})

    # Строка 5: Доход общий = НФ + Монблан
    rev_nf = tl_metrics.get(5, 0)
    updates.append({'range': f'{cl}5', 'values': [[rev_nf + mb_revenue]]})

    # Монблан
    updates.append({'range': f'{cl}11', 'values': [[mb_revenue]]})
    updates.append({'range': f'{cl}12', 'values': [[mb_checks]]})

    # Сегменты (Воронка)
    for fin_row, val in seg_metrics.items():
        updates.append({'range': f'{cl}{fin_row}', 'values': [[val]]})

    ws.batch_update(updates, value_input_option='USER_ENTERED')

    # Формулы (RevPAR, RevPAC, F&B %, % к ПГ)
    formulas = [
        (f'{cl}13', f'={cl}11/{cl}5'),            # F&B %
        (f'{cl}24', f'={cl}23*{cl}28'),            # RevPAR
        (f'{cl}25', f'={cl}5/{cl}21'),             # RevPAC
        (f'{cl}9',  f'={cl}8/{cl}7'),              # % к ПГ
    ]
    for cell, formula in formulas:
        ws.update_acell(cell, formula)

    print(f'  ✅ Записано {len(updates)} значений + {len(formulas)} формул → колонка {cl}')


# ─── MAIN ─────────────────────────────────────────────────────
def main():
    week_start = date.fromisocalendar(YEAR, WEEK_NUMBER, 1)
    week_end   = date.fromisocalendar(YEAR, WEEK_NUMBER, 7)
    print(f'\n{"="*60}')
    print(f'Неделя {WEEK_NUMBER} {YEAR}: {week_start} – {week_end}')
    print(f'{"="*60}\n')

    client = gs_client()
    print('✅ Google Sheets: подключились\n')

    # 1. TravelLine
    print('─── TravelLine ───')
    tl_metrics = collect_travelline(week_start, week_end)
    if tl_metrics is None:
        print('❌ TravelLine: нет данных, прерываем.')
        return

    print(f'\nМетрики TravelLine:')
    for row in sorted(tl_metrics):
        print(f'  Строка {row:2d}: {tl_metrics[row]}')

    # 2. Монблан
    print('\n─── Монблан ───')
    mb_revenue, mb_checks = read_monblan(client, WEEK_NUMBER, YEAR)
    print(f'  Выручка = {mb_revenue:,.0f} руб, Чеков = {mb_checks}')

    # 3. Воронка
    print('\n─── Воронка (сегменты) ───')
    seg_metrics = read_segments(client, WEEK_NUMBER)
    if seg_metrics:
        for fin_row, val in sorted(seg_metrics.items()):
            print(f'  Строка {fin_row}: {val}')
    else:
        print('  (нет данных)')

    # 4. Записываем всё в таблицу
    print('\n─── Запись в «2026» ───')
    write_all(client, WEEK_NUMBER, week_start, week_end, tl_metrics, mb_revenue, mb_checks, seg_metrics)

    print(f'\n✅ Готово: неделя {WEEK_NUMBER} — все три источника записаны.')


if __name__ == '__main__':
    main()
