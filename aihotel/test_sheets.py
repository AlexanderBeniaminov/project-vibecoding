"""
Тест подключения к Google Sheets.
Запуск: python test_sheets.py

Что проверяет:
1. GOOGLE_CREDS_JSON парсится как валидный JSON
2. Подключение к Google Sheets через Service Account
3. Доступ к финансовой и стратегической таблицам
4. Листы существуют и читаются
"""
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def check(label, ok, detail=''):
    icon = '✅' if ok else '❌'
    print(f'  {icon} {label}', f'— {detail}' if detail else '')
    return ok


def main():
    print('=== Тест Google Sheets ===\n')
    all_ok = True

    # 1. Переменные окружения
    print('1. Переменные окружения:')
    for var in ['GOOGLE_CREDS_JSON', 'FINANCE_SHEET_ID', 'STRATEGY_SHEET_ID']:
        val = os.environ.get(var, '')
        ok = bool(val)
        all_ok &= check(var, ok, 'заполнена' if ok else 'ПУСТО — добавь в .env')

    # 2. Парсинг JSON
    print('\n2. Парсинг GOOGLE_CREDS_JSON:')
    creds_raw = os.environ.get('GOOGLE_CREDS_JSON', '')
    try:
        creds_info = json.loads(creds_raw)
        check('json.loads()', True, f"project_id: {creds_info.get('project_id', '?')}")
        check('тип аккаунта', creds_info.get('type') == 'service_account',
              creds_info.get('type', 'не найдено'))
    except Exception as e:
        all_ok = False
        check('json.loads()', False, str(e))
        print('\nСовет: GOOGLE_CREDS_JSON должна содержать ВЕСЬ JSON из credentials.json одной строкой')
        return

    # 3. Подключение к gspread
    print('\n3. Подключение к Google Sheets:')
    try:
        from utils.sheets import get_client
        client = get_client()
        check('get_client()', True, 'Service Account авторизован')
    except Exception as e:
        all_ok = False
        check('get_client()', False, str(e))
        print('\nСовет: убедись, что Service Account добавлен в общий доступ обеих таблиц')
        return

    # 4. Финансовая таблица
    print('\n4. Финансовая таблица (FINANCE_SHEET_ID):')
    finance_id = os.environ.get('FINANCE_SHEET_ID', '')
    required_sheets = ['Статус системы', 'Дайджест', 'Анализ', 'База знаний']
    try:
        spreadsheet = client.open_by_key(finance_id)
        check('открыть таблицу', True, spreadsheet.title)
        existing = [ws.title for ws in spreadsheet.worksheets()]
        print(f'  Листы в таблице: {existing}')
        for sheet_name in required_sheets:
            ok = sheet_name in existing
            all_ok &= check(f'лист "{sheet_name}"', ok, 'найден' if ok else 'СОЗДАТЬ ВРУЧНУЮ')
    except Exception as e:
        all_ok = False
        check('открыть финансовую таблицу', False, str(e))
        print('\nСовет: скопируй ID из URL таблицы (между /d/ и /edit)')

    # 5. Стратегическая таблица
    print('\n5. Стратегическая таблица (STRATEGY_SHEET_ID):')
    strategy_id = os.environ.get('STRATEGY_SHEET_ID', '')
    required_strategy = ['Задачи недели', 'Статусы', 'Архив']
    try:
        spreadsheet = client.open_by_key(strategy_id)
        check('открыть таблицу', True, spreadsheet.title)
        existing = [ws.title for ws in spreadsheet.worksheets()]
        print(f'  Листы в таблице: {existing}')
        for sheet_name in required_strategy:
            ok = sheet_name in existing
            all_ok &= check(f'лист "{sheet_name}"', ok, 'найден' if ok else 'СОЗДАТЬ ВРУЧНУЮ')
    except Exception as e:
        all_ok = False
        check('открыть стратегическую таблицу', False, str(e))

    print('\n' + ('='*40))
    if all_ok:
        print('✅ Все проверки пройдены! Google Sheets готов.')
    else:
        print('❌ Есть проблемы — исправь отмеченные пункты и запусти снова.')


if __name__ == '__main__':
    main()
