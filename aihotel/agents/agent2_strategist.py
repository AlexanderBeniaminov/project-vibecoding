import os
import sys
import json
import time
import datetime
import openai
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.sheets import get_client, get_worksheet, get_flag, set_flag
from utils.prompts import build_agent2_system_prompt
from utils.kpi_tracker import build_kpi_progress_block

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


def extract_data_week(digest_rows: list) -> tuple:
    """Читает номер недели и дату из заголовка дайджеста Агента 1.
    Возвращает ('2026-W13', '23.03-29.03') или (None, '') если не найдено.
    """
    import re
    if not digest_rows:
        return None, ''
    first_cell = digest_rows[0][0] if digest_rows[0] else ''
    # Формат: "ДАЙДЖЕСТ  |  Неделя 13  |  23.03-29.03"
    match = re.search(r'Неделя\s+(\d+)\s*\|?\s*([\d.,\- –]+)', first_cell)
    if match:
        week_num = int(match.group(1))
        date_part = match.group(2).strip(' |–-')
        year = datetime.date.today().year
        return f"{year}-W{week_num:02d}", date_part
    return None, ''


def call_claude(system_prompt: str, user_message: str) -> str:
    client = openai.OpenAI(
        base_url=os.environ.get('ROUTERAI_BASE_URL', 'https://routerai.ru/api/v1'),
        api_key=os.environ['ROUTERAI_API_KEY'],
    )
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model='deepseek/deepseek-v4-pro',
                max_tokens=16000,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message},
                ],
            )
            content = response.choices[0].message.content
            if not content:
                finish = response.choices[0].finish_reason
                raise RuntimeError(f"Пустой ответ от API (finish_reason={finish})")
            return content
        except Exception as e:
            if attempt < 2:
                print(f"  Ошибка RouterAI API (попытка {attempt + 1}): {e}. Жду 5 сек...")
                time.sleep(5)
            else:
                raise RuntimeError(f"RouterAI API недоступен: {e}")


def archive_current_tasks(ws_tasks: object, ws_archive: object, current_week: str) -> None:
    all_rows = ws_tasks.get_all_values()
    if len(all_rows) <= 1:
        print("  Нет задач для архивирования")
        return

    week_label = [f"Неделя {current_week}"] + [""] * (len(all_rows[0]) - 1)
    task_rows = all_rows[1:]
    rows_to_add = [week_label] + task_rows
    ws_archive.append_rows(rows_to_add)
    print(f"  Архивировано {len(task_rows)} задач")


def get_recent_archive(ws_archive: object, weeks: int = 4) -> str:
    all_values = ws_archive.get_all_values()
    if not all_values:
        return "Архив пуст — это первая неделя работы системы."

    week_indices = []
    for i, row in enumerate(all_values):
        if row and row[0].startswith('Неделя '):
            week_indices.append(i)

    start_idx = week_indices[-weeks] if len(week_indices) >= weeks else 0
    recent_rows = all_values[start_idx:]

    lines = []
    for row in recent_rows:
        if any(row):
            lines.append(" | ".join(row))
    return "\n".join(lines) if lines else "Нет данных в архиве."


