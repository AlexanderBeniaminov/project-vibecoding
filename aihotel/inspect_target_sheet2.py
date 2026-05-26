"""
Инспекция структуры листов — только нужные данные
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

def trim_row(row):
    while row and row[-1] == '':
        row = row[:-1]
    return row

def main():
    client = get_client()
    spreadsheet = client.open_by_key(SHEET_ID)

    target_ws = spreadsheet.worksheet('2026')
    old_ws = spreadsheet.worksheet('2026 старый')

    # === ЦЕЛЕВОЙ ЛИСТ '2026' — структура (колонки A и B) ===
    print("=== ЛИСТ '2026' — строки 1-82 (col A и B) ===")
    target_data = target_ws.get_all_values()
    for i, row in enumerate(target_data, 1):
        col_a = row[0] if len(row) > 0 else ''
        col_b = row[1] if len(row) > 1 else ''
        # Данные из уже заполненных колонок (несколько первых)
        data_cols = row[2:12] if len(row) > 2 else []
        data_cols_str = ' | '.join(data_cols)
        if col_a or col_b:
            print(f"  {i:3}: A='{col_a}' B='{col_b}' | Данные: {data_cols_str[:80]}")

    print()
    print("=== ЛИСТ '2026 старый' — первые 5 строк (заголовки) ===")
    old_data = old_ws.get_all_values()
    for i, row in enumerate(old_data[:5], 1):
        print(f"  {i:3}: {trim_row(row)[:15]}")

    print()
    print("=== ЛИСТ '2026 старый' — строки 6-100 (col A и B, плюс данные) ===")
    for i, row in enumerate(old_data[5:100], 6):
        col_a = row[0] if len(row) > 0 else ''
        col_b = row[1] if len(row) > 1 else ''
        data_cols = row[2:12] if len(row) > 2 else []
        data_str = ' | '.join(data_cols)
        if col_a or col_b or any(data_cols):
            print(f"  {i:3}: A='{col_a}' B='{col_b}' | {data_str[:80]}")

if __name__ == '__main__':
    main()
