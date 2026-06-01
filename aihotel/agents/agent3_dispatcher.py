import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
from utils.sheets import get_client, get_worksheet, get_flag
from utils.telegram import send as tg_send
from utils.email_notify import send as email_send

load_dotenv()

FINANCE_SHEET_ID    = os.environ.get('FINANCE_SHEET_ID', '')
STRATEGY_SHEET_ID   = os.environ.get('STRATEGY_SHEET_ID', '')
MAX_BOT_TOKEN       = os.environ.get('MAX_BOT_TOKEN', '')
MAX_OWNER_ID        = os.environ.get('MAX_OWNER_ID', '')
VIKTOR_EMAIL        = os.environ.get('VIKTOR_EMAIL', '')


def get_current_week() -> str:
    today = datetime.date.today()
    iso = today.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def notify_owner():
    """Вт 04:00 UTC — уведомить собственника (MAX) что задачи на неделю готовы."""
    client_gs = get_client()
    ws_status = get_worksheet(client_gs, FINANCE_SHEET_ID, 'Статус системы')

    if get_flag(ws_status, 'задачи_сформированы') != 'да':
        msg = "⚠️ Губаха — задачи недели ещё не сформированы. Проверьте запуск Агента 2."
        tg_send(MAX_BOT_TOKEN, MAX_OWNER_ID, msg)
        print("Задачи не сформированы — уведомление собственнику отправлено")
        return

    ws_tasks = get_worksheet(client_gs, STRATEGY_SHEET_ID, 'Задачи недели')
    all_rows = ws_tasks.get_all_values()

    by_person = {}
    for row in all_rows[2:]:  # пропускаем заголовок и метку недели
        if not any(row):
            continue
        name = row[0] if row else ''
        if name and not name.startswith('Неделя'):
            by_person[name] = by_person.get(name, 0) + 1

    task_lines = "\n".join(f"  {name}: {cnt} задач(и)" for name, cnt in by_person.items())
    current_week = get_current_week()

    msg = (
        f"✅ Губаха — задачи на {current_week} сформированы\n\n"
        f"Всего задач: {sum(by_person.values())}\n"
        f"{task_lines}\n\n"
        f"Откройте таблицу для проверки."
    )
    tg_send(MAX_BOT_TOKEN, MAX_OWNER_ID, msg)
    print(f"Уведомление собственнику (MAX): {sum(by_person.values())} задач по {len(by_person)} исполнителям")


def check_digest():
    """Вт 09:00 МСК — проверить что дайджест сформирован.
    Если нет — email Виктору + Telegram Александру.
    """
    client_gs = get_client()
    ws_status = get_worksheet(client_gs, FINANCE_SHEET_ID, 'Статус системы')
    current_week = get_current_week()

    if get_flag(ws_status, 'дайджест_записан') == 'да':
        print("Дайджест записан — всё в порядке.")
        return

    msg_tg = (
        f"🚨 Губаха {current_week} — дайджест не сформирован!\n"
        f"Агент 1 не отработал (данные не внесены или ошибка).\n"
        f"Агент 2 не запустится — задачи не будут сформированы."
    )
    tg_send(MAX_BOT_TOKEN, MAX_OWNER_ID, msg_tg)

    if VIKTOR_EMAIL:
        email_send(
            VIKTOR_EMAIL,
            f"Губаха {current_week} — дайджест не сформирован",
            f"Губаха, {current_week}\n\n"
            f"Агент 1 не смог сформировать дайджест — данные не были внесены "
            f"в лист «2026» до 22:00 МСК.\n\n"
            f"Пожалуйста, внесите данные вручную. "
            f"После этого запустите Агента 1 вручную через GitHub Actions.",
        )
    print(f"Дайджест не сформирован — MAX Александру + email Виктору")


