#!/usr/bin/env python3
"""
Зонд: полная структура данных недели 17 (апр 20-26, 2026).
Цель: найти все поля для расчёта метрик — сервисы, источники, теги.
"""
import base64, json, re, time
from datetime import date, datetime, timedelta
import requests

with open(".env") as f:
    env = f.read()

CLIENT_ID     = re.search(r"TL_CLIENT_ID=(.+)",     env).group(1).strip()
CLIENT_SECRET = re.search(r"TL_CLIENT_SECRET=(.+)", env).group(1).strip()
PROPERTY_ID   = re.search(r"TL_PROPERTY_ID=(.+)",   env).group(1).strip()

AUTH_URL = "https://partner.tlintegration.com/auth/token"
RR_BASE  = "https://partner.tlintegration.com/api/read-reservation/v1"

WEEK_START = date(2026, 4, 20)
WEEK_END   = date(2026, 4, 26)


def get_token():
    r = requests.post(AUTH_URL,
        data={"grant_type": "client_credentials",
              "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def forge_token(dt):
    ts = int(datetime(dt.year, dt.month, dt.day).timestamp() * 1000)
    return base64.b64encode(json.dumps({"BookingIds": [], "MillisecondsFrom": ts},
                                        separators=(",", ":")).encode()).decode()


def collect_numbers(token):
    hdrs = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    prefixes = set()
    d = WEEK_START - timedelta(days=3)
    while d <= WEEK_END:
        prefixes.add(d.strftime("%Y%m%d"))
        d += timedelta(days=1)

    ct = forge_token(WEEK_START - timedelta(days=90))
    nums = []
    for _ in range(60):
        r = requests.get(RR_BASE + f"/properties/{PROPERTY_ID}/bookings",
                         headers=hdrs, params={"pageSize": 100, "continueToken": ct},
                         timeout=30)
        if r.status_code != 200:
            break
        data = r.json()
        for s in data.get("bookingSummaries", []):
            if s.get("number", "")[:8] in prefixes and s["status"] == "Active":
                nums.append(s["number"])
        last = data["bookingSummaries"][-1]["modifiedDateTime"][:10] if data.get("bookingSummaries") else "9"
        if last.replace("-", "") > (WEEK_END + timedelta(days=14)).strftime("%Y%m%d"):
            break
        ct = data.get("continueToken", "")
        if not ct or not data.get("hasMoreData", False):
            break
        time.sleep(0.3)
    return nums


def main():
    token = get_token()
    hdrs  = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    nums  = collect_numbers(token)
    print(f"Найдено активных броней: {len(nums)}\n")

    # ── Полный JSON первых 2 броней (структура) ──────────────────────────────
    print("=" * 70)
    print("ПОЛНАЯ СТРУКТУРА ПЕРВЫХ 2 БРОНЕЙ")
    print("=" * 70)
    for num in nums[:2]:
        r = requests.get(RR_BASE + f"/properties/{PROPERTY_ID}/bookings/{num}",
                         headers=hdrs, timeout=30)
        if r.status_code == 200:
            bk = r.json().get("booking", {})
            print(f"\n── Бронь {num} ──")
            print(json.dumps(bk, ensure_ascii=False, indent=2))
        time.sleep(0.5)

    # ── Агрегация по всем броням ─────────────────────────────────────────────
    all_sources  = {}   # ключ → кол-во
    all_services = {}   # id → {name, count, amount}
    all_tags     = {}   # tag → count
    segment_keys = set()

    print(f"\n\n{'='*70}")
    print(f"АГРЕГАЦИЯ ПО ВСЕМ {len(nums)} БРОНЯМ")
    print("=" * 70)

    for num in nums:
        r = requests.get(RR_BASE + f"/properties/{PROPERTY_ID}/bookings/{num}",
                         headers=hdrs, timeout=30)
        if r.status_code != 200:
            continue
        bk = r.json().get("booking", {})

        # источник
        src = bk.get("source") or {}
        k = f"{src.get('type','?')} | ch={src.get('channelId','?')} | {src.get('channelName','?')}"
        all_sources[k] = all_sources.get(k, 0) + 1

        # теги / метки / доп. поля
        for tag in (bk.get("tags") or []):
            all_tags[str(tag)] = all_tags.get(str(tag), 0) + 1
        for lbl in (bk.get("labels") or []):
            all_tags[f"label:{lbl}"] = all_tags.get(f"label:{lbl}", 0) + 1
        # Другие классификационные поля
        for field in ("groupId", "companyId", "corporateId", "purpose", "marketSegment",
                      "bookingPurpose", "category", "segmentCode"):
            v = bk.get(field)
            if v:
                key = f"{field}={v}"
                all_tags[key] = all_tags.get(key, 0) + 1

        # сервисы на уровне брони
        for svc in (bk.get("services") or []):
            _add_service(all_services, svc, prefix="[BK]")

        # сервисы на уровне проживания
        for rs in bk.get("roomStays", []):
            for svc in (rs.get("services") or []):
                _add_service(all_services, svc, prefix="")

        time.sleep(0.3)

    print("\n=== ИСТОЧНИКИ (source) ===")
    for k, c in sorted(all_sources.items(), key=lambda x: -x[1]):
        print(f"  {c:2d}x  {k}")

    print("\n=== СЕРВИСЫ (доп. услуги) ===")
    if all_services:
        print(f"  {'ID':>12} | {'Кол':>4} | {'Сумма':>12} | Название")
        for sid, s in sorted(all_services.items(), key=lambda x: -x[1]["count"]):
            print(f"  {str(sid):>12} | {s['count']:>4} | {s['amount']:>12,.0f} | {s['name']}")
    else:
        print("  Сервисов нет")

    print("\n=== ТЕГИ / ДОППОЛ. ПОЛЯ ===")
    if all_tags:
        for t, c in sorted(all_tags.items(), key=lambda x: -x[1]):
            print(f"  {c:2d}x  {t}")
    else:
        print("  Тегов нет")


def _add_service(store, svc, prefix=""):
    sid   = svc.get("id") or svc.get("serviceId") or "?"
    sname = svc.get("name") or svc.get("serviceName") or svc.get("title") or "?"
    amt   = svc.get("totalPrice") or svc.get("price") or svc.get("amount") or 0
    key   = f"{prefix}{sid}"
    if key not in store:
        store[key] = {"name": f"{prefix} {sname}".strip(), "count": 0, "amount": 0}
    store[key]["count"]  += 1
    store[key]["amount"] += amt


if __name__ == "__main__":
    main()
