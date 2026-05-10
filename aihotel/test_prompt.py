"""
Тестовый скрипт для итерации промпта Агента 2.

Читает дайджест из таблицы → вызывает Groq → печатает задачи в консоль.
НЕ пишет в таблицу, НЕ трогает флаги. Безопасно запускать многократно.

Рабочий цикл:
  1. python agents/agent1_analyst.py <НОМЕР_НЕДЕЛИ>   # генерирует дайджест
  2. python test_prompt.py                             # смотрим задачи
  3. Правим utils/prompts.py → снова python test_prompt.py
"""
import os
import sys
import json
import time
from groq import Groq
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.sheets import get_client, get_worksheet
from utils.prompts import build_agent2_system_prompt

load_dotenv()

COLS = {'исполнитель': 18, 'блок': 6, 'задача': 50, 'результат': 45,
        'проверка': 45, 'срок': 16, 'цель': 50}


def call_groq(system_prompt: str, user_message: str) -> str:
    client = Groq(api_key=os.environ['GROQ_API_KEY'])
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model='llama-3.3-70b-versatile',
                max_tokens=4096,
                response_format={'type': 'json_object'},
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message},
                ],
            )
            return response.choices[0].message.content
        except Exception as e:
            if attempt < 2:
                print(f"  Ошибка Groq API (попытка {attempt + 1}): {e}. Жду 5 сек...")
                time.sleep(5)
            else:
                raise RuntimeError(f"Groq API недоступен: {e}")


def parse_tasks(raw: str) -> list:
    raw = raw.strip()
    start = raw.find('[')
    end = raw.rfind(']') + 1
    if start == -1 or end == 0:
        raise ValueError("JSON-массив не найден в ответе")
    return json.loads(raw[start:end])


def wrap(text: str, width: int) -> list:
    words = str(text).split()
    lines, line = [], []
    length = 0
    for word in words:
        if length + len(word) + bool(line) > width:
            lines.append(' '.join(line))
            line, length = [word], len(word)
        else:
            line.append(word)
            length += len(word) + bool(line) - 1
    if line:
        lines.append(' '.join(line))
    return lines or ['']


def print_task(i: int, task: dict) -> None:
    executor = task.get('исполнитель', '?')
    block = task.get('блок', '?')
    fields = [
        ('Задача',    task.get('задача', ''),    COLS['задача']),
        ('Результат', task.get('результат', ''), COLS['результат']),
        ('Проверка',  task.get('проверка', ''),  COLS['проверка']),
        ('Срок',      task.get('срок', ''),       COLS['срок']),
        ('KPI',       task.get('цель', ''),       COLS['цель']),
    ]
    print(f"\n{'─'*70}")
    print(f"  #{i}  {executor}  [Блок {block}]")
    print(f"{'─'*70}")
    for label, value, width in fields:
        lines = wrap(value, width)
        print(f"  {label:<10} {lines[0]}")
        for extra in lines[1:]:
            print(f"  {'':<10} {extra}")


def main():
    finance_sheet_id = os.environ['FINANCE_SHEET_ID']
    strategy_sheet_id = os.environ['STRATEGY_SHEET_ID']

    print("Подключаюсь к Google Sheets...")
    gs = get_client()

    print("Читаю дайджест...")
    ws_digest = get_worksheet(gs, finance_sheet_id, 'Дайджест')
    digest_rows = ws_digest.get_all_values()
    digest_text = '\n'.join(
        ' | '.join(cell.strip() for cell in row if cell.strip())
        for row in digest_rows
        if any(cell.strip() for cell in row)
    ) or "Дайджест пуст."
    print(f"  {len(digest_text)} символов")

    print("Читаю базу знаний...")
    ws_knowledge = get_worksheet(gs, finance_sheet_id, 'База знаний')
    knowledge_rows = ws_knowledge.get_all_values()
    knowledge_base = "\n".join([" ".join(row) for row in knowledge_rows if any(row)])

    print("Читаю архив задач...")
    ws_archive = get_worksheet(gs, strategy_sheet_id, 'Архив')
    all_archive = ws_archive.get_all_values()
    if all_archive:
        week_indices = [i for i, row in enumerate(all_archive)
                        if row and row[0].startswith('Неделя ')]
        start = week_indices[-4] if len(week_indices) >= 4 else 0
        archive_lines = [' | '.join(r) for r in all_archive[start:] if any(r)]
        archive_text = '\n'.join(archive_lines) or "Архив пуст."
    else:
        archive_text = "Архив пуст — первая неделя."

    system_prompt = build_agent2_system_prompt()
    user_message = f"""АРХИВ ЗАДАЧ ПРОШЛЫХ НЕДЕЛЬ:
{archive_text}

ДАЙДЖЕСТ ТЕКУЩЕЙ НЕДЕЛИ:
{digest_text}

ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ (база знаний объекта):
{knowledge_base}

Сформируй задачи для команды на эту неделю."""

    print("Вызываю Groq API...")
    raw = call_groq(system_prompt, user_message)

    print("Парсинг...")
    tasks = parse_tasks(raw)

    print(f"\n{'═'*70}")
    print(f"  ЗАДАЧИ НА НЕДЕЛЮ  ({len(tasks)} задач)")
    print(f"{'═'*70}")

    by_person: dict = {}
    for task in tasks:
        name = task.get('исполнитель', 'Неизвестный')
        by_person.setdefault(name, []).append(task)

    idx = 1
    for name, person_tasks in by_person.items():
        for task in person_tasks:
            print_task(idx, task)
            idx += 1

    print(f"\n{'═'*70}")
    print(f"  Итого: {len(tasks)} задач для {len(by_person)} исполнителей")
    print(f"{'═'*70}\n")


if __name__ == '__main__':
    main()
