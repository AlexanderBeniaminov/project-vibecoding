import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
from utils.sheets import get_client, get_worksheet, get_flag
from utils.max_notify import send as max_send
from utils.email_notify import send as email_send

load_dotenv()

FINANCE_SHEET_ID  = os.environ.get('FINANCE_SHEET_ID', '')
STRATEGY_SHEET_ID = os.environ.get('STRATEGY_SHEET_ID', '')
MAX_OWNER_ID      = os.environ.get('MAX_OWNER_ID', '')
VIKTOR_EMAIL      = os.environ.get('VIKTOR_EMAIL', '')


def get_current_week() -> str:
    today = datetime.date.today()
    iso = today.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def notify_owner():
    """Вт 09:00 МСК (из check_digest если задачи готовы) — MAX Александру."""
    client_gs = get_client()
    ws_tasks  = get_worksheet(client_gs, STRATEGY_SHEET_ID, 'Задачи недели')
    all_rows  = ws_tasks.get_all_values()

    by_person = {}
    for row in all_rows[2:]:
        if not any(row):
            continue
        name = row[0] if row else ''
        if name and not name.startswith('Неделя'):
            by_person[name] = by_person.get(name, 0) + 1

    task_lines   = "\n".join(f"  {name}: {cnt} задач(и)" for name, cnt in by_person.items())
    current_week = get_current_week()

    msg = (
        f"✅ Губаха — задачи на {current_week} сформированы\n\n"
        f"Всего задач: {sum(by_person.values())}\n"
        f"{task_lines}\n\n"
        f"Откройте таблицу для проверки."
    )
    max_send(MAX_OWNER_ID, msg)
    print(f"Уведомление (MAX): {sum(by_person.values())} задач по {len(by_person)} исполнителям")


def check_digest():
    """Вт 09:00 МСК — проверить дайджест и задачи.
    Нет дайджеста → MAX Александру + email Виктору.
    Задачи готовы → MAX Александру: сводка.
    """
    client_gs = get_client()
    ws_status = get_worksheet(client_gs, FINANCE_SHEET_ID, 'Статус системы')
    current_week = get_current_week()

    digest_ok = get_flag(ws_status, 'дайджест_записан') == 'да'
    tasks_ok  = get_flag(ws_status, 'задачи_сформированы') == 'да'

    if not digest_ok:
        max_send(MAX_OWNER_ID,
            f"🚨 Губаха {current_week} — дайджест не сформирован!\n"
            f"Агент 1 не отработал. Задачи команды НЕ будут сформированы автоматически."
        )
        if VIKTOR_EMAIL:
            email_send(
                VIKTOR_EMAIL,
                f"Губаха {current_week} — дайджест не сформирован",
                f"Губаха, {current_week}\n\n"
                f"Агент 1 не смог сформировать дайджест — данные не были внесены "
                f"в лист «2026» до 22:00 МСК.\n\n"
                f"Пожалуйста, внесите данные. "
                f"После этого запустите Агента 1 вручную через GitHub Actions.",
            )
        print("Дайджест не сформирован — MAX Александру + email Виктору")
        return

    if tasks_ok:
        notify_owner()
    else:
        max_send(MAX_OWNER_ID,
            f"⚠️ Губаха {current_week} — дайджест готов, но задачи ещё не сформированы.\n"
            f"Проверьте запуск Агента 2."
        )
        print("Задачи не сформированы — предупреждение MAX Александру")


def remind():
    """Пн 15:00 МСК — email Виктору: внести данные до 22:00."""
    today   = datetime.date.today()
    weekday = today.weekday()  # 0=пн

    if weekday == 0:
        _remind_data_missing()
    else:
        print(f"Remind: день {weekday}, действие не задано.")


def _remind_data_missing():
    """Только email Виктору с напоминанием внести данные до 22:00."""
    current_week = get_current_week()
    if VIKTOR_EMAIL:
        email_send(
            VIKTOR_EMAIL,
            f"Губаха {current_week} — внесите данные сегодня до 22:00",
            f"Губаха, {current_week}\n\n"
            f"Напоминание: пожалуйста внесите данные прошедшей недели "
            f"в лист «2026» финансовой таблицы до 22:00 МСК.\n\n"
            f"Строки 54–82: NPS, отзывы, остатки, ремонт, уборки, ФОТ.\n\n"
            f"После заполнения система автоматически отправит подтверждение.",
        )
        print("Напоминание Пн 15:00: email → Виктор")
    else:
        print("Напоминание Пн: VIKTOR_EMAIL не задан, пропуск")


def main():
    if len(sys.argv) < 2:
        print("Использование: python agents/agent3_dispatcher.py <mode>")
        print("Режимы: check_digest | remind | notify_owner")
        sys.exit(1)

    mode = sys.argv[1]
    print(f"=== Агент 3: Диспетчер [{mode}] ===")

    if not FINANCE_SHEET_ID or not STRATEGY_SHEET_ID:
        print("ОШИБКА: FINANCE_SHEET_ID или STRATEGY_SHEET_ID не задан")
        sys.exit(1)

    if mode == 'check_digest':
        check_digest()
    elif mode == 'remind':
        remind()
    elif mode == 'notify_owner':
        notify_owner()
    else:
        print(f"ОШИБКА: Неизвестный режим: {mode}")
        sys.exit(1)

    print(f"=== Агент 3 [{mode}] завершил работу ===")


if __name__ == '__main__':
    main()
