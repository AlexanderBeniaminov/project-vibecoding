"""
Тестовый скрипт для итерации промпта Агента 2.

Читает дайджест из таблицы → вызывает Groq → ПИШЕТ задачи в лист «Задачи недели».
Флаги и архив НЕ трогает. Безопасно запускать многократно — каждый запуск
перезаписывает лист задач черновиком текущей итерации.

Рабочий цикл:
  1. python agents/agent1_analyst.py <НОМЕР_НЕДЕЛИ>   # генерирует дайджест
  2. python test_prompt.py                             # пишет задачи в таблицу
  3. Читаем задачи в Google Sheet, даём комментарии
  4. Правим utils/prompts.py → снова python test_prompt.py
"""
import os
import sys
import json
import time
import datetime
from groq import Groq
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.sheets import get_client, get_worksheet
from utils.prompts import build_agent2_system_prompt

load_dotenv()


def get_current_week() -> str:
    today = datetime.date.today()
    iso = today.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def call_groq(system_prompt: str, user_message: str) -> str:
    client = Groq(api_key=os.environ['GROQ_API_KEY'])
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model='llama-3.3-70b-versatile',
                max_tokens=2800,
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


def sanitize_tasks(tasks: list) -> list:
    """Постобработка: исправляем устойчивые ошибки модели."""
    nadezhda_fixes = [
        ('скриншот из TravelLine', 'скриншот с сайта'),
        ('в TravelLine', 'на сайте'),
        ('из TravelLine', 'с сайта'),
        ('TravelLine', 'сайте'),
    ]
    upravlyayushchy_proверка_fixes = [
        ('Отчет в Bitrix', 'Фото проблемных мест — Виктору'),
        ('Отчёт в Bitrix', 'Фото проблемных мест — Виктору'),
        ('отчет в Bitrix', 'Фото проблемных мест — Виктору'),
    ]
    for task in tasks:
        executor = task.get('исполнитель', '')
        if executor == 'Надежда':
            for field in ('задача', 'результат', 'проверка'):
                val = task.get(field, '')
                for old, new in nadezhda_fixes:
                    val = val.replace(old, new)
                task[field] = val
        if executor == 'Управляющий':
            val = task.get('проверка', '')
            for old, new in upravlyayushchy_proверка_fixes:
                val = val.replace(old, new)
            task['проверка'] = val
    return tasks


def write_tasks_to_sheet(ws_tasks, tasks: list, week_label: str) -> None:
    header = ['Исполнитель', 'Блок', 'Задача', 'Результат', 'Как проверить', 'Срок', 'Стратегическая цель']
    ws_tasks.clear()
    ws_tasks.update(values=[header], range_name='A1')

    rows = [[week_label] + [''] * 6]

    # Группируем по исполнителю для читаемости
    by_person: dict = {}
    for task in tasks:
        name = task.get('исполнитель', 'Неизвестный')
        by_person.setdefault(name, []).append(task)

    for name, person_tasks in by_person.items():
        for task in person_tasks:
            rows.append([
                task.get('исполнитель', ''),
                task.get('блок', ''),
                task.get('задача', ''),
                task.get('результат', ''),
                task.get('проверка', ''),
                task.get('срок', ''),
                task.get('цель', ''),
            ])

    ws_tasks.append_rows(rows)
    print(f"  Записано {len(tasks)} задач для {len(by_person)} исполнителей")


def print_tasks(tasks: list) -> None:
    by_person: dict = {}
    for task in tasks:
        name = task.get('исполнитель', 'Неизвестный')
        by_person.setdefault(name, []).append(task)

    print(f"\n{'═'*70}")
    print(f"  ЗАДАЧИ ({len(tasks)} задач для {len(by_person)} исполнителей)")
    print(f"{'═'*70}")

    for name, person_tasks in by_person.items():
        print(f"\n  ▶ {name} ({len(person_tasks)} задач)")
        for i, task in enumerate(person_tasks, 1):
            print(f"  {'─'*66}")
            print(f"  #{i} [{task.get('блок', '?')}]  {task.get('задача', '')[:80]}")
            print(f"     Результат:  {task.get('результат', '')[:70]}")
            print(f"     Проверка:   {task.get('проверка', '')[:70]}")
            print(f"     Срок:       {task.get('срок', '')}")
            print(f"     KPI:        {task.get('цель', '')[:70]}")

    print(f"\n{'═'*70}\n")


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
    tasks = sanitize_tasks(parse_tasks(raw))

    # Формируем метку недели из дайджеста (берём первую строку)
    first_line = digest_rows[0][0] if digest_rows and digest_rows[0] else ''
    week_label = first_line if first_line else f"Черновик {get_current_week()}"

    # Записываем в Google Sheet
    print("Записываю в лист «Задачи недели»...")
    ws_tasks = get_worksheet(gs, strategy_sheet_id, 'Задачи недели')
    write_tasks_to_sheet(ws_tasks, tasks, week_label)

    # Дублируем в консоль для удобства
    print_tasks(tasks)

    print("✅ Задачи записаны в Google Sheet → лист «Задачи недели»")
    print(f"   Откройте таблицу и проверьте задачи.")


if __name__ == '__main__':
    main()
