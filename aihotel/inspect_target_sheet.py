"""
Скрипт для инспекции целевого листа и листа '2026 старый'
Читает структуру и данные для заполнения строк 40+
"""
import json
import gspread
from google.oauth2.service_account import Credentials

CREDS_FILE = '/Users/user/Downloads/aihotel-gubaha-f2f4b68bb17e.json'
SHEET_ID = '1Ohm7tst750zDzSeIewJFj_cPC6vl0-5J0UiuNfZvY_k'
TARGET_GID = '2018226789'

def get_client():
    creds = Credentials.from_service_account_file(
        CREDS_FILE,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return gspread.Client(auth=creds)

def main():
    client = get_client()
    spreadsheet = client.open_by_key(SHEET_ID)

    # Список всех листов
    print("=== ЛИСТЫ ТАБЛИЦЫ ===")
    for ws in spreadsheet.worksheets():
        print(f"  id={ws.id}, title='{ws.title}'")

    print()

    # Найти целевой лист по gid
    target_ws = None
    old_ws = None
    for ws in spreadsheet.worksheets():
        if str(ws.id) == TARGET_GID:
            target_ws = ws
        if '2026 старый' in ws.title:
            old_ws = ws

    if target_ws:
        print(f"=== ЦЕЛЕВОЙ ЛИСТ: '{target_ws.title}' ===")
        # Читаем все данные
        all_values = target_ws.get_all_values()
        print(f"Всего строк: {len(all_values)}")
        print()
        print("Строки 1-50 (или все если меньше):")
        for i, row in enumerate(all_values[:50], 1):
            # Убираем пустые хвосты строки
            trimmed = row
            while trimmed and trimmed[-1] == '':
                trimmed = trimmed[:-1]
            if trimmed:  # Показываем только непустые строки
                print(f"  {i:3}: {trimmed}")

    print()

    if old_ws:
        print(f"=== ЛИСТ '2026 старый': '{old_ws.title}' ===")
        all_old = old_ws.get_all_values()
        print(f"Всего строк: {len(all_old)}")
        print()
        print("Строки 1-10 (заголовки и структура):")
        for i, row in enumerate(all_old[:10], 1):
            trimmed = row
            while trimmed and trimmed[-1] == '':
                trimmed = trimmed[:-1]
            print(f"  {i:3}: {trimmed}")

        print()
        print("Строки 11-60 (данные):")
        for i, row in enumerate(all_old[10:60], 11):
            trimmed = row
            while trimmed and trimmed[-1] == '':
                trimmed = trimmed[:-1]
            if trimmed:
                print(f"  {i:3}: {trimmed}")
    else:
        print("ЛИСТ '2026 старый' НЕ НАЙДЕН!")

if __name__ == '__main__':
    main()
