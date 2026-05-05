#!/usr/bin/env python3
"""
Зондирующий скрипт — раунд 4 (финальный).
Цель: полная структура брони апреля 2026 + счётчик комнат + PMS analytics.
"""
import base64
import json
import re
import sys
import requests

with open(".env") as f:
    env = f.read()

CLIENT_ID     = re.search(r"TL_CLIENT_ID=(.+)",     env).group(1).strip()
CLIENT_SECRET = re.search(r"TL_CLIENT_SECRET=(.+)", env).group(1).strip()
PROPERTY_ID   = re.search(r"TL_PROPERTY_ID=(.+)",   env).group(1).strip()

AUTH_URL = "https://partner.tlintegration.com/auth/token"
PMS_BASE = "https://partner.tlintegration.com/api/pms/v2"
RR_BASE  = "https://partner.tlintegration.com/api/read-reservation/v1"


def get_token():
    resp = requests.post(
        AUTH_URL,
        data={"grant_type": "client_credentials",
              "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"❌ Авторизация: {resp.status_code}"); sys.exit(1)
    print("✅ Токен получен\n")
    return resp.json()["access_token"]


def forge_token(unix_ms: int) -> str:
    data = {"BookingIds": [], "MillisecondsFrom": unix_ms}
    return base64.b64encode(json.dumps(data, separators=(",", ":")).encode()).decode()


def main():
    token = get_token()
    hdrs = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # -----------------------------------------------------------------------
    # 1. Находим первую бронь с заездом в апреле 2026
    #    Прыгаем на 1 апреля 2026 UTC (1743465600000 мс)
    # -----------------------------------------------------------------------
    print("=== 1. ИЩЕМ БРОНЬ С ЗАЕЗДОМ В АПРЕЛЕ 2026 ===\n")

    ts_apr2026 = 1743465600000  # 2026-04-01 00:00 UTC
    ct = forge_token(ts_apr2026)

    booking_number = None
    page = 0
    while booking_number is None and page < 20:
        r = requests.get(
            RR_BASE + f"/properties/{PROPERTY_ID}/bookings",
            headers=hdrs,
            params={"pageSize": 100, "continueToken": ct},
            timeout=30,
        )
        if r.status_code != 200:
            print(f"❌ Ошибка списка: {r.status_code} {r.text[:200]}")
            break
        data = r.json()
        summaries = data.get("bookingSummaries", [])
        page += 1

        for s in summaries:
            num = s.get("number", "")
            # Заезд в апреле 2026: номер начинается с 202604
            if num.startswith("202604"):
                booking_number = num
                print(f"Нашли бронь апреля 2026: {num}")
                print(f"  status: {s['status']}")
                print(f"  created: {s['createdDateTime']}")
                print(f"  modified: {s['modifiedDateTime']}")
                break

        if not booking_number:
            ct = data.get("continueToken", "")
            if not ct or not data.get("hasMoreData", False):
                print("Броней апреля 2026 не найдено")
                break
            print(f"  Страница {page}: просмотрено {len(summaries)} броней, продолжаем...")

    # -----------------------------------------------------------------------
    # 2. Полные детали найденной брони
    # -----------------------------------------------------------------------
    if booking_number:
        print(f"\n=== 2. ПОЛНЫЕ ДЕТАЛИ БРОНИ {booking_number} ===\n")
        r = requests.get(
            RR_BASE + f"/properties/{PROPERTY_ID}/bookings/{booking_number}",
            headers=hdrs, timeout=30,
        )
        print(f"→ {r.status_code}")
        if r.status_code == 200:
            # Выводим полностью без обрезки
            print(json.dumps(r.json(), ensure_ascii=False, indent=2))
        else:
            print(r.text[:500])

    # -----------------------------------------------------------------------
    # 3. Список номеров (для расчёта общей ёмкости)
    # -----------------------------------------------------------------------
    print("\n=== 3. СПИСОК НОМЕРОВ И ТИПОВ ===\n")
    r = requests.get(PMS_BASE + f"/properties/{PROPERTY_ID}/rooms",
                     headers=hdrs, timeout=30)
    print(f"→ {r.status_code}")
    if r.status_code == 200:
        rooms = r.json().get("rooms", [])
        print(f"Всего номеров: {len(rooms)}")
        # Считаем по типам
        by_type = {}
        for rm in rooms:
            rt = rm.get("roomTypeId", "?")
            by_type[rt] = by_type.get(rt, 0) + 1
        print("По типам (roomTypeId: количество):")
        for rt, cnt in sorted(by_type.items()):
            print(f"  {rt}: {cnt}")

    # -----------------------------------------------------------------------
    # 4. PMS Analytics — последняя попытка с правильным токеном
    # -----------------------------------------------------------------------
    print("\n=== 4. PMS ANALYTICS — финал ===\n")
    params = {"dateFrom": "2026-04-20", "dateTo": "2026-04-26"}

    for url in [
        f"{PMS_BASE}/properties/{PROPERTY_ID}/analytics/daily-occupancy-statistics",
        f"https://partner.tlintegration.com/api/pms/v1/properties/{PROPERTY_ID}/analytics/daily-occupancy-statistics",
        f"https://partner.tlintegration.com/api/pms-analytics/v1/properties/{PROPERTY_ID}/analytics/daily-occupancy-statistics",
    ]:
        r = requests.get(url, headers=hdrs, params=params, timeout=15)
        short = url.replace("https://partner.tlintegration.com/api/", "")
        print(f"  {r.status_code} → {short}")
        if r.status_code == 200:
            print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:3000])
        elif r.status_code not in (404, 405):
            print(f"  Ответ: {r.text[:200]}")

    print("\n=== ГОТОВО ===")


if __name__ == "__main__":
    main()
