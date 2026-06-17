#!/usr/bin/env python3
"""
Сбор данных TravelLine для указанной недели.
Записывает метрики в лист "2026" финансовой таблицы.

Как использовать:
  - Автоматически (GitHub Actions, понедельник): собирает данные прошедшей недели.
  - Вручную: задайте WEEK_NUMBER и YEAR явно, или оставьте None для авто.
  - DISCOVERY_MODE = True → только показывает типы номеров, НЕ пишет в таблицу.
"""
import base64
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta

import gspread
import requests
from google.oauth2.service_account import Credentials

# ============================================================
# НАСТРОЙКА
# ============================================================
# None = автоматически определить по текущей дате (для GitHub Actions).
# Число  = конкретная неделя (для ручного запуска или повторного сбора).
WEEK_NUMBER    = None    # None → авто; или задайте вручную, например: 18
YEAR           = None    # None → авто; или задайте вручную, например: 2026
DISCOVERY_MODE = False   # True = только показать, False = записать в таблицу


def _resolve_week_year(week_override, year_override):
    """Если значения не заданы — берём прошедшую ISO-неделю (запуск в понедельник)."""
    if week_override is not None and year_override is not None:
        return week_override, year_override
    today = date.today()
    iso   = today.isocalendar()
    # Запускаемся в понедельник → прошедшая неделя = iso.week - 1
    if iso[2] == 1:
        w = iso[1] - 1
        y = iso[0]
        if w == 0:   # переход через Новый год
            dec31 = date(y - 1, 12, 31)
            w = dec31.isocalendar()[1]
            y -= 1
    else:
        w, y = iso[1], iso[0]
    return w, y

# Коттеджи — все типы с "Коттедж" в названии + 6-местный dogfriendly
# Источник: зонд rooms endpoint + booking details
COTTAGE_TYPES = {
    152774,   # Коттедж 4-м с мини-кухней и сауной
    183368,   # Коттедж 4-м с мини-кухней и сауной dogfriendly
    198656,   # Коттедж 4-м с кухней
    152776,   # Коттедж 6-м с кухней и сауной
    183367,   # Коттедж 8-м с кухней и сауной
    213511,   # Коттедж 8-м с кухней и сауной (семейный)
    296293,   # 6-местный коттедж с кухней и сауной dogfriendly
    # Неизвестные по имени, но не хостел (из rooms endpoint):
    123405, 183411, 183414, 183438, 208986, 208987,
}

# Хостел Даниэль — все типы "(Хостел Daniel)"
DANIELLE_TYPES = {
    84929,    # (Daniel) Стандарт с большой кроватью
    84928,    # (Daniel) Эконом с двумя кроватями
    84934,    # (Daniel) Эконом 4-местный
    84939,    # (Daniel) предположительно Койко-место в 8-местном — уточнить!
}

# Хостел Ален — все типы "(Хостел Alen)"
ALEN_TYPES = {
    82359, 82361, 82364, 82365, 82367,   # из зонда (место в номере)
    220392,   # 48 единиц — вероятно койко-места Ален
    220405,   # 4 единицы — вероятно Ален
}

# Количество единиц из rooms endpoint (для расчёта загрузки):
TOTAL_COTTAGES = 21   # 123405(1)+152774(2)+152776(2)+183367(1)+183368(2)+
                      # 183411(3)+183414(1)+183438(1)+198656(3)+208986(3)+208987(1)+213511(1)
TOTAL_DANIELLE = 15   # 84928(2)+84929(1)+84934(12) — без 84939, уточнить
TOTAL_ALEN     = 58   # 82xxx(6)+220392(48)+220405(4) — уточнить

# Монблан — трекинг-таблица (лист «ЕжеНедельно»)
MONBLAN_SHEET_ID = '1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI'
MONBLAN_GID      = 2051236241   # GID листа «ЕжеНедельно»

# Воронка — файл сегментов Евгении/Надежды
SEG_SHEET_ID   = '1CdeyCx0VlzqNpUSDhmIdJPZYuR_1nv33bHu5FLnHX_8'
SEG_SHEET_NAME = '2026 ✓'

