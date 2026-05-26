"""
Заполняем строки 40-82 листа '2026' за неделю 21
Данные берём из '2026 старый'
"""
import gspread
from google.oauth2.service_account import Credentials

CREDS_FILE = '/Users/user/Downloads/aihotel-gubaha-f2f4b68bb17e.json'
SHEET_ID = '1Ohm7tst750zDzSeIewJFj_cPC6vl0-5J0UiuNfZvY_k'

# Колонка для недели 21 в '2026': C=3 + 20 = W=23 (1-based)
WEEK21_COL = 23  # W

def get_client():
    creds = Credentials.from_service_account_file(
        CREDS_FILE,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return gspread.Client(auth=creds)

def col_to_letter(col_1based):
    """Число колонки → буква (1=A, 23=W и т.д.)"""
    result = ''
    n = col_1based
    while n > 0:
        n -= 1
        result = chr(65 + n % 26) + result
        n //= 26
    return result

def main():
    client = get_client()
    spreadsheet = client.open_by_key(SHEET_ID)
    target_ws = spreadsheet.worksheet('2026')

    col_letter = col_to_letter(WEEK21_COL)
    print(f"Заполняем колонку {col_letter} (неделя 21) в листе '2026'")

    # Маппинг: строка в '2026' → значение из '2026 старый' за неделю 21
    # Источники указаны в комментариях (строка в '2026 старый')
    week21_data = {
        # 👥 СЕГМЕНТЫ ГОСТЕЙ
        40: 3,        # ДР: броней          ← old row 67: Броней ДР
        41: 1,        # ДР: проживаний      ← old row 69: Проживаний ДР
        42: 12850,    # ДР: сумма           ← old row 70: Сумма по ДР
        44: 0,        # Группы: броней      ← old row 77: Броней групп
        45: 0,        # Группы: проживаний  ← old row 79: Проживаний групп
        46: 0,        # Группы: сумма       ← old row 80: Сумма по группам
        48: 0,        # Корпоративы: броней ← old row 72: Броней корпоратив
        49: 0,        # Корпоративы: сумма  ← old row 75: Сумма от корпорантов
        51: 7,        # Физики: броней      ← old row 82: Броней физиков
        52: 40925,    # Физики: сумма       ← old row 85: Сумма по физикам

        # ⭐ КАЧЕСТВО СЕРВИСА
        54: '100%',   # NPS                          ← old row 58
        56: 1,        # Отзывы коттеджи (кол-во)     ← old row 59
        57: '0%',     # Отзывы коттеджи (негат. %)   ← old row 60
        59: 0,        # Отзывы хостелы (кол-во)      ← old row 61
        60: '0%',     # Отзывы хостелы (негат. %)    ← old row 62

        # ⚙️ ОПЕРАЦИИ И ДЕНЬГИ
        62: 8749350,  # Остаток на счёте     ← old row 33
        63: 287909,   # Остаток в кассе      ← old row 34
        65: 0,        # Кредит. задолж.      ← old row 31
        66: 0,        # Дебит. задолж.       ← old row 32

        # Ремонт
        68: 0,        # Ремонт: заявок       ← old row 88
        69: 0,        # Ремонт: выполнено    ← old row 89
        70: 0,        # Ремонт: не выполнено ← old row 90

        # Уборки
        72: 4,        # Уборки коттеджи          ← old row 92
        73: 0,        # Из них стыковочных (кот.) ← old row 93
        74: 0,        # Уборки хостелы            ← old row 94

        # Звонки
        76: 0,        # Звонков входящих     ← old row 97
        77: 0,        # Неотвеченных         ← old row 98
        78: '0%',     # Доля без ответа      ← old row 99 (#DIV/0! → 0% т.к. 0 из 0)

        # Персонал
        80: 1,        # Проверок стандартов        ← old row 101
        81: 80878,    # ФОТ горничные+техники       ← old row 102
        82: 38570,    # ФОТ F&B персонал            ← old row 103
    }

    # Формируем batch update
    updates = []
    for row_num, value in sorted(week21_data.items()):
        cell_range = f"{col_letter}{row_num}"
        updates.append({
            'range': cell_range,
            'values': [[value]]
        })
        print(f"  {cell_range}: {value}")

    print(f"\nЗаписываем {len(updates)} ячеек...")
    target_ws.batch_update(updates, value_input_option='USER_ENTERED')
    print("✅ Готово!")

    # Проверка — читаем обратно что записали
    print("\nПроверка (читаем обратно):")
    for row_num in sorted(week21_data.keys()):
        cell = f"{col_letter}{row_num}"
        actual = target_ws.acell(cell, value_render_option='FORMATTED_VALUE').value
        expected = week21_data[row_num]
        status = "✅" if str(actual) else "❌"
        print(f"  {status} {cell}: записали={expected}, в таблице={actual}")

if __name__ == '__main__':
    main()
