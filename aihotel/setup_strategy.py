"""Устанавливает заголовки в листах стратегической таблицы."""
import os
import sys
import warnings
warnings.filterwarnings('ignore')

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.sheets import get_client

client = get_client()
strategy_id = os.environ['STRATEGY_SHEET_ID']
ss = client.open_by_key(strategy_id)

# Задачи недели — заголовки
ws_tasks = ss.worksheet('Задачи недели')
existing = ws_tasks.row_values(1)
if not any(existing):
    ws_tasks.update('A1', [['Исполнитель', 'Блок', 'Задача', 'Результат', 'Как проверить', 'Срок']])
    print("✅ 'Задачи недели': заголовки добавлены")
else:
    print(f"ℹ️  'Задачи недели': заголовки уже есть → {existing}")

# Статусы — заголовки
ws_statuses = ss.worksheet('Статусы')
existing = ws_statuses.row_values(1)
if not any(existing):
    ws_statuses.update('A1', [['Исполнитель', 'Задача', 'Статус', 'Комментарий']])
    print("✅ 'Статусы': заголовки добавлены")
else:
    print(f"ℹ️  'Статусы': заголовки уже есть → {existing}")

# Архив — просто пустой, заголовки не нужны
print("ℹ️  'Архив': заголовки не нужны, агент заполнит автоматически")

print("\n✅ Стратегическая таблица готова!")
print("   Недели отслеживаются автоматически — объясняю ниже.")
