#!/usr/bin/env python3
"""
fix_sheet_dates.py — одноразовая миграция листа «Ежедневно».

Проблема: write_daily_row использовал valueInputOption="USER_ENTERED",
поэтому Google Sheets преобразовывал строку «2026-03-30» в Excel serial
number, который отображается как «пн», «вт», «ср» и т.д.
В результате _find_or_create_date_column не находил существующие колонки
и создавал дубли правее.

Что делает этот скрипт:
  1. Читает строку 1 листа «Ежедневно» с сырыми (unformatted) значениями.
  2. Для каждого Excel serial number конвертирует обратно в ISO-строку
     и перезаписывает ячейку через valueInputOption="RAW".
  3. Очищает дублирующие колонки (AC и правее), которые появились при
     повторных попытках записи в период с неправильной логикой.

После запуска нужно перезапустить collect для 30.03–05.04 через
GitHub Actions → "Сбор данных Монблан" → Run workflow.
"""

import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from sheets_writer import get_service, _excel_serial_to_date, _col_letter

SHEETS_ID  = os.environ.get("GOOGLE_SHEETS_ID", "1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI")
CREDS_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
CREDS_PATH = os.path.join(os.path.dirname(__file__), "credentials.json")

# Колонка, начиная с которой считаем данные дублями (AC = 29)
DUPLICATE_FROM_COL = 29  # AC


def fix_date_row(service, spreadsheet_id: str):
    """
    Исправить строку 1: Excel serial numbers → ISO-строки (RAW).
    Возвращает список (колонка, дата) тех ячеек, которые были исправлены.
    """
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="Ежедневно!1:1",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    row = result.get("values", [[]])[0] if result.get("values") else []

    updates = []
    fixed = []
    for i, cell in enumerate(row):
        if isinstance(cell, (int, float)) and cell > 10000:
            try:
                iso = _excel_serial_to_date(int(cell))
                col_ltr = _col_letter(i + 1)
                print(f"  Колонка {col_ltr} ({i+1}): serial {cell} → {iso}")
                updates.append({"range": f"Ежедневно!{col_ltr}1", "values": [[iso]]})
                fixed.append((i + 1, iso))
            except Exception as e:
                print(f"  Колонка {_col_letter(i+1)}: не удалось конвертировать {cell}: {e}")

    if updates:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": updates},
        ).execute()
        print(f"\n✅ Исправлено {len(updates)} ячеек с датами")
    else:
        print("ℹ️  Excel serial numbers не найдены — даты уже в правильном формате")

    return fixed


def clear_duplicate_columns(service, spreadsheet_id: str, from_col: int):
    """
    Очистить всё содержимое начиная с колонки from_col (1-based) на листе «Ежедневно».
    Используется для удаления дублирующих колонок, возникших из-за ошибки поиска дат.
    """
    col_ltr = _col_letter(from_col)

    # Проверяем, есть ли там данные
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"Ежедневно!{col_ltr}1:{col_ltr}1",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    vals = result.get("values", [[]])[0] if result.get("values") else []

    if not vals:
        print(f"ℹ️  Колонка {col_ltr} пустая — дублей нет")
        return

    print(f"Очищаем дублирующие колонки начиная с {col_ltr} (первое значение: {vals[0]!r})...")
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"Ежедневно!{col_ltr}1:ZZ",
    ).execute()
    print(f"✅ Колонки {col_ltr}+ очищены")


def show_header(service, spreadsheet_id: str):
    """Вывести текущее состояние строки 1 для диагностики."""
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="Ежедневно!1:1",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    row = result.get("values", [[]])[0] if result.get("values") else []
    print("Строка 1 (форматированные значения):")
    for i, cell in enumerate(row):
        if cell and cell != "Показатель":
            print(f"  {_col_letter(i+1)}: {cell!r}")


if __name__ == "__main__":
    # Подключение к Google Sheets
    if CREDS_JSON:
        service = get_service(credentials_json=CREDS_JSON)
    elif os.path.exists(CREDS_PATH):
        service = get_service(credentials_path=CREDS_PATH)
    else:
        print("❌ Нет GOOGLE_SERVICE_ACCOUNT_JSON и нет credentials.json")
        sys.exit(1)

    if not SHEETS_ID:
        print("❌ Нет GOOGLE_SHEETS_ID")
        sys.exit(1)

    print("=== Текущее состояние строки 1 ===")
    show_header(service, SHEETS_ID)

    print("\n=== Шаг 1: исправление Excel serial → ISO строки ===")
    fixed = fix_date_row(service, SHEETS_ID)

    print("\n=== Шаг 2: очистка дублирующих колонок (AC и правее) ===")
    clear_duplicate_columns(service, SHEETS_ID, from_col=DUPLICATE_FROM_COL)

    print("\n=== Итоговое состояние строки 1 ===")
    show_header(service, SHEETS_ID)

    print("\n✅ Готово!")
    print("Теперь запустите collect для каждого дня 30.03–05.04 через GitHub Actions:")
    print("  Actions → 'Сбор данных Монблан (23:30)' → Run workflow → введите дату")
    for d in ["2026-03-30", "2026-03-31", "2026-04-01", "2026-04-02", "2026-04-03", "2026-04-04", "2026-04-05"]:
        print(f"  - {d}")
