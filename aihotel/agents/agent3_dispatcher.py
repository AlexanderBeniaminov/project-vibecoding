import os
import sys
import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.sheets import get_client, get_worksheet, get_flag, set_flag
from utils import max_bot
from utils.prompts import build_owner_notify_message, build_task_message, build_remind_message

load_dotenv()

# URL стратегической таблицы для ссылок в сообщениях
STRATEGY_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{os.environ.get('STRATEGY_SHEET_ID', 'ID')}/edit"


def get_current_week() -> str:
    today = datetime.date.today()
    iso = today.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def get_week_label() -> str:
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return f"{monday.strftime('%-d')}–{sunday.strftime('%-d %B')}"


def get_team_ids() -> list:
    raw = os.environ.get('MAX_TEAM_IDS', '')
    return [x.strip() for x in raw.split(',') if x.strip()]


def mode_notify_owner(client_gs, ws_status):
    """Отправляет собственнику ссылку на задачи для утверждения."""
    print("Режим: notify_owner")

    if get_flag(ws_status, 'задачи_сформированы') != 'да':
        print("Задачи ещё не сформированы (Агент 2 не запущен). Выхожу.")
        return

    strategy_sheet_id = os.environ['STRATEGY_SHEET_ID']
    ws_tasks = get_worksheet(client_gs, strategy_sheet_id, 'Задачи недели')
    tasks = ws_tasks.get_all_records()

    if not tasks:
        print("Лист задач пуст. Выхожу.")
        return

    # Краткая сводка
    by_person = {}
    for t in tasks:
        name = t.get('Исполнитель', 'Неизвестный')
        by_person[name] = by_person.get(name, 0) + 1

    summary_lines = []
    for name, count in by_person.items():
        summary_lines.append(f"  • {name}: {count} задач(и)")
    summary = "\n".join(summary_lines)

    message = build_owner_notify_message(summary, STRATEGY_SHEET_URL)
    ok = max_bot.send_owner(message)

    if ok:
        print("✅ Уведомление собственнику отправлено")
    else:
        print("❌ Ошибка отправки собственнику")


def mode_send_tasks(client_gs, ws_status):
    """Отправляет задачи исполнителям — только если собственник утвердил."""
    print("Режим: send_tasks")

    # Идемпотентность — не отправлять дважды
    if get_flag(ws_status, 'задачи_отправлены') == 'да':
        print("Задачи уже отправлены на этой неделе. Выхожу.")
        return

    # Проверяем утверждение
    if get_flag(ws_status, 'задачи_утверждены') != 'да':
        print("Утверждение ещё не получено. Ждём следующей проверки.")
        return

    strategy_sheet_id = os.environ['STRATEGY_SHEET_ID']
    ws_tasks = get_worksheet(client_gs, strategy_sheet_id, 'Задачи недели')
    tasks = ws_tasks.get_all_records()

    if not tasks:
        print("Лист задач пуст. Выхожу.")
        return

    # Группируем задачи по исполнителю
    tasks_by_person = {}
    for task in tasks:
        name = task.get('Исполнитель', '')
        if name not in tasks_by_person:
            tasks_by_person[name] = []
        tasks_by_person[name].append(task)

    team_ids = get_team_ids()
    team_names = list(tasks_by_person.keys())
    week_label = get_week_label()

    if len(team_ids) != len(team_names):
        print(f"ПРЕДУПРЕЖДЕНИЕ: {len(team_ids)} ID в MAX_TEAM_IDS, но {len(team_names)} исполнителей в таблице")
        print(f"Исполнители в таблице: {team_names}")
        print("Проверь порядок MAX_TEAM_IDS в .env")

    # Отправка
    print(f"Отправляю задачи {len(team_names)} исполнителям...")
    for i, name in enumerate(team_names):
        if i >= len(team_ids):
            print(f"  ПРОПУСК {name}: нет MAX ID (проверь MAX_TEAM_IDS)")
            continue

        person_tasks = tasks_by_person[name]
        user_id = team_ids[i]
        message = build_task_message(name, person_tasks, STRATEGY_SHEET_URL, week_label)
        ok = max_bot.send_message(user_id, message)
        status = "✅" if ok else "❌"
        print(f"  {status} {name} (ID {user_id}): {len(person_tasks)} задач(и)")

    set_flag(ws_status, 'задачи_отправлены', 'да')
    print("\n✅ Рассылка завершена")


def mode_remind(client_gs, ws_status):
    """Напоминание тем, кто не заполнил статусы."""
    print("Режим: remind")

    strategy_sheet_id = os.environ['STRATEGY_SHEET_ID']
    ws_statuses = get_worksheet(client_gs, strategy_sheet_id, 'Статусы')
    statuses = ws_statuses.get_all_records()

    if not statuses:
        print("Лист статусов пуст. Выхожу.")
        return

    # Кто не заполнил
    team_ids = get_team_ids()
    ws_tasks = get_worksheet(client_gs, strategy_sheet_id, 'Задачи недели')
    tasks = ws_tasks.get_all_records()
    team_names = list({t.get('Исполнитель', '') for t in tasks if t.get('Исполнитель')})

    # Кто из тех, у кого есть задачи, не заполнил статус
    filled = set()
    for row in statuses:
        status = str(row.get('Статус', '')).strip()
        name = str(row.get('Исполнитель', '')).strip()
        if status and status != '' and name:
            filled.add(name)

    not_filled = [name for name in team_names if name not in filled]

    if not not_filled:
        print("Все заполнили статусы. Напоминания не нужны.")
        return

    print(f"Отправляю напоминания: {not_filled}")
    for i, name in enumerate(team_names):
        if name not in not_filled:
            continue
        if i >= len(team_ids):
            print(f"  ПРОПУСК {name}: нет MAX ID")
            continue
        user_id = team_ids[i]
        message = build_remind_message(name, STRATEGY_SHEET_URL)
        ok = max_bot.send_message(user_id, message)
        print(f"  {'✅' if ok else '❌'} {name}")

    print(f"\n✅ Напоминания отправлены: {len(not_filled)} человек")


def main():
    if len(sys.argv) < 2:
        print("Использование: python agent3_dispatcher.py [notify_owner | send_tasks | remind]")
        sys.exit(1)

    mode = sys.argv[1]
    print(f"=== Агент 3: Диспетчер (режим: {mode}) ===")

    finance_sheet_id = os.environ['FINANCE_SHEET_ID']
    print("Подключаюсь к Google Sheets...")
    client_gs = get_client()
    ws_status = get_worksheet(client_gs, finance_sheet_id, 'Статус системы')

    if mode == 'notify_owner':
        mode_notify_owner(client_gs, ws_status)
    elif mode == 'send_tasks':
        mode_send_tasks(client_gs, ws_status)
    elif mode == 'remind':
        mode_remind(client_gs, ws_status)
    else:
        print(f"Неизвестный режим: {mode}")
        sys.exit(1)


if __name__ == '__main__':
    main()
