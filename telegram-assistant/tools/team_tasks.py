"""
team_tasks.py — Добавление задач команде ВК Губаха в Google Sheets "Задачи недели".

Spreadsheet: STRATEGY_SHEET_ID из config
Лист: Задачи недели
Колонки: Исполнитель | Блок | Задача | Результат | Как проверить | Срок
"""
from datetime import datetime

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

import config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

TEAM_MEMBERS = {"виктор", "евгения", "надежда", "управляющий", "тех.директор", "техдиректор"}

SHEET_NAME = "Задачи недели"


def _get_service():
    creds = Credentials.from_service_account_file(config.SERVICE_ACCOUNT_JSON, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def add_team_task(
    executor: str,
    task: str,
    deadline: str = "",
    result: str = "",
    how_to_check: str = "",
    block: str = "A",
) -> str:
    """Добавляет строку в конец листа "Задачи недели"."""
    sheet_id = getattr(config, "STRATEGY_SHEET_ID", "")
    if not sheet_id:
        return "Ошибка: STRATEGY_SHEET_ID не задан в config."

    # Нормализуем имя исполнителя
    executor_clean = executor.strip()

    row = [executor_clean, block.upper(), task, result, how_to_check, deadline]

    try:
        service = _get_service()
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"'{SHEET_NAME}'!A:F",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        deadline_str = f" до {deadline}" if deadline else ""
        return f"Задача добавлена: {executor_clean} — {task}{deadline_str}"
    except Exception as e:
        return f"Ошибка записи в Sheets: {e}"
