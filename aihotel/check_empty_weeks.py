"""
Проверяем что именно пустое в листе '2026' начиная со строки 40
и смотрим полные данные из '2026 старый'
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

def main():
    client = get_client()
    spreadsheet = client.open_by_key(SHEET_ID)

    target_ws = spreadsheet.worksheet('2026')
    old_ws = spreadsheet.worksheet('2026 старый')

    target_data = target_ws.get_all_values()
    old_data = old_ws.get_all_values()

    # Строка 1 (индекс 0) — заголовки недель в целевом листе
    header_row = target_data[0]
    print("=== Строка 1 целевого листа (заголовки) ===")
    print(header_row)
    print()

    # Строки 2 (даты)
    dates_row = target_data[1]
    print("=== Строка 2 (даты) ===")
    print(dates_row[:25])
    print()

    # Смотрим строки 40-82 в целевом листе — все колонки
    print("=== Строки 40-82 в '2026' — все 25 колонок данных ===")
    for row_idx in range(39, 82):  # 0-based
        if row_idx >= len(target_data):
            break
        row = target_data[row_idx]
        label = row[1] if len(row) > 1 else ''
        # Данные с col C (индекс 2) по col Z (индекс 27)
        data = row[2:27] if len(row) > 2 else []
        # Считаем сколько непустых ячеек
        non_empty = [v for v in data if v.strip()]
        if label or non_empty:
            # Показываем все значения
            data_str = ' | '.join(f'W{i+1}:{v}' for i, v in enumerate(data) if v.strip())
            empty_weeks = [i+1 for i, v in enumerate(data) if not v.strip()]
            print(f"  Row{row_idx+1}: '{label}' | Заполнено: {len(non_empty)} нед | Пустые: {empty_weeks[:10]} | {data_str[:100]}")

    print()
    print("=== Данные из '2026 старый' — понимаем структуру ===")
    # Строка 3 в старом листе — даты (индекс 2)
    old_row3 = old_data[2] if len(old_data) > 2 else []
    print(f"Строка 3 (даты): {old_row3[:30]}")
    print()

    # Ищем строки с данными по сегментам в '2026 старый'
    # По нашим данным из предыдущего скрипта:
    # Строка 67 — Броней ДР
    # Строка 68 — На сумму ДР (броней)
    # Строка 69 — Проживаний ДР
    # Строка 70 — Сумма по ДР
    # Строка 72 — Броней корпоратив
    # Строка 73 — Сумма корпоратив
    # Строка 74 — Проживаний корпоратив
    # Строка 75 — Сумма корпоратив
    # Строка 77 — Броней групп
    # Строка 78 — Сумма групп
    # Строка 79 — Проживаний групп
    # Строка 80 — Сумма групп
    # Строка 82 — Броней физиков
    # Строка 83 — Сумма физиков (броней)
    # Строка 84 — Проживаний физиков
    # Строка 85 — Сумма физиков

    interesting_rows_old = [65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86]
    print("=== '2026 старый' — строки 66-86 (сегменты) — все колонки ===")
    for row_idx in interesting_rows_old:
        if row_idx >= len(old_data):
            break
        row = old_data[row_idx]
        label = row[2] if len(row) > 2 else ''  # col C — заголовок
        # Данные идут каждые 2 колонки начиная с col D (индекс 3)
        # Неделя 1: индекс 3, Неделя 2: индекс 5, ...
        data = {}
        for w in range(1, 26):
            col_idx = 3 + (w - 1) * 2  # D, F, H, ...
            if col_idx < len(row):
                val = row[col_idx].strip().replace('\xa0', '').replace(' ', '')
                if val:
                    data[w] = val
        if label or data:
            print(f"  Row{row_idx+1}: '{label}' | {data}")

if __name__ == '__main__':
    main()
