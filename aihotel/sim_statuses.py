"""Симуляция: заполняем лист 'Статусы' данными нед.11 — все выполнили, кроме Надежды."""
import os, sys
from dotenv import load_dotenv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.sheets import get_client, get_worksheet
load_dotenv()

strategy_sheet_id = os.environ['STRATEGY_SHEET_ID']
gs = get_client()

ws_tasks = get_worksheet(gs, strategy_sheet_id, 'Задачи недели')
rows = ws_tasks.get_all_values()

tasks = []
for row in rows:
    if not row or not row[0]:
        continue
    executor = row[0].strip()
    if executor in ('Исполнитель',) or executor.startswith('ДАЙДЖЕСТ') \
            or executor.startswith('Неделя') or executor.startswith('Черновик'):
        continue
    if len(row) >= 3 and row[2].strip():
        tasks.append({'исполнитель': executor, 'задача': row[2].strip()})

print(f"Найдено задач: {len(tasks)}")

ws_statuses = get_worksheet(gs, strategy_sheet_id, 'Статусы')
ws_statuses.clear()
ws_statuses.update(values=[['Исполнитель', 'Задача', 'Статус', 'Комментарий']], range_name='A1')

status_rows = []
for t in tasks:
    if t['исполнитель'] == 'Надежда':
        status_rows.append([t['исполнитель'], t['задача'], '', 'Не успела — не хватило времени'])
    else:
        status_rows.append([t['исполнитель'], t['задача'], 'да', ''])

if status_rows:
    ws_statuses.append_rows(status_rows)
    print(f"Статусы записаны ({len(status_rows)} строк):")
    for r in status_rows:
        mark = '✅' if r[2] == 'да' else '❌'
        print(f"  {mark} {r[0]}: {r[1][:65]}")
