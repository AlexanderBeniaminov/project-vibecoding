import os
import sys
import json
import time
import datetime
from groq import Groq
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.sheets import get_client, get_worksheet, get_flag, set_flag
from utils.prompts import build_agent2_system_prompt

load_dotenv()


def get_current_week() -> str:
    today = datetime.date.today()
    iso = today.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def get_week_dates(week_str: str) -> str:
    year, week = int(week_str[:4]), int(week_str[6:])
    monday = datetime.date.fromisocalendar(year, week, 1)
    sunday = monday + datetime.timedelta(days=6)
    return f"{monday.strftime('%-d %b')} – {sunday.strftime('%-d %b %Y')}"


def call_claude(system_prompt: str, user_message: str) -> str:
    client = Groq(api_key=os.environ['GROQ_API_KEY'])
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model='llama-3.3-70b-versatile',
                max_tokens=4096,
                response_format={'type': 'json_object'},  # гарантирует валидный JSON
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


def archive_current_tasks(ws_tasks: object, ws_archive: object, current_week: str) -> None:
    all_rows = ws_tasks.get_all_values()
    if len(all_rows) <= 1:
        print("  Нет задач для архивирования")
        return

    week_label = [f"Неделя {current_week}"] + [""] * (len(all_rows[0]) - 1)
    task_rows = all_rows[1:]  # без заголовка
    rows_to_add = [week_label] + task_rows
    ws_archive.append_rows(rows_to_add)
    print(f"  Архивировано {len(task_rows)} задач")


def get_recent_archive(ws_archive: object, weeks: int = 4) -> str:
    all_values = ws_archive.get_all_values()
    if not all_values:
        return "Архив пуст — это первая неделя работы системы."

    # Находим маркеры недель
    week_indices = []
    for i, row in enumerate(all_values):
        if row and row[0].startswith('Неделя '):
            week_indices.append(i)

    # Берём последние N недель
    start_idx = week_indices[-weeks] if len(week_indices) >= weeks else 0
    recent_rows = all_values[start_idx:]

    lines = []
    for row in recent_rows:
        if any(row):
            lines.append(" | ".join(row))
    return "\n".join(lines) if lines else "Нет данных в архиве."


def parse_tasks_json(raw: str) -> list:
    # Убираем возможный текст до/после JSON
    raw = raw.strip()
    start = raw.find('[')
    end = raw.rfind(']') + 1
    if start == -1 or end == 0:
        raise ValueError("JSON-массив не найден в ответе")
    return json.loads(raw[start:end])


def main():
    print("=== Агент 2: Стратег ===")
    current_week = get_current_week()
    print(f"Текущая неделя: {current_week}")

    finance_sheet_id = os.environ['FINANCE_SHEET_ID']
    strategy_sheet_id = os.environ['STRATEGY_SHEET_ID']

    print("Подключаюсь к Google Sheets...")
    client_gs = get_client()

    # Идемпотентность
    ws_status = get_worksheet(client_gs, finance_sheet_id, 'Статус системы')
    if get_flag(ws_status, 'задачи_сформированы') == 'да':
        print("Задачи уже сформированы на этой неделе. Выхожу.")
        return

    # Проверяем что дайджест готов
    if get_flag(ws_status, 'дайджест_записан') != 'да':
        print("ПРЕДУПРЕЖДЕНИЕ: Агент 1 ещё не записал дайджест. Запусти сначала agent1_analyst.py")
        sys.exit(1)

    # Читаем базу знаний
    print("Читаю базу знаний...")
    ws_knowledge = get_worksheet(client_gs, finance_sheet_id, 'База знаний')
    knowledge_rows = ws_knowledge.get_all_values()
    knowledge_base = "\n".join([" ".join(row) for row in knowledge_rows if any(row)])

    # Читаем дайджест — читаем ВСЕ строки листа (агент 1 пишет форматированную таблицу)
    print("Читаю дайджест от Агента 1...")
    ws_digest = get_worksheet(client_gs, finance_sheet_id, 'Дайджест')
    digest_rows = ws_digest.get_all_values()
    digest_text = '\n'.join(
        ' | '.join(cell.strip() for cell in row if cell.strip())
        for row in digest_rows
        if any(cell.strip() for cell in row)
    ) or "Дайджест пуст."
    print(f"  Дайджест: {len(digest_text)} символов")

    # Читаем архив
    print("Читаю архив задач...")
    ws_tasks = get_worksheet(client_gs, strategy_sheet_id, 'Задачи недели')
    ws_archive = get_worksheet(client_gs, strategy_sheet_id, 'Архив')
    archive_text = get_recent_archive(ws_archive)

    # Архивируем текущие задачи перед перезаписью
    print("Архивирую задачи прошлой недели...")
    archive_current_tasks(ws_tasks, ws_archive, current_week)

    # Очищаем лист задач (оставляем заголовок)
    header = ws_tasks.row_values(1)
    ws_tasks.clear()
    if header:
        ws_tasks.update(values=[header], range_name='A1')

    # Формируем промпт
    system_prompt = build_agent2_system_prompt()
    user_message = f"""АРХИВ ЗАДАЧ ПРОШЛЫХ НЕДЕЛЬ:
{archive_text}

ДАЙДЖЕСТ ТЕКУЩЕЙ НЕДЕЛИ:
{digest_text}

ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ (база знаний объекта):
{knowledge_base}

Сформируй задачи для всех 6 исполнителей на неделю {current_week}."""

    # Вызов Claude
    print("Формирую задачи через Claude API...")
    try:
        raw_response = call_claude(system_prompt, user_message)
    except RuntimeError as e:
        print(f"ОШИБКА: Агент 2: ошибка Groq API. Нужна ручная постановка задач. Ошибка: {e}")
        sys.exit(1)

    # Парсинг JSON
    print("Парсинг JSON-ответа...")
    try:
        tasks = parse_tasks_json(raw_response)
        print(f"  Получено {len(tasks)} задач")
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ОШИБКА: Агент 2: не удалось распарсить JSON. Нужна ручная постановка задач.\nОшибка: {e}\nОтвет (первые 500 символов): {raw_response[:500]}")
        sys.exit(1)

    # Запись задач в таблицу
    print("Записываю задачи в таблицу...")
    rows_to_write = []
    for task in tasks:
        rows_to_write.append([
            task.get('исполнитель', ''),
            task.get('блок', ''),
            task.get('задача', ''),
            task.get('результат', ''),
            task.get('проверка', ''),
            task.get('срок', ''),
            task.get('цель', ''),
        ])

    if rows_to_write:
        week_dates = get_week_dates(current_week)
        week_label = f"Неделя {current_week}  |  {week_dates}"
        if not header:
            ws_tasks.update(values=[['Исполнитель', 'Блок', 'Задача', 'Результат', 'Как проверить', 'Срок', 'Стратегическая цель']], range_name='A1')
        # Строка-разделитель с номером недели перед задачами
        ws_tasks.append_rows([[week_label] + [''] * 6] + rows_to_write)

    set_flag(ws_status, 'задачи_сформированы', 'да')

    print("\n✅ Агент 2 завершил работу.")
    print(f"   Сформировано задач: {len(tasks)}")
    by_person = {}
    for t in tasks:
        name = t.get('исполнитель', 'Неизвестный')
        by_person[name] = by_person.get(name, 0) + 1
    for name, count in by_person.items():
        print(f"   {name}: {count} задач(и)")


if __name__ == '__main__':
    main()
