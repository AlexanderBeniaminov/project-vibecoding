"""
Проверяем строки 88-130 '2026 старый' + все данные для недель 21-22
"""
import json
import gspread
from google.oauth2.service_account import Credentials

CREDS_FILE = '/Users/user/Downloads/aihotel-gubaha-f2f4b68bb17e.json'
SHEET_ID = '1Ohm7tst750zDzSeIewJFj_cPC6vl0-5J0UiuNfZvY_k'

def get_client():
    creds = Credentials.from_service_account_file(
        CREDS_FILE,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return gspread.Client(auth=creds)

def get_week_val(row, week_num):
    """Из строки '2026 старый' берём значение за нужную неделю (каждые 2 колонки начиная с D)"""
    col_idx = 3 + (week_num - 1) * 2  # col D=3, F=5, H=7, ...
    if col_idx < len(row):
        return row[col_idx].strip().replace('\xa0', '').replace(' ', '')
    return ''

def main():
    client = get_client()
    spreadsheet = client.open_by_key(SHEET_ID)
    old_ws = spreadsheet.worksheet('2026 старый')
    old_data = old_ws.get_all_values()

    print(f"Всего строк в '2026 старый': {len(old_data)}")
    print()

    # Строки 88-130 — ремонт, уборки, звонки, ФОТ
    print("=== '2026 старый' строки 88-130 — все данные ===")
    for row_idx in range(87, min(130, len(old_data))):
        row = old_data[row_idx]
        label = row[2] if len(row) > 2 else ''
        data = {}
        for w in range(1, 25):
            val = get_week_val(row, w)
            if val:
                data[w] = val
        if label or data:
            print(f"  Row{row_idx+1}: '{label}' | {data}")

    print()
    print("=== Данные за неделю 21 по всем строкам '2026 старый' ===")
    for row_idx, row in enumerate(old_data):
        val21 = get_week_val(row, 21)
        val22 = get_week_val(row, 22)
        label = row[2] if len(row) > 2 else ''
        if val21 or val22:
            print(f"  Row{row_idx+1}: '{label}' | W21={val21} | W22={val22}")

if __name__ == '__main__':
    main()
