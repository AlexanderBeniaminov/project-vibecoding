"""Показывает структуру финансовой таблицы — первые 20 строк и 10 столбцов."""
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

for sheet_name in ['Сезон 2026', '2025']:
    print(f"\n{'='*60}")
    print(f"ЛИСТ: {sheet_name}")
    print('='*60)
    try:
        ws = ss.worksheet(sheet_name)
        # Берём первые 25 строк и 8 столбцов
        data = ws.get('A1:H25')
        for i, row in enumerate(data, 1):
            # Убираем пустые с конца
            while row and row[-1].strip() == '':
                row.pop()
            if any(cell.strip() for cell in row):
                print(f"Строка {i:2d}: {row}")
    except Exception as e:
        print(f"Ошибка: {e}")
