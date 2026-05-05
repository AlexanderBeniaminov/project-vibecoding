"""Создаёт необходимые листы в обеих таблицах. Запустить один раз."""
import os
import sys
import warnings
warnings.filterwarnings('ignore')

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.sheets import get_client

client = get_client()

# === Стратегическая таблица ===
print("Стратегическая таблица...")
strategy_id = os.environ['STRATEGY_SHEET_ID']
ss = client.open_by_key(strategy_id)
existing = [ws.title for ws in ss.worksheets()]
print(f"  Текущие листы: {existing}")

if 'Задачи недели' not in existing:
    ws = ss.add_worksheet(title='Задачи недели', rows=100, cols=6)
    ws.update('A1', [['Исполнитель', 'Блок', 'Задача', 'Результат', 'Как проверить', 'Срок']])
    print("  ✅ Создан лист 'Задачи недели'")
else:
    print("  ℹ️  'Задачи недели' уже есть")

if 'Статусы' not in existing:
    ws = ss.add_worksheet(title='Статусы', rows=100, cols=4)
    ws.update('A1', [['Исполнитель', 'Задача', 'Статус', 'Комментарий']])
    print("  ✅ Создан лист 'Статусы'")
else:
    print("  ℹ️  'Статусы' уже есть")

if 'Архив' not in existing:
    ss.add_worksheet(title='Архив', rows=500, cols=6)
    print("  ✅ Создан лист 'Архив'")
else:
    print("  ℹ️  'Архив' уже есть")

print(f"  Итог: {[ws.title for ws in ss.worksheets()]}")

# === Финансовая таблица ===
print("\nФинансовая таблица...")
finance_id = os.environ['FINANCE_SHEET_ID']
try:
    ss_finance = client.open_by_key(finance_id)
    existing_f = [ws.title for ws in ss_finance.worksheets()]
    print(f"  Текущие листы: {existing_f}")

    needed = ['Статус системы', 'Дайджест', 'Анализ', 'База знаний']
    for name in needed:
        if name not in existing_f:
            ss_finance.add_worksheet(title=name, rows=50, cols=10)
            print(f"  ✅ Создан лист '{name}'")
        else:
            print(f"  ℹ️  '{name}' уже есть")

    # Заполняем Статус системы если пустой
    ws_status = ss_finance.worksheet('Статус системы')
    current = ws_status.get_all_values()
    if not current or current[0][0] != 'ключ':
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
        print("  ✅ Заполнен лист 'Статус системы'")

except Exception as e:
    print(f"  ❌ Ошибка: {e}")
    print()
    print("  Скорее всего финансовая таблица — Excel-файл (.xlsx).")
    print("  Что сделать:")
    print("  1. Открой файл в Google Drive")
    print("  2. Меню Файл → Сохранить как Google Таблицы")
    print("  3. Скопируй ID новой таблицы и обнови FINANCE_SHEET_ID в .env")

print("\n✅ Готово!")
