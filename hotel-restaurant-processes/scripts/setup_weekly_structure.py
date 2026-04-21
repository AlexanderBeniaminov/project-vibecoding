"""
Применяет структуру столбца A на лист «Монблан» (gid=2051236241)
и защищает его от изменений через Sheets API.

Запуск: python setup_weekly_structure.py
"""

import json
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = '1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI'
SHEET_GID      = 2051236241
CREDS_FILE     = 'credentials.json'

MB_LABELS = [
    'Год',                               # 1
    'Неделя',                            # 2
    'Монблан',                           # 3
    'Выручка всего и по категориям',     # 4
    'Кухня',                             # 5
    '',                                  # 6
    'Бар',                               # 7
    '',                                  # 8
    'Выручка день - вечер',              # 9
    'Утро (9:00 - 11:00)',               # 10
    '',                                  # 11
    'День (11:00 - 17:00)',              # 12
    '',                                  # 13
    'Вечер (17:00 - 21:00)',             # 14
    '',                                  # 15
    'Средняя выручка по дням недели',    # 16
    'Понедельник',                       # 17
    '',                                  # 18
    'Вторник',                           # 19
    '',                                  # 20
    'Среда',                             # 21
    '',                                  # 22
    'Четверг',                           # 23
    '',                                  # 24
    'Пятница',                           # 25
    '',                                  # 26
    'Суббота',                           # 27
    '',                                  # 28
    'Воскресенье',                       # 29
    '',                                  # 30
    'Кол-во гостей',                     # 31
    'Утро (9:00 - 11:00)',               # 32
    '',                                  # 33
    'День (11:00 - 17:00)',              # 34
    '',                                  # 35
    'Вечер (17:00 - 21:00)',             # 36
    '',                                  # 37
    'Средний чек на гостя',              # 38
    'Утро (9:00 - 11:00)',               # 39
    'День (11:00 - 17:00)',              # 40
    'Вечер (17:00 - 21:00)',             # 41
    'Кол-во чеков',                      # 42
    'Утро (9:00 - 11:00)',               # 43
    'День (11:00 - 17:00)',              # 44
    'Вечер (17:00 - 21:00)',             # 45
    'Количество блюд',                   # 46
    'Средний счет',                      # 47
    'Средний чек на блюдо',              # 48
    'Средний чек на гостя (кухня)',      # 49
    'Средний чек на гостя (бар)',        # 50
    'Ср. кол-во блюд на гостя',          # 51
    'Оборачиваемость столов',            # 52
    'Утро (9:00 - 11:00)',               # 53
    'День (11:00 - 17:00)',              # 54
    'Вечер (17:00 - 21:00)',             # 55
    'Оборачиваемость пос. мест',         # 56
    'Утро (9:00 - 11:00)',               # 57
    'День (11:00 - 17:00)',              # 58
    'Вечер (17:00 - 21:00)',             # 59
    'Вклад в выручку группы гостей',     # 60
    'Выручка по чекам 1 гость',          # 61
    '',                                  # 62
    'Выручка по чекам 2 гостя',          # 63
    '',                                  # 64
    'Выручка по чекам 3+ гостя',         # 65
    '',                                  # 66
    'Коэффициент групповой лояльности',  # 67
    'Кол-во чеков 1 гость',              # 68
    '',                                  # 69
    'Кол-во чеков 2 гостя',              # 70
    '',                                  # 71
    'Кол-во чеков 3 + гостя',            # 72
    '',                                  # 73
    'Градация чеков по сумме, выручка',  # 74
    '0-500 руб.',                        # 75
    '',                                  # 76
    '500-1000 руб.',                     # 77
    '',                                  # 78
    '1000-1500 руб.',                    # 79
    '',                                  # 80
    '1500-3000 руб.',                    # 81
    '',                                  # 82
    '3000-5000 руб.',                    # 83
    '',                                  # 84
    '5000 + руб',                        # 85
    '',                                  # 86
    'Столов',                            # 87
    'Посадочных мест',                   # 88
    '',                                  # 89
    'Мероприятия',                       # 90
    'Завтраки (кол-во по гостям)',       # 91
    'Количество мероприятий',            # 92
    'Выручка мероприятий',               # 93
    'Количество гостей',                 # 94
    'Средний чек на гостя',              # 95
    'Средний чек на мероприятие',        # 96
]


