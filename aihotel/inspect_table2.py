"""Показывает ВСЕ строки финансовой таблицы (столбец C — названия метрик)."""
import os
import sys
import warnings
warnings.filterwarnings('ignore')

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.sheets import get_client

client = get_client()
ss = client.open_by_key(os.environ['FINANCE_SHEET_ID'])

ws = ss.worksheet('Сезон 2026')
# Берём только столбец C чтобы увидеть все метрики
col_c = ws.col_values(3)
print("Все метрики (столбец C):")
for i, val in enumerate(col_c, 1):
    if val.strip():
        print(f"  Строка {i:3d}: {val.strip()}")