# Маппинг: (строка в «2026 ✓», строка в «2026» финансового отчёта)
SEG_MAPPING = [
    (6,  51), (9,  52),           # Физики: броней, сумма
    (14, 40), (16, 41), (17, 42), # ДР: броней, проживаний, сумма
    (22, 44), (24, 45), (25, 46), # Группы: броней, проживаний, сумма
    (30, 48), (33, 49),           # Корп: броней, сумма
]


# ============================================================
# Загрузка ключей — из os.environ (GitHub Actions) или .env (локально)
# ============================================================
def _load_env_file(path=".env"):
    """Парсим .env вручную — python-dotenv не обрабатывает многострочный JSON."""
    if not os.path.exists(path):
        return
    content = open(path).read()
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("#"):
            i += 1
            continue
        if "=" not in line:
            i += 1
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if val.startswith("{"):
            json_lines = [val]
            depth = val.count("{") - val.count("}")
            i += 1
            while depth > 0 and i < len(lines):
                json_lines.append(lines[i])
                depth += lines[i].count("{") - lines[i].count("}")
                i += 1
            os.environ.setdefault(key, "\n".join(json_lines))
        else:
            os.environ.setdefault(key, val)
            i += 1

_load_env_file()

def _env(key):
    val = os.environ.get(key, '').strip()
    if not val:
        raise RuntimeError(f"Переменная окружения {key} не задана")
    return val

def _env_json(key):
    return json.loads(_env(key))

CLIENT_ID        = _env("TL_CLIENT_ID")
CLIENT_SECRET    = _env("TL_CLIENT_SECRET")
PROPERTY_ID      = _env("TL_PROPERTY_ID")
FINANCE_SHEET_ID = _env("FINANCE_SHEET_ID")
GOOGLE_CREDS     = _env_json("GOOGLE_CREDS_JSON")

AUTH_URL = "https://partner.tlintegration.com/auth/token"
RR_BASE  = "https://partner.tlintegration.com/api/read-reservation/v1"


