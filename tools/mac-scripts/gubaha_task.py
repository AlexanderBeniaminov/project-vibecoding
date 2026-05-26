#!/usr/bin/env python3
"""
gubaha_task.py — Добавляет задачу команде ВК Губаха в Google Sheets.

Использование:
  python3 ~/bin/gubaha_task.py "Виктор" "проверить закупки" "30 мая"
  python3 ~/bin/gubaha_task.py "Надежда" "подготовить отчёт"

Колонки: Исполнитель | Блок | Задача | Результат | Как проверить | Срок
Блок всегда = "Устно"
"""
import sys
import json
from datetime import datetime

SERVICE_ACCOUNT_JSON = "/Users/user/.config/google/personal_service_account.json"
STRATEGY_SHEET_ID = "11eaWcbY1pFMfniACcpZkodJgLOzTRpbXmyejSK9LEQ4"
SHEET_NAME = "Задачи недели"

TEAM_ALIASES = {
    "виктор": "Виктор",
    "евгения": "Евгения",
    "женя": "Евгения",
    "надежда": "Надежда",
    "надя": "Надежда",
    "управляющий": "Управляющий",
    "техдиректор": "Тех.директор",
    "тех.директор": "Тех.директор",
    "технический директор": "Тех.директор",
}


def normalize_executor(name: str) -> str:
    return TEAM_ALIASES.get(name.strip().lower(), name.strip().capitalize())


def add_task(executor: str, task: str, deadline: str = "") -> str:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_JSON,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    executor_clean = normalize_executor(executor)
    row = [executor_clean, "Устно", task, "", "", deadline]

    service.spreadsheets().values().append(
        spreadsheetId=STRATEGY_SHEET_ID,
        range=f"'{SHEET_NAME}'!A:F",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()

    deadline_str = f" (срок: {deadline})" if deadline else ""
    return f"✅ Задача добавлена: {executor_clean} — {task}{deadline_str}"


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Использование: gubaha_task.py <исполнитель> <задача> [срок]")
        sys.exit(1)
    executor = sys.argv[1]
    task = sys.argv[2]
    deadline = sys.argv[3] if len(sys.argv) > 3 else ""
    try:
        print(add_task(executor, task, deadline))
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