def get_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDS_FILE,
        scopes=['https://www.googleapis.com/auth/spreadsheets'],
    )
    return build('sheets', 'v4', credentials=creds)


def get_sheet_name(service):
    """Возвращает имя листа по GID."""
    spreadsheet = service.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        fields='sheets.properties',
    ).execute()
    for sheet in spreadsheet.get('sheets', []):
        props = sheet['properties']
        if props['sheetId'] == SHEET_GID:
            return props['title']
    raise ValueError(f'Лист с GID={SHEET_GID} не найден')


def write_column_a(service, sheet_name):
    """Записывает все 96 меток в столбец A."""
    values = [[label] for label in MB_LABELS]
    range_name = f"'{sheet_name}'!A1:A96"
    body = {
        'valueInputOption': 'RAW',
        'data': [{'range': range_name, 'values': values}],
    }
    result = service.spreadsheets().values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body=body,
    ).execute()
    updated = result.get('totalUpdatedCells', 0)
    print(f'✅ Записано ячеек в столбец A: {updated}')


def protect_column_a(service):
    """Добавляет защищённый диапазон A1:A96 (только для редакторов таблицы)."""

    # Сначала удаляем старую защиту MB_COLUMN_A_STRUCTURE если есть
    spreadsheet = service.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        fields='sheets.protectedRanges,sheets.properties.sheetId',
    ).execute()

    delete_requests = []
    for sheet in spreadsheet.get('sheets', []):
        if sheet['properties']['sheetId'] != SHEET_GID:
            continue
        for pr in sheet.get('protectedRanges', []):
            if pr.get('description') == 'MB_COLUMN_A_STRUCTURE':
                delete_requests.append({
                    'deleteProtectedRange': {'protectedRangeId': pr['protectedRangeId']}
                })

    if delete_requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={'requests': delete_requests},
        ).execute()
        print(f'  Удалено старых защит: {len(delete_requests)}')

    # Добавляем новую защиту — warningOnly=True:
    # не блокирует полностью (сервисный аккаунт не может выдавать права пользователям),
    # но показывает предупреждение при попытке редактировать столбец A.
    add_request = {
        'addProtectedRange': {
            'protectedRange': {
                'range': {
                    'sheetId': SHEET_GID,
                    'startRowIndex': 0,    # строка 1 (0-based)
                    'endRowIndex': 96,     # строка 96 включительно
                    'startColumnIndex': 0, # столбец A
                    'endColumnIndex': 1,
                },
                'description': 'MB_COLUMN_A_STRUCTURE',
                'warningOnly': True,       # предупреждение вместо жёсткой блокировки
            }
        }
    }

    result = service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={'requests': [add_request]},
    ).execute()

    pr_id = result['replies'][0]['addProtectedRange']['protectedRange']['protectedRangeId']
    print(f'✅ Защита установлена (ID={pr_id}), диапазон A1:A96')
    print('   Режим: warningOnly — при изменении ячейки показывается предупреждение.')
    print('   Для жёсткой блокировки — добавьте editors через Apps Script.')


def main():
    print('Подключаемся к Google Sheets...')
    service = get_service()

    sheet_name = get_sheet_name(service)
    print(f'  Лист найден: «{sheet_name}»')

    print('\n1. Записываем структуру столбца A (96 строк)...')
    write_column_a(service, sheet_name)

    print('\n2. Устанавливаем защиту на A1:A96...')
    protect_column_a(service)

    print('\nГотово!')


if __name__ == '__main__':
    main()