def send_tasks():
    """Вт 06:00-14:00 UTC (5 попыток) — проверить что задачи сформированы.
    Если нет — предупредить собственника через MAX.
    """
    client_gs = get_client()
    ws_status = get_worksheet(client_gs, FINANCE_SHEET_ID, 'Статус системы')

    if get_flag(ws_status, 'задачи_сформированы') == 'да':
        print("Задачи сформированы — повторное уведомление не нужно.")
        return

    current_week = get_current_week()
    msg = (
        f"⚠️ Губаха {current_week} — задачи ещё не записаны в таблицу.\n"
        f"Проверьте запуск Агента 2."
    )
    tg_send(MAX_BOT_TOKEN, MAX_OWNER_ID, msg)
    print("Задачи не сформированы — напоминание отправлено через MAX")


def remind():
    """Напоминания в зависимости от дня недели.
    Пн 12:00 UTC → Виктору (Telegram + email): внести данные до дедлайна.
    Чт 09:00 UTC → собственнику (MAX): обновить статусы задач.
    """
    today = datetime.date.today()
    weekday = today.weekday()  # 0=пн, 3=чт

    if weekday == 0:  # Понедельник
        _remind_data_missing()
    elif weekday == 3:  # Четверг
        _remind_update_statuses()
    else:
        print(f"Remind: день {weekday}, действие не задано.")


def _remind_data_missing():
    """Понедельник — напомнить Виктору (Telegram) и Александру (MAX) о дедлайне."""
    current_week = get_current_week()

    # Александр узнаёт что дедлайн сегодня — через MAX
    tg_send(MAX_BOT_TOKEN, MAX_OWNER_ID,
        f"📋 Губаха {current_week} — сегодня дедлайн внесения данных (до 22:00 МСК)."
    )

    # Виктор — только email (karpenko@entens.ru)
    if VIKTOR_EMAIL:
        email_send(
            VIKTOR_EMAIL,
            f"Губаха {current_week} — внесите данные сегодня до 22:00",
            f"Губаха, {current_week}\n\n"
            f"Напоминание: пожалуйста внесите данные прошедшей недели "
            f"в лист «2026» финансовой таблицы до 22:00 МСК.\n\n"
            f"После этого Агент 1 автоматически проведёт анализ.",
        )
    print("Напоминание Пн: Виктор (email), Александр (MAX)")


def _remind_update_statuses():
    """Четверг — напомнить Александру (MAX) обновить статусы задач."""
    try:
        client_gs = get_client()
        ws_tasks = get_worksheet(client_gs, STRATEGY_SHEET_ID, 'Задачи недели')
        all_rows = ws_tasks.get_all_values()

        empty_status, total = 0, 0
        for row in all_rows[2:]:
            if not any(row) or (row[0] and row[0].startswith('Неделя')):
                continue
            total += 1
            status = row[7] if len(row) > 7 else ''
            if not status.strip():
                empty_status += 1
    except Exception as e:
        print(f"  Предупреждение: не удалось прочитать задачи: {e}")
        empty_status, total = 0, 0

    if total == 0:
        print("Напоминание Чт: нет задач в листе — пропускаем.")
        return

    msg = (
        f"🔔 Губаха — середина недели.\n"
        f"Попросите команду обновить статусы задач в таблице.\n"
        f"Без статуса: {empty_status} из {total} задач."
    )
    tg_send(MAX_BOT_TOKEN, MAX_OWNER_ID, msg)
    print(f"Напоминание Чт: {empty_status}/{total} без статуса")


def main():
    if len(sys.argv) < 2:
        print("Использование: python agents/agent3_dispatcher.py <mode>")
        print("Режимы: notify_owner | send_tasks | remind")
        sys.exit(1)

    mode = sys.argv[1]
    print(f"=== Агент 3: Диспетчер [{mode}] ===")

    if not FINANCE_SHEET_ID or not STRATEGY_SHEET_ID:
        print("ОШИБКА: FINANCE_SHEET_ID или STRATEGY_SHEET_ID не задан")
        sys.exit(1)

    if mode == 'notify_owner':
        notify_owner()
    elif mode == 'check_digest':
        check_digest()
    elif mode == 'send_tasks':
        send_tasks()
    elif mode == 'remind':
        remind()
    else:
        print(f"ОШИБКА: Неизвестный режим: {mode}")
        sys.exit(1)

    print(f"=== Агент 3 [{mode}] завершил работу ===")


if __name__ == '__main__':
    main()