def sanitize_tasks(tasks: list) -> list:
    """Постобработка: исправляем устойчивые ошибки модели."""
    nadezhda_fixes = [
        ('скриншот из TravelLine', 'скриншот с сайта'),
        ('в TravelLine', 'на сайте'),
        ('из TravelLine', 'с сайта'),
        ('TravelLine', 'сайте'),
    ]
    upravlyayushchy_fixes = [
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
            for old, new in upravlyayushchy_fixes:
                val = val.replace(old, new)
            task['проверка'] = val
            if 'Виктору' not in task.get('проверка', ''):
                task['проверка'] = 'Фото проблемных мест — Виктору'
        if executor == 'Евгения':
            zadacha = task.get('задача', '').lower()
            if 'добавить' in zadacha and ('заявки' in zadacha or 'заявку' in zadacha):
                task['задача'] = 'Дожать не менее 3 pending-заявок в воронке Bitrix до оплаты'
                task['результат'] = 'Минимум 3 заявки переведены в статус "оплачено" или подтверждено бронирование'
                task['проверка'] = 'Скриншот воронки Bitrix с обновлёнными статусами'
    return tasks


def parse_tasks_json(raw: str) -> list:
    raw = raw.strip()
    start = raw.find('[')
    end = raw.rfind(']') + 1
    if start == -1 or end == 0:
        raise ValueError("JSON-массив не найден в ответе")
    return json.loads(raw[start:end])


def send_telegram_notification(current_week: str, tasks: list, kpi_block: str) -> None:
    bot_token = os.environ.get('MAX_BOT_TOKEN', '')
    owner_id  = os.environ.get('MAX_OWNER_ID', '')
    if not bot_token or not owner_id:
        print("  Telegram-уведомление пропущено: нет MAX_BOT_TOKEN или MAX_OWNER_ID")
        return

    by_person = {}
    for t in tasks:
        name = t.get('исполнитель', 'Неизвестный')
        by_person[name] = by_person.get(name, 0) + 1

    task_lines = "\n".join(f"  {name}: {cnt} задач(и)" for name, cnt in by_person.items())
    # Берём только первые 3 строки KPI для краткости
    kpi_summary = "\n".join(kpi_block.split("\n")[:8])

    text = (
        f"✅ Задачи на неделю {current_week} сформированы\n\n"
        f"{kpi_summary}\n\n"
        f"Задач всего: {len(tasks)}\n{task_lines}"
    )

    try:
        import urllib.request
        data = json.dumps({'chat_id': int(owner_id), 'text': text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=data,
            headers={'Content-Type': 'application/json'},
        )
        urllib.request.urlopen(req, timeout=10)
        print("  Telegram-уведомление отправлено")
    except Exception as e:
        print(f"  Предупреждение: не удалось отправить Telegram-уведомление: {e}")


def main():
    print("=== Агент 2: Стратег ===")
    force = '--force' in sys.argv
    current_week = get_current_week()
    print(f"Текущая неделя: {current_week}" + (" [FORCE]" if force else ""))

    finance_sheet_id = os.environ['FINANCE_SHEET_ID']
    strategy_sheet_id = os.environ['STRATEGY_SHEET_ID']

    print("Подключаюсь к Google Sheets...")
    client_gs = get_client()

    # Идемпотентность
    ws_status = get_worksheet(client_gs, finance_sheet_id, 'Статус системы')
    if not force and get_flag(ws_status, 'задачи_сформированы') == 'да':
        print("Задачи уже сформированы на этой неделе. Выхожу.")
        return

    # Проверяем что дайджест готов
    if not force and get_flag(ws_status, 'дайджест_записан') != 'да':
        print("ПРЕДУПРЕЖДЕНИЕ: Агент 1 ещё не записал дайджест. Запусти сначала agent1_analyst.py")
        sys.exit(1)

    # Читаем KPI-прогресс
    print("Вычисляю прогресс KPI...")
    kpi_block = build_kpi_progress_block(client_gs)
    print(f"  KPI-блок готов ({len(kpi_block)} символов)")

    # Читаем базу знаний
    print("Читаю базу знаний...")
    ws_knowledge = get_worksheet(client_gs, finance_sheet_id, 'База знаний')
    knowledge_rows = ws_knowledge.get_all_values()
    knowledge_base = "\n".join([" ".join(row) for row in knowledge_rows if any(row)])

    # Читаем дайджест
    print("Читаю дайджест от Агента 1...")
    ws_digest = get_worksheet(client_gs, finance_sheet_id, 'Дайджест')
    digest_rows = ws_digest.get_all_values()
    digest_text = '\n'.join(
        ' | '.join(cell.strip() for cell in row if cell.strip())
        for row in digest_rows
        if any(cell.strip() for cell in row)
    ) or "Дайджест пуст."
    print(f"  Дайджест: {len(digest_text)} символов")

    # Определяем неделю данных из заголовка дайджеста
    data_week, data_dates = extract_data_week(digest_rows)
    if data_week:
        print(f"  Неделя данных: {data_week} ({data_dates})")
    else:
        data_week  = current_week
        data_dates = get_week_dates(current_week)
        print(f"  Неделя данных не распознана, использую текущую: {data_week}")

    # Читаем архив
    print("Читаю архив задач...")
    ws_tasks = get_worksheet(client_gs, strategy_sheet_id, 'Задачи недели')
    ws_archive = get_worksheet(client_gs, strategy_sheet_id, 'Архив')
    archive_text = get_recent_archive(ws_archive)

    # Архивируем задачи прошлой недели
    print("Архивирую задачи прошлой недели...")
    archive_current_tasks(ws_tasks, ws_archive, current_week)

    # Очищаем лист задач (оставляем заголовок)
    header = ws_tasks.row_values(1)
    ws_tasks.clear()
    if header:
        ws_tasks.update(values=[header], range_name='A1')

    # Формируем промпт
    system_prompt = build_agent2_system_prompt()
    user_message = f"""ПРОГРЕСС СТРАТЕГИЧЕСКИХ KPI:
{kpi_block}

АРХИВ ЗАДАЧ ПРОШЛЫХ НЕДЕЛЬ:
{archive_text}

ДАЙДЖЕСТ ТЕКУЩЕЙ НЕДЕЛИ:
{digest_text}

ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ (база знаний объекта):
{knowledge_base}

Сформируй задачи для всех 6 исполнителей на неделю {data_week} ({data_dates})."""

    # Вызов LLM (DeepSeek V4 Pro через RouterAI)
    print("Формирую задачи через DeepSeek V4 Pro (RouterAI)...")
    try:
        raw_response = call_claude(system_prompt, user_message)
    except RuntimeError as e:
        print(f"ОШИБКА: Агент 2: ошибка RouterAI API. Нужна ручная постановка задач. Ошибка: {e}")
        sys.exit(1)

    # Парсинг JSON
    print("Парсинг JSON-ответа...")
    try:
        tasks = sanitize_tasks(parse_tasks_json(raw_response))
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
            '',   # Статус — заполняет сотрудник
            '',   # Комментарий — заполняет сотрудник
        ])

    if rows_to_write:
        week_label = f"Неделя {data_week}  |  {data_dates}"
        if not header:
            ws_tasks.update(
                values=[['Исполнитель', 'Блок', 'Задача', 'Результат', 'Как проверить', 'Срок', 'KPI', 'Статус', 'Комментарий']],
                range_name='A1',
            )
        ws_tasks.append_rows([[week_label] + [''] * 8] + rows_to_write)

    set_flag(ws_status, 'задачи_сформированы', 'да')

    # Telegram-уведомление собственнику
    print("Отправляю Telegram-уведомление...")
    send_telegram_notification(data_week, tasks, kpi_block)

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
