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


# ============================================================
# Загрузка ключей из .env
# ============================================================
with open(".env") as f:
    env = f.read()

def _env(key):
    return re.search(rf"{key}=(.+)", env).group(1).strip()

def _env_json(key):
    m = re.search(rf"{key}=(.*?)(?=\n[A-Z_]+=|\Z)", env, re.DOTALL)
    return json.loads(m.group(1).strip())

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

    # Целевые префиксы: заезды в неделю + 3 дня до (stay-over гости)
    prefixes = set()
    d = week_start - timedelta(days=3)
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
            if ov == 0:
                continue

            total_nights = max(1, (
                date.fromisoformat(dep[:10]) - date.fromisoformat(arr[:10])
            ).days)
            ratio = ov / total_nights

            rt_id_str = rs["roomType"]["id"]
            rt_id     = int(rt_id_str) if rt_id_str.isdigit() else rt_id_str
            rt_name   = rs["roomType"]["name"]

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

    return metrics, room_type_stats


# ============================================================
# Запись в Google Sheets
# ============================================================
METRIC_LABELS = {
    5:  "Доход НФ (без Монблан), руб",
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
}


def write_to_sheet(metrics: dict, week_num: int, week_start: date, week_end: date):
    creds = Credentials.from_service_account_info(
        GOOGLE_CREDS, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.Client(auth=creds)
    ss = client.open_by_key(FINANCE_SHEET_ID)

    # Показываем все листы для диагностики
    all_titles = [w.title for w in ss.worksheets()]
    print(f"Листы в таблице: {all_titles}")

    SHEET_NAME = "2026"
    if SHEET_NAME not in all_titles:
        print(f"❌ Лист '{SHEET_NAME}' не найден. Доступные листы: {all_titles}")
        return
    ws = ss.worksheet(SHEET_NAME)

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
        date_label = f"{week_start.strftime('%d.%m')}–{week_end.strftime('%d.%m.%Y')}"
        ws.update_cell(2, col, date_label)
        print(f"Создана новая колонка {col_letter(col)} для недели {week_num}")
    else:
        print(f"Найдена колонка {col_letter(col)} для недели {week_num}")

    # Записываем метрики
    cl = col_letter(col)
    updates = [{"range": f"{cl}{row}", "values": [[val]]}
               for row, val in metrics.items()]
    ws.batch_update(updates, value_input_option="USER_ENTERED")
    print(f"✅ Записано {len(updates)} значений в колонку {cl}")


# ============================================================
# MAIN
# ============================================================
def main():
    week_num, year = _resolve_week_year(WEEK_NUMBER, YEAR)
    week_start, week_end = get_week_dates(year, week_num)
    print(f"\n{'='*60}")
    print(f"TravelLine Collector — Неделя {week_num} {year}")
    print(f"Период: {week_start} – {week_end}")
    print(f"Режим: {'DISCOVERY (только просмотр)' if DISCOVERY_MODE else 'ЗАПИСЬ В ТАБЛИЦУ'}")
    print(f"{'='*60}\n")

    token = get_token()
    print("✅ TravelLine: токен получен\n")

    # Шаг 1: собираем номера броней
    active_nums, cancelled_nums = collect_booking_numbers(token, week_start, week_end)
    print(f"\nИтого: {len(active_nums)} активных, {len(cancelled_nums)} отменённых броней\n")

    if not active_nums and not cancelled_nums:
        print("⚠️  Броней не найдено. Проверьте WEEK_NUMBER и YEAR.")
        return


    # Шаг 2: загружаем детали активных броней
    print(f"Загружаем детали {len(active_nums)} активных броней...")
    bookings = []
    for i, num in enumerate(active_nums, 1):
        bk = fetch_detail(token, num)
        if bk:
            bookings.append(bk)
        if i % 5 == 0 or i == len(active_nums):
            print(f"  {i}/{len(active_nums)} загружено")

    print(f"\nДеталей получено: {len(bookings)}\n")

    # Шаг 3: считаем метрики
    metrics, rt_stats = calculate(bookings, len(cancelled_nums), week_start, week_end)

    # Вывод типов номеров (для настройки)
    print("=== ТИПЫ НОМЕРОВ ===")
    print(f"{'ID':>10} | {'Броней':>6} | {'Ночей':>6} | {'Выручка':>12} | Название")
    print("-" * 80)
    for rt_id, s in sorted(rt_stats.items(), key=lambda x: -x[1]["revenue"]):
        print(f"{rt_id:>10} | {s['stays']:>6} | {s['nights']:>6} | "
              f"{s['revenue']:>12,.0f} | {s['name']}")

    # Вывод метрик
    print(f"\n=== МЕТРИКИ — Неделя {week_num} ===")
    for row in sorted(metrics):
        val = metrics[row]
        label = METRIC_LABELS.get(row, f"Строка {row}")
        # Форматирование для читаемости
        if row in {22, 28, 29, 30, 32, 33}:
            display = f"{val*100:.1f}%"
        elif row in {5, 23}:
            display = f"{val:,.0f} руб"
        else:
            display = str(val)
        print(f"  Строка {row:2d}: {label:<28} = {display}")

    if DISCOVERY_MODE:
        print("\n" + "="*60)
        print("DISCOVERY_MODE = True — данные НЕ записаны в таблицу.")
        print("\nЧто делать дальше:")
        print("1. Посмотрите вывод 'ТИПЫ НОМЕРОВ' выше")
        print("2. Определите какие ID относятся к Коттеджам, Даниэль, Ален")
        print("3. Заполните COTTAGE_TYPES, DANIELLE_TYPES, ALEN_TYPES и TOTAL_*")
        print("4. Поменяйте DISCOVERY_MODE = False")
        print("5. Запустите снова — данные запишутся в таблицу")
        return

    write_to_sheet(metrics, week_num, week_start, week_end)


if __name__ == "__main__":
    main()