# ============================================================
# Утилиты
# ============================================================
def col_letter(n: int) -> str:
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def get_token() -> str:
    resp = requests.post(
        AUTH_URL,
        data={"grant_type": "client_credentials",
              "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def forge_token(dt: date) -> str:
    ts_ms = int(datetime(dt.year, dt.month, dt.day).timestamp() * 1000)
    payload = {"BookingIds": [], "MillisecondsFrom": ts_ms}
    return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def get_week_dates(year: int, week: int):
    monday = date.fromisocalendar(year, week, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def overlap_nights(arr_str: str, dep_str: str, w_start: date, w_end: date) -> int:
    arr = date.fromisoformat(arr_str[:10])
    dep = date.fromisoformat(dep_str[:10])
    start = max(arr, w_start)
    end   = min(dep, w_end + timedelta(days=1))
    return max(0, (end - start).days)


# ============================================================
# Сбор бронирований
# ============================================================
def collect_booking_numbers(token: str, week_start: date, week_end: date):
    """
    Возвращает (active_numbers, cancelled_numbers) — номера броней с заездом в целевую неделю.
    Сканирует начиная с (week_start - 90 дней).
    """
    hdrs = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # Целевые префиксы: заезды в неделю + 21 день до (переходящие брони)
    # 21 день покрывает типичный максимальный срок проживания на курорте.
    prefixes = set()
    d = week_start - timedelta(days=21)
    while d <= week_end:
        prefixes.add(d.strftime("%Y%m%d"))
        d += timedelta(days=1)

    scan_from = week_start - timedelta(days=90)
    scan_end  = week_end   + timedelta(days=14)
    ct = forge_token(scan_from)

    active, cancelled = [], []
    page = 0

    print(f"Сканируем брони с {scan_from} по {scan_end}...")
    while page < 60:
        r = requests.get(
            RR_BASE + f"/properties/{PROPERTY_ID}/bookings",
            headers=hdrs,
            params={"pageSize": 100, "continueToken": ct},
            timeout=30,
        )
        if r.status_code != 200:
            print(f"  ❌ Ошибка {r.status_code}: {r.text[:200]}")
            break

        data = r.json()
        summaries = data.get("bookingSummaries", [])
        page += 1

        for s in summaries:
            num = s.get("number", "")
            if num[:8] in prefixes:
                (active if s["status"] == "Active" else cancelled).append(num)

        last_mod = summaries[-1]["modifiedDateTime"][:10] if summaries else "?"
        print(f"  Стр.{page}: {len(summaries)} броней, "
              f"найдено: активных={len(active)} отменённых={len(cancelled)}, "
              f"до даты={last_mod}")

        if last_mod.replace("-", "") > scan_end.strftime("%Y%m%d"):
            print("  Период пройден, стоп.")
            break

        ct = data.get("continueToken", "")
        if not ct or not data.get("hasMoreData", False):
            break

        time.sleep(0.5)

    return active, cancelled


def fetch_detail(token: str, number: str) -> dict:
    hdrs = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    r = requests.get(
        RR_BASE + f"/properties/{PROPERTY_ID}/bookings/{number}",
        headers=hdrs, timeout=30,
    )
    time.sleep(0.5)
    return r.json().get("booking", {}) if r.status_code == 200 else {}


# ============================================================
# Расчёт метрик
# ============================================================

def _svc_category(name: str, meal_code: str) -> str:
    """Категория сервиса по названию и mealPlanCode."""
    if meal_code == "BreakFast" or "завтрак" in name.lower():
        return "breakfast"
    n = name.lower()
    if any(k in n for k in ("фурако", "баня", "бани", "банный")):
        return "furako"
    if any(k in n for k in ("беседк", "мангал")):
        return "besedka"
    return "other"


def calculate(bookings: list, cancelled_count: int,
              week_start: date, week_end: date):
    """Возвращает (metrics_dict, room_type_stats_dict)."""
    rev_rooms    = 0.0   # выручка за номера (без сервисов)
    rev_furako   = 0.0   # Фурако/бани
    rev_besedka  = 0.0   # Беседки/мангалы
    rev_other    = 0.0   # Прочие сервисы
    guests          = 0
    returning       = 0
    cottage_nights  = 0
    cottage_los     = []   # реальные сроки заезда в коттеджах (дней)
    danielle_nights = 0
    alen_nights     = 0
    breakfast_count = 0
    direct_count    = 0
    cottage_departures = 0   # уборки коттеджей = кол-во выездов за неделю
    hostel_departures  = 0   # уборки хостелов = кол-во выездов за неделю
    total           = len(bookings)
    room_type_stats = {}

    for bk in bookings:
        # Повторный гость = есть карта лояльности
        loyalty = (bk.get("guaranteeInfo") or {}).get("loyalty") or {}
        if loyalty.get("cards"):
            returning += 1

        # Канал продаж: BookingEngine = онлайн-виджет, PMS = вручную администратором
        # Оба считаются прямыми продажами (не OTA)
        src_type = ((bk.get("source") or {}).get("type") or "")
        if src_type in ("BookingEngine", "PMS"):
            direct_count += 1

        # Сервисы брони: цены в svc["total"]["priceAfterTax"]
        # Сервисы дублируются на уровне брони и roomStay → берём только с уровня roomStay.
        # Завтраки не вычитаем из стоимости номера — они часть НФ-выручки (строка 5).
        # Фурако/беседки/прочее — отдельные строки (17, 18, 19).
        bk_breakfast = 0
        bk_furako    = 0.0
        bk_besedka   = 0.0
        bk_other_svc = 0.0

        for rs in bk.get("roomStays", []):
            arr = rs["stayDates"]["arrivalDateTime"]
            dep = rs["stayDates"]["departureDateTime"]
            ov  = overlap_nights(arr, dep, week_start, week_end)

            # Парсим rt_id один раз — используется и для уборок, и для категорий ночей
            rt_id_str = rs["roomType"]["id"]
            rt_id     = int(rt_id_str) if rt_id_str.isdigit() else rt_id_str
            rt_name   = rs["roomType"]["name"]

            # Считаем уборки ДО фильтра по ov: любой выезд в неделю = уборка.
            # Проверяем до ov==0, чтобы не пропустить гостей с заездом в прошлой неделе.
            dep_date = date.fromisoformat(dep[:10])
            if week_start <= dep_date <= week_end:
                if rt_id in COTTAGE_TYPES:
                    cottage_departures += 1
                elif rt_id in DANIELLE_TYPES or rt_id in ALEN_TYPES:
                    hostel_departures += 1

            if ov == 0:
                continue

            total_nights = max(1, (
                date.fromisoformat(dep[:10]) - date.fromisoformat(arr[:10])
            ).days)
            ratio = ov / total_nights

            # Выделяем только нехлебные платные сервисы из цены номера (строки 17-19)
            rs_svc_to_extract = 0.0
            for svc in rs.get("services", []):
                svc_price = (svc.get("total") or {}).get("priceAfterTax", 0.0)
                cat = _svc_category(svc.get("name", ""), svc.get("mealPlanCode", ""))
                if cat == "breakfast":
                    bk_breakfast += 1
                    # Завтрак остаётся в цене номера (НФ-выручка)
                elif cat == "furako":
                    rs_svc_to_extract += svc_price
                    bk_furako   += svc_price * ratio
                elif cat == "besedka":
                    rs_svc_to_extract += svc_price
                    bk_besedka  += svc_price * ratio
                else:
                    rs_svc_to_extract += svc_price
                    bk_other_svc += svc_price * ratio

            # Выручка за номер = цена roomStay минус извлечённые сервисы, пропорционально
            rs_room_price = rs["total"]["priceAfterTax"] - rs_svc_to_extract
            rs_room_week  = rs_room_price * ratio

            rev_rooms += rs_room_week
            guests    += rs["guestCount"]["adultCount"] + len(rs["guestCount"]["childAges"])

            # Статистика по типам номеров (для диагностики)
            if rt_id not in room_type_stats:
                room_type_stats[rt_id] = {"name": rt_name, "stays": 0, "nights": 0, "revenue": 0}
            room_type_stats[rt_id]["stays"]   += 1
            room_type_stats[rt_id]["nights"]  += ov
            room_type_stats[rt_id]["revenue"] += rs_room_week

            # Ночи по категориям
            if rt_id in COTTAGE_TYPES:
                cottage_nights += ov
                cottage_los.append(total_nights)   # реальный срок заезда
            elif rt_id in DANIELLE_TYPES:
                danielle_nights += ov
            elif rt_id in ALEN_TYPES:
                alen_nights += ov

        # Сервисные выручки накапливаем от брони
        rev_furako  += bk_furako
        rev_besedka += bk_besedka
        rev_other   += bk_other_svc
        breakfast_count += bk_breakfast

    W = 7  # дней в неделе
    metrics = {}

    # Выручка
    metrics[5]  = round(rev_rooms)
    metrics[17] = round(rev_furako)    # Фурако/бани (0 если нет)
    metrics[18] = round(rev_besedka)   # Беседки/мангалы
    metrics[19] = round(rev_other)     # Прочие сервисы

    # Гости и качество
    metrics[14] = breakfast_count
    metrics[21] = guests

    if total > 0:
        metrics[22] = round(returning / total, 4)    # % повторных
        metrics[33] = round(direct_count / total, 4) # % прямых

    total_with_cancel = total + cancelled_count
    if total_with_cancel > 0:
        metrics[32] = round(cancelled_count / total_with_cancel, 4)

    # ADR = выручка коттеджей (без сервисов) / ночи коттеджей
    cottage_rev = sum(
        v["revenue"] for rt_id, v in room_type_stats.items()
        if rt_id in COTTAGE_TYPES
    )
    if cottage_nights > 0:
        metrics[23] = round(cottage_rev / cottage_nights)
        metrics[27] = round(sum(cottage_los) / len(cottage_los), 1)  # реальный срок заезда

    # Загрузка — всегда пишем (даже 0)
    metrics[28] = round(cottage_nights  / (TOTAL_COTTAGES * W), 4)
    metrics[29] = round(danielle_nights / (TOTAL_DANIELLE * W), 4)
    metrics[30] = round(alen_nights     / (TOTAL_ALEN     * W), 4)

    # Уборки = количество выездов за неделю по категориям
    metrics[72] = cottage_departures
    metrics[74] = hostel_departures

    return metrics, room_type_stats


# ============================================================
# Google Sheets клиент (общий для чтения и записи)
# ============================================================
def _gs_client() -> gspread.Client:
    creds = Credentials.from_service_account_info(
        GOOGLE_CREDS, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.Client(auth=creds)


def _clean_num(v) -> str:
    """Убирает неразрывные пробелы и пробели-разделители из числовых значений ячеек."""
    return str(v).replace('\xa0', '').replace(' ', '').replace(',', '.').strip()


def read_monblan(client: gspread.Client, week_num: int, year: int):
    """
    Читает выручку (строка 4) и кол-во чеков (строка 42) из трекинг-листа Монблан.
    Возвращает (revenue: float, checks: int). При ошибке — (0, 0).
    """
    try:
        mb_ss = client.open_by_key(MONBLAN_SHEET_ID)
        mb_sh = next((s for s in mb_ss.worksheets() if s.id == MONBLAN_GID), None)
        if not mb_sh:
            print(f"  ⚠️ Монблан: лист GID={MONBLAN_GID} не найден")
            return 0, 0

        year_row = mb_sh.row_values(1)
        week_row = mb_sh.row_values(2)

        # Год в ячейке может быть «2 026» — убираем нецифры перед сравнением
        mb_col = None
        for i, (yr_v, wk_v) in enumerate(zip(year_row[1:], week_row[1:]), start=2):
            yr = int(re.sub(r'\D', '', str(yr_v))) if re.sub(r'\D', '', str(yr_v)) else 0
            wk = int(str(wk_v).strip()) if str(wk_v).strip().isdigit() else 0
            if wk == week_num and yr == year:
                mb_col = i
                break

        # Fallback: если ISO-неделя не найдена — берём последнюю заполненную колонку
        if mb_col is None:
            print(f"  ⚠️ Монблан: неделя {week_num}/{year} не найдена, берём последнюю")
            for i in range(len(week_row) - 1, 0, -1):
                if str(week_row[i]).strip():
                    mb_col = i + 1
                    print(f"  ℹ️ Монблан: используем колонку {mb_col} (нед.{week_row[i]})")
                    break

        if mb_col is None:
            print("  ⚠️ Монблан: данные не найдены")
            return 0, 0

        revenue = float(_clean_num(mb_sh.cell(4,  mb_col).value) or 0)
        checks  = int(float(_clean_num(mb_sh.cell(42, mb_col).value) or 0))
        return revenue, checks

    except Exception as e:
        print(f"  ❌ Монблан ошибка: {e}")
        return 0, 0


def read_segments(client: gspread.Client, week_num: int) -> dict:
    """
    Читает данные сегментов из листа «2026 ✓» файла Евгении/Надежды.
    Возвращает {fin_row: value} согласно SEG_MAPPING. При ошибке — {}.
    """
    try:
        seg_ss = client.open_by_key(SEG_SHEET_ID)
        seg_sh = seg_ss.worksheet(SEG_SHEET_NAME)

        # Строка 1 листа воронки: номера недель начиная с колонки C (1-based = 3)
        row1 = seg_sh.row_values(1)
        seg_col = None
        for i, v in enumerate(row1[2:], start=3):
            if str(v).strip() == str(week_num):
                seg_col = i
                break

        if seg_col is None:
            print(f"  ⚠️ Воронка: неделя {week_num} не найдена в строке 1")
            return {}

        result = {}
        for seg_row, fin_row in SEG_MAPPING:
            v = seg_sh.cell(seg_row, seg_col).value
            c = _clean_num(v) if v not in (None, '') else ''
            result[fin_row] = float(c) if c else 0
        return result

    except Exception as e:
        print(f"  ❌ Воронка ошибка: {e}")
        return {}


# ============================================================
# Запись в Google Sheets
# ============================================================
METRIC_LABELS = {
    5:  "Доход общий НФ+Монблан, руб",
    11: "Выручка Монблан, руб",
    12: "Чеков Монблан",
    14: "Завтраков (кол-во)",
    17: "Фурако/бани, руб",
    18: "Беседки/мангалы, руб",
    19: "Прочие услуги, руб",
    21: "Гостей всего",
    22: "% повторных гостей",
    23: "ADR (коттеджи), руб",
    27: "Ср. пребывание, дней",
    28: "Загрузка Коттеджей %",
    29: "Загрузка Даниэль %",
    30: "Загрузка Ален %",
    32: "Доля отмен %",
    33: "Прямые продажи %",
    40: "ДР: броней",
    41: "ДР: проживаний",
    42: "ДР: сумма, руб",
    44: "Группы: броней",
    45: "Группы: проживаний",
    46: "Группы: сумма, руб",
    48: "Корп: броней",
    49: "Корп: сумма, руб",
    51: "Физики: броней",
    52: "Физики: сумма, руб",
    72: "Уборки коттеджи",
    74: "Уборки хостелы",
}


def write_to_sheet(
    client: gspread.Client,
    metrics: dict,
    week_num: int,
    week_start: date,
    week_end: date,
    mb_revenue: float = 0,
    mb_checks: int = 0,
    seg_metrics: dict = None,
):
    ss = client.open_by_key(FINANCE_SHEET_ID)
    ws = ss.worksheet("2026")

    # Ищем или создаём колонку недели
    row1 = ws.row_values(1)
    col = None
    for i, v in enumerate(row1):
        if str(v).strip() == str(week_num):
            col = i + 1
            break

    if col is None:
        col = len(row1) + 1
        ws.update_cell(1, col, week_num)
        date_label = f"{week_start.strftime('%d.%m')}–{week_end.strftime('%d.%m')}"
        ws.update_cell(2, col, date_label)
        print(f"  Создана новая колонка {col_letter(col)} для недели {week_num}")
    else:
        print(f"  Используем колонку {col_letter(col)} для недели {week_num}")

    cl = col_letter(col)
    updates = []

    # TravelLine метрики (строка 5 = НФ без Монблан, переопределим ниже)
    for row, val in metrics.items():
        updates.append({"range": f"{cl}{row}", "values": [[val]]})

    # Строка 5: суммарный доход = НФ (TravelLine) + Монблан
    updates.append({"range": f"{cl}5", "values": [[metrics.get(5, 0) + mb_revenue]]})

    # Монблан
    updates.append({"range": f"{cl}11", "values": [[mb_revenue]]})
    updates.append({"range": f"{cl}12", "values": [[mb_checks]]})

    # Сегменты (Воронка)
    for fin_row, val in (seg_metrics or {}).items():
        updates.append({"range": f"{cl}{fin_row}", "values": [[val]]})

    ws.batch_update(updates, value_input_option="USER_ENTERED")

    # Формулы для расчётных строк
    formulas = [
        (9,  f"={cl}8/{cl}7"),    # % к факту прошлого года (нарастающим)
        (13, f"={cl}11/{cl}5"),   # F&B % от оборота
        (24, f"={cl}23*{cl}28"),  # RevPAR = ADR × Загрузка коттеджей
        (25, f"={cl}5/{cl}21"),   # RevPAC = Доход / Гостей
    ]
    for frow, formula in formulas:
        ws.update_acell(f"{cl}{frow}", formula)

    total_written = len(updates) + len(formulas)
    print(f"  ✅ Записано {len(updates)} значений + {len(formulas)} формулы → колонка {cl}")


# ============================================================
# MAIN
# ============================================================
def main():
    week_num, year = _resolve_week_year(WEEK_NUMBER, YEAR)
    week_start, week_end = get_week_dates(year, week_num)
    date_label = f"{week_start.strftime('%d.%m')}–{week_end.strftime('%d.%m')}"
    print(f"\n{'='*60}")
    print(f"TravelLine Collector — Неделя {week_num} {year} ({date_label})")
    print(f"Режим: {'DISCOVERY (только просмотр)' if DISCOVERY_MODE else 'ЗАПИСЬ В ТАБЛИЦУ'}")
    print(f"{'='*60}\n")

    # ── 1. TravelLine ────────────────────────────────────────────
    token = get_token()
    print("✅ TravelLine: токен получен\n")

    active_nums, cancelled_nums = collect_booking_numbers(token, week_start, week_end)
    print(f"\nИтого: {len(active_nums)} активных, {len(cancelled_nums)} отменённых броней\n")

    if not active_nums and not cancelled_nums:
        print("⚠️  Броней не найдено. Проверьте WEEK_NUMBER и YEAR.")
        return

    print(f"Загружаем детали {len(active_nums)} активных броней...")
    bookings = []
    for i, num in enumerate(active_nums, 1):
        bk = fetch_detail(token, num)
        if bk:
            bookings.append(bk)
        if i % 10 == 0 or i == len(active_nums):
            print(f"  {i}/{len(active_nums)} загружено")

    print(f"\nДеталей получено: {len(bookings)}\n")
    metrics, rt_stats = calculate(bookings, len(cancelled_nums), week_start, week_end)

    # ── 2. Монблан + Воронка (один GS-клиент на оба источника и запись) ──
    client = _gs_client()
    print("─── Монблан ───")
    mb_revenue, mb_checks = read_monblan(client, week_num, year)
    print(f"  Выручка (стр.11): {mb_revenue:,.0f} руб, Чеков (стр.12): {mb_checks}")

    print("─── Воронка (сегменты) ───")
    seg_metrics = read_segments(client, week_num)
    if seg_metrics:
        for fin_row, val in sorted(seg_metrics.items()):
            label = METRIC_LABELS.get(fin_row, f"Строка {fin_row}")
            print(f"  Стр.{fin_row:2d} ({label}): {val}")
    else:
        print("  (нет данных)")

    # ── Вывод TravelLine ─────────────────────────────────────────
    print("─── Типы номеров (TravelLine) ───")
    print(f"{'ID':>10} | {'Броней':>6} | {'Ночей':>6} | {'Выручка':>12} | Название")
    print("-" * 78)
    for rt_id, s in sorted(rt_stats.items(), key=lambda x: -x[1]["revenue"]):
        print(f"{rt_id:>10} | {s['stays']:>6} | {s['nights']:>6} | "
              f"{s['revenue']:>12,.0f} | {s['name']}")

    print(f"\n─── Метрики TravelLine — Неделя {week_num} ───")
    for row in sorted(metrics):
        val = metrics[row]
        label = METRIC_LABELS.get(row, f"Строка {row}")
        if row in {22, 28, 29, 30, 32, 33}:
            display = f"{val*100:.1f}%"
        elif row in {5, 23}:
            display = f"{val:,.0f} руб"
        else:
            display = str(val)
        print(f"  Строка {row:2d}: {label:<32} = {display}")

    if DISCOVERY_MODE:
        print("\n" + "="*60)
        print("DISCOVERY_MODE = True — данные НЕ записаны в таблицу.")
        return

    # ── 3. Запись ────────────────────────────────────────────────
    print("\n─── Запись в «2026» ───")
    write_to_sheet(client, metrics, week_num, week_start, week_end,
                   mb_revenue=mb_revenue, mb_checks=mb_checks, seg_metrics=seg_metrics)

    print(f"\n✅ Готово: неделя {week_num} ({date_label}) — TravelLine + Монблан + Воронка записаны.")


if __name__ == "__main__":
    main()
