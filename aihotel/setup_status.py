"""Заполняет лист Статус системы и показывает структуру таблицы."""
import os
import sys
import warnings
warnings.filterwarnings('ignore')

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.sheets import get_client

client = get_client()
finance_id = os.environ['FINANCE_SHEET_ID']
ss = client.open_by_key(finance_id)

# Все листы
all_sheets = [ws.title for ws in ss.worksheets()]
print(f"Все листы финансовой таблицы: {all_sheets}")

# Заполняем Статус системы
ws_status = ss.worksheet('Статус системы')
ws_status.update('A1', [
    ['ключ', 'значение'],
    ['неделя', ''],
    ['данные_внесены', 'нет'],
    ['анализ_готов', 'нет'],
    ['дайджест_записан', 'нет'],
    ['задачи_сформированы', 'нет'],
    ['задачи_утверждены', 'нет'],
    ['задачи_отправлены', 'нет'],
])
print("✅ Лист 'Статус системы' заполнен")

# Смотрим структуру листа с данными (Сезон 2026)
try:
    ws_data = ss.worksheet('Сезон 2026')
    headers = ws_data.row_values(1)
    first_row = ws_data.row_values(2)
    print(f"\nЛист 'Сезон 2026':")
    print(f"  Заголовки: {headers}")
    print(f"  Первая строка данных: {first_row}")
except Exception as e:
    print(f"Лист 'Сезон 2026': {e}")
