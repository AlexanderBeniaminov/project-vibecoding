#!/usr/bin/env python3
"""
Разовый скрипт: перемещает колонку 2026-06-01 на правильную позицию
между 2026-05-31 и 2026-06-02 в листе «Ежедневно».
"""
import json
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = "1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI"
SHEET_GID = 1392722568
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

TARGET_DATE  = "2026-06-01"
ANCHOR_DATE  = "2026-05-31"


def main():
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if creds_json:
        info  = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        path  = os.path.join(os.path.dirname(__file__), "credentials.json")
        creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)

    service = build("sheets", "v4", credentials=creds)
    sheets  = service.spreadsheets()

    result = sheets.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="Ежедневно!1:1",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    row1 = result.get("values", [[]])[0]

    col_target = None
    col_after_anchor = None

    for i, cell in enumerate(row1):
        s = str(cell).strip()
        if s == ANCHOR_DATE:
            col_after_anchor = i + 1  # позиция сразу ПОСЛЕ якоря (вставить сюда)
        if s == TARGET_DATE:
            col_target = i

    if col_target is None:
        print(f"ERROR: колонка {TARGET_DATE} не найдена в строке 1")
        sys.exit(1)
    if col_after_anchor is None:
        print(f"ERROR: колонка {ANCHOR_DATE} не найдена в строке 1")
        sys.exit(1)

    print(f"{TARGET_DATE}: текущий индекс {col_target}  →  нужный {col_after_anchor}")

    if col_target == col_after_anchor:
        print("Колонка уже на правильном месте.")
        return

    sheets.batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{
            "moveDimension": {
                "source": {
                    "sheetId":    SHEET_GID,
                    "dimension":  "COLUMNS",
                    "startIndex": col_target,
                    "endIndex":   col_target + 1,
                },
                "destinationIndex": col_after_anchor,
            }
        }]},
    ).execute()

    print(f"✅ Колонка {TARGET_DATE} перемещена на позицию {col_after_anchor + 1}")


if __name__ == "__main__":
    main()
