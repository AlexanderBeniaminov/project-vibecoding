#!/usr/bin/env python3
"""
project_notes.py — Запись мыслей/идей/планов по проектам в Google Sheets.

Использование:
  python3 ~/bin/project_notes.py "губаха" "нужно добавить онлайн-бронирование хостелов"
  python3 ~/bin/project_notes.py "юникорн" "идея: геймификация онбординга"
  python3 ~/bin/project_notes.py "прочее" "в офисе нужен ремонт в марте"
"""
import sys
from datetime import datetime
from pathlib import Path

SA_PATH = "/Users/user/.config/google/personal_service_account.json"
SHEET_ID = "1aiCKUs-Le-adHSfAOOC2AHRs1vCWzm-E3lucPTbRRkc"

# Нормализация названия проекта
PROJECT_MAP = {
    "губаха": "Губаха",
    "гб": "Губаха",
    "отель": "Губаха",
    "курорт": "Губаха",
    "юникорн": "Юникорн",
    "unicorn": "Юникорн",
    "рог": "Юникорн",
    "прочее": "Прочее",
    "офис": "Прочее",
    "разное": "Прочее",
    "общее": "Прочее",
}


def normalize_project(name: str) -> str:
    key = name.strip().lower()
    if key in PROJECT_MAP:
        return PROJECT_MAP[key]
    # Частичное совпадение
    for k, v in PROJECT_MAP.items():
        if k in key or key in k:
            return v
    # Capitalise как есть — новый проект
    return name.strip().capitalize()


def save(project_raw: str, text: str) -> str:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    project = normalize_project(project_raw)
    now = datetime.now()
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M")

    creds = Credentials.from_service_account_file(
        SA_PATH, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Проверяем — есть ли лист с таким проектом
    meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    existing = [s["properties"]["title"] for s in meta["sheets"]]

    if project not in existing:
        # Создаём новый лист
        svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={
            "requests": [{"addSheet": {"properties": {"title": project}}}]
        }).execute()
        svc.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=f"'{project}'!A1:C1",
            valueInputOption="USER_ENTERED",
            body={"values": [["Дата", "Время", "Мысль / Идея / План"]]}
        ).execute()

    # Добавляем строку
    svc.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=f"'{project}'!A:C",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [[date_str, time_str, text.strip()]]}
    ).execute()

    return f"✅ Записано в «{project}»:\n{text.strip()}"


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    try:
        print(save(sys.argv[1], sys.argv[2]))
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
