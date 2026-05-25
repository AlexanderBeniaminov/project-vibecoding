"""
Применяет к листу «Еженедельно»:
  1. Числовые форматы для строк 4–96 (данные, колонки B+):
     — % строки (без десятых): 0%
     — все остальные: # ##0  (пробел как разделитель тысяч, без десятых)
  2. Даты в строке 3: "DD-DD" диапазон пн–вс для каждой ISO-недели из строк 1-2
"""

from datetime import date, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = '1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI'
SHEET_GID      = 2051236241
CREDS_FILE     = 'credentials.json'

# Строки, которые должны быть в формате % (без десятых)
PCT_ROWS = {6, 8, 11, 13, 15, 18, 20, 22, 24, 26, 28, 30,
            33, 35, 37, 62, 64, 66, 69, 71, 73, 76, 78, 80, 82, 84, 86}

FIRST_DATA_ROW = 4   # строка 4 — первая строка данных
LAST_DATA_ROW  = 96  # строка 96 — последняя


def get_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDS_FILE,
        scopes=['https://www.googleapis.com/auth/spreadsheets'],
    )
    return build('sheets', 'v4', credentials=creds)


def get_sheet_name(service):
    ss = service.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        fields='sheets.properties',
    ).execute()
    for sheet in ss.get('sheets', []):
        if sheet['properties']['sheetId'] == SHEET_GID:
            return sheet['properties']['title']
    raise ValueError(f'Лист GID={SHEET_GID} не найден')


def iso_week_date_range(year, iso_week):
    """Возвращает строку 'DD-DD' (пн-вс) для заданной ISO-недели."""
    jan4        = date(int(year), 1, 4)
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    monday      = week1_monday + timedelta(weeks=int(iso_week) - 1)
    sunday      = monday + timedelta(days=6)
    return f'{monday.day:02d}-{sunday.day:02d}'


def fix_formats(service, num_cols):
    """Применяет числовые форматы к строкам 4–96, колонки B (индекс 1) + num_cols."""
    requests = []
    for row in range(FIRST_DATA_ROW, LAST_DATA_ROW + 1):
        if row in PCT_ROWS:
            fmt = {'type': 'PERCENT', 'pattern': '0%'}
        else:
            fmt = {'type': 'NUMBER', 'pattern': '#,##0'}

        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId':          SHEET_GID,
                    'startRowIndex':    row - 1,       # 0-based
                    'endRowIndex':      row,
                    'startColumnIndex': 1,             # столбец B
                    'endColumnIndex':   1 + num_cols,
                },
                'cell': {
                    'userEnteredFormat': {'numberFormat': fmt}
                },
                'fields': 'userEnteredFormat.numberFormat',
            }
        })

    # Шлём пачками по 50 запросов — чтобы не превысить лимит
    batch_size = 50
    for i in range(0, len(requests), batch_size):
        service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={'requests': requests[i:i + batch_size]},
        ).execute()
        print(f'  Форматы: строки {FIRST_DATA_ROW + i}–{min(LAST_DATA_ROW, FIRST_DATA_ROW + i + batch_size - 1)} ✓')

    print(f'✅ Форматы применены: {len(requests)} строк, {num_cols} колонок')


def fix_row3_dates(service, sheet_name, years, weeks):
    """Пересчитывает строку 3: диапазон дат для каждой ISO-недели."""
    dates = []
    for yr, wk in zip(years, weeks):
        try:
            dates.append([iso_week_date_range(yr, wk)])
        except Exception:
            dates.append([''])

    # Транспонируем: нам нужна одна строка из num_cols ячеек
    date_row = [[d[0] for d in dates]]

    num_cols = len(dates)
    range_name = f"'{sheet_name}'!B3:{chr(ord('A') + num_cols)}3" if num_cols <= 25 else None

    # Для большого числа колонок используем числовой адрес через batchUpdate
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'!B3",
        valueInputOption='RAW',
        body={'values': date_row},
    ).execute()

    print(f'✅ Строка 3 заполнена: {num_cols} дат (первая: {date_row[0][0]}, последняя: {date_row[0][-1]})')


def main():
    print('Подключаемся к Google Sheets...')
    service = get_service()
    sheet_name = get_sheet_name(service)
    print(f'  Лист: «{sheet_name}»')

    # Читаем строки 1 и 2 (год и неделя)
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'!B1:ZZ2",
        valueRenderOption='UNFORMATTED_VALUE',
    ).execute()
    rows = result.get('values', [])
    years = rows[0] if len(rows) > 0 else []
    weeks = rows[1] if len(rows) > 1 else []
    num_cols = len(years)
    print(f'  Колонок данных: {num_cols}')
    print(f'  Диапазон: {years[0]} нед.{int(weeks[0])} → {years[-1]} нед.{int(weeks[-1])}')

    print('\n1. Применяем числовые форматы к строкам 4–96...')
    fix_formats(service, num_cols)

    print('\n2. Восстанавливаем даты в строке 3...')
    fix_row3_dates(service, sheet_name, years, weeks)

    print('\nВсё готово!')


if __name__ == '__main__':
    main()
