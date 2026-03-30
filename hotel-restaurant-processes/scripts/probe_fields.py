"""
probe_fields.py — финальный поиск endpoint списаний и полей TRANSACTIONS.
"""
import hashlib, os, requests
BASE_URL = "https://593-760-434.iiko.it/resto/api"
LOGIN    = os.environ.get("IIKO_LOGIN", "")
PASSWORD = os.environ.get("IIKO_PASSWORD", "")

def sha1(t): return hashlib.sha1(t.encode()).hexdigest()
def get_token():
    r = requests.get(f"{BASE_URL}/auth", params={"login": LOGIN, "pass": sha1(PASSWORD)}, timeout=15)
    return r.text.strip()
def get(token, path):
    r = requests.get(f"{BASE_URL}{path}", params={"key": token}, timeout=15)
    return r.status_code, r.text[:250]
def olap(token, report_type, group_by, agg_fields):
    payload = {
        "reportType": report_type, "buildSummary": True,
        "groupByRowFields": group_by, "aggregateFields": agg_fields,
        "filters": {"OpenDate.Typed": {"filterType": "DateRange", "periodType": "CUSTOM",
            "from": "2020-01-01", "to": "2026-03-30", "includeLow": "true", "includeHigh": "true"}}
    }
    r = requests.post(f"{BASE_URL}/v2/reports/olap", params={"key": token}, json=payload, timeout=20)
    return r.status_code, r.text[:200]

token = get_token()
print(f"Токен: {token[:20]}...\n")

print("=== 1. Endpoint списаний — ещё варианты ===")
for path in [
    "/v2/documents/export/WRITE_OFF",
    "/v2/documents/writeOff",
    "/v2/documents/writeoff",
    "/store/writeOff/list",
    "/v2/store/document/export/WRITE_OFF",
    "/v2/documents",
    "/v2/documents/list",
    "/v2/store",
]:
    code, text = get(token, path)
    mark = "✅" if code == 200 else "❌"
    print(f"  {mark} {path}: {code} | {text[:100]}")

print("\n=== 2. TRANSACTIONS — ищем правильное поле суммы ===")
for f in ["ProductSumInt", "Sum", "SumInt", "Amount", "AmountInt",
          "TransactionSum", "Price", "PriceInt", "Cost", "CostInt"]:
    code, text = olap(token, "TRANSACTIONS", [], [f])
    mark = "✅" if code == 200 else "❌"
    print(f"  {mark} TRANSACTIONS/{f}: {text[:80]}")

print("\n=== 3. OrderNum как groupBy — для градации чеков ===")
code, text = olap(token, "SALES", ["OrderNum"], ["DishSumInt"])
print(f"  OrderNum groupBy: {code} | {text[:150]}")
