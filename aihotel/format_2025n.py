#!/usr/bin/env python3
"""
Применяет форматирование к листу "2025н":
  - Цвета и шрифты заголовков разделов (из листа "Новая структура")
  - Числовой формат #,##0 для рублёвых/счётных ячеек
  - Процентный формат 0% для процентных ячеек
  - RevPAR и RevPAC — целые числа #,##0
  - Средняя длительность пребывания — 1 знак #,##0.0
"""
import json
import re

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import gspread

# ---------------------------------------------------------------------------
# Константы форматирования (сняты с листа "Новая структура")
# ---------------------------------------------------------------------------

# Заголовки разделов: (row_1based, bg_rgb, font_size)
# A1:AF1  — год/недели, шрифт 16, тёмно-синий
# B2:AF2  — даты, шрифт 16, тёмно-синий (A2 — белый)
# A3:AF3  и т.д. — разделы, шрифт 14

SECTION_HEADERS = [
    # (row_1based, start_col_0based, end_col_exclusive, r, g, b, font_size)
    (1,  0, 32, 0.129, 0.286, 0.529, 16),   # год + недели — вся строка
    (2,  1, 32, 0.129, 0.286, 0.529, 16),   # даты — B2:AF2 (A2 белый)
    (3,  0, 32, 0.129, 0.486, 0.267, 14),   # 💰 ДОХОДЫ
    (20, 0, 32, 0.129, 0.298, 0.647, 14),   # 📊 ЗАГРУЗКА И ПРОДАЖИ
    (39, 0, 32, 0.349, 0.200, 0.600, 14),   # 👥 СЕГМЕНТЫ ГОСТЕЙ
    (53, 0, 32, 1.000, 0.498, 0.549, 14),   # ⭐ КАЧЕСТВО СЕРВИСА
    (61, 0, 32, 0.349, 0.420, 0.549, 14),   # ⚙️ ОПЕРАЦИИ И ДЕНЬГИ
]

# Числовые форматы для ДАННЫХ колонок (C=2 ... AF=31)
DATA_COL_START = 2   # col C (0-based)
DATA_COL_END   = 32  # до AF включительно

# Строки с процентами — формат "0%"
PERCENT_ROWS = {6, 9, 13, 15, 22, 28, 29, 30, 32, 33, 37, 38, 54, 57, 60, 78}

# Строки с числами/рублями — формат "#,##0"
NUMBER_ROWS = {
    4, 5, 7, 8,
    11, 12, 14,
    17, 18, 19,
    21, 23, 24, 25,
    35, 36,
    40, 41, 42,
    44, 45, 46,
    48, 49,
    51, 52,
    56, 59,
    62, 63, 65, 66,
    68, 69, 70,
    72, 73, 74,
    76, 77,
    80, 81, 82,
}

# Строка с дробными числами — формат "#,##0.0"
DECIMAL_ROWS = {27}  # Ср. пребывание в коттеджах (дней)


def make_color(r, g, b):
    return {"red": r, "green": g, "blue": b}


def repeat_cell_request(sheet_gid, row0, col_start, col_end, cell_fmt, fields):
    """repeatCell request для одной строки."""
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_gid,
                "startRowIndex": row0,
                "endRowIndex": row0 + 1,
                "startColumnIndex": col_start,
                "endColumnIndex": col_end,
            },
            "cell": {"userEnteredFormat": cell_fmt},
            "fields": fields,
        }
    }


def main():
    with open(".env") as f:
        env = f.read()

    creds_info = json.loads(
        re.search(r"GOOGLE_CREDS_JSON=(.*?)(?=\n[A-Z_]+=|\Z)", env, re.DOTALL).group(1).strip()
    )
    sheet_id = re.search(r"FINANCE_SHEET_ID=(.+)", env).group(1).strip()

    creds = Credentials.from_service_account_info(
        creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    service = build("sheets", "v4", credentials=creds)
    client  = gspread.Client(auth=creds)

    ss = client.open_by_key(sheet_id)
    ws_new = ss.worksheet("2025н")
    gid = ws_new.id
    print(f"Лист '2025н', gid={gid}")

    requests = []

    # -----------------------------------------------------------------------
    # 1. Заголовки разделов: фон + белый жирный текст
    # -----------------------------------------------------------------------
    for (row1, col_start, col_end, r, g, b, fs) in SECTION_HEADERS:
        cell_fmt = {
            "backgroundColor": make_color(r, g, b),
            "textFormat": {
                "bold": True,
                "fontSize": fs,
                "foregroundColorStyle": {"rgbColor": make_color(1, 1, 1)},
            },
        }
        requests.append(
            repeat_cell_request(
                gid, row1 - 1, col_start, col_end,
                cell_fmt,
                "userEnteredFormat(backgroundColor,textFormat(bold,fontSize,foregroundColorStyle))",
            )
        )

    # -----------------------------------------------------------------------
    # 2. Числовые форматы для данных (колонки C–AF)
    # -----------------------------------------------------------------------
    for row1 in PERCENT_ROWS:
        cell_fmt = {"numberFormat": {"type": "PERCENT", "pattern": "0%"}}
        requests.append(
            repeat_cell_request(
                gid, row1 - 1, DATA_COL_START, DATA_COL_END,
                cell_fmt, "userEnteredFormat.numberFormat",
            )
        )

    for row1 in NUMBER_ROWS:
        cell_fmt = {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}}
        requests.append(
            repeat_cell_request(
                gid, row1 - 1, DATA_COL_START, DATA_COL_END,
                cell_fmt, "userEnteredFormat.numberFormat",
            )
        )

    for row1 in DECIMAL_ROWS:
        cell_fmt = {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.0"}}
        requests.append(
            repeat_cell_request(
                gid, row1 - 1, DATA_COL_START, DATA_COL_END,
                cell_fmt, "userEnteredFormat.numberFormat",
            )
        )

    # -----------------------------------------------------------------------
    # 3. Выполняем все изменения одним батчем
    # -----------------------------------------------------------------------
    print(f"Отправляю {len(requests)} запросов форматирования...")
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": requests},
    ).execute()
    print("Форматирование применено.")

    # -----------------------------------------------------------------------
    # 4. Быстрая верификация: читаем форматирование нескольких ячеек
    # -----------------------------------------------------------------------
    check = service.spreadsheets().get(
        spreadsheetId=sheet_id,
        ranges=["'2025н'!A1:AF82"],
        fields="sheets(data(rowData(values(userEnteredFormat(backgroundColor,numberFormat)))))",
    ).execute()

    rows = check["sheets"][0]["data"][0]["rowData"]

    def get_fmt(row_idx, col_idx):
        try:
            return rows[row_idx]["values"][col_idx].get("userEnteredFormat", {})
        except (IndexError, KeyError):
            return {}

    print("\n=== ПРОВЕРКА ФОРМАТИРОВАНИЯ ===")
    tests = [
        (1,  0, "Строка 1  A1  (фон тёмно-синий)"),
        (2,  1, "Строка 2  B2  (фон тёмно-синий)"),
        (3,  0, "Строка 3  A3  (фон тёмно-зелёный)"),
        (20, 0, "Строка 20 A20 (фон средне-синий)"),
        (39, 0, "Строка 39 A39 (фон фиолетовый)"),
        (53, 0, "Строка 53 A53 (фон розовый)"),
        (61, 0, "Строка 61 A61 (фон серо-синий)"),
        (5,  2, "Строка 5  C5  (Доход, #,##0)"),
        (23, 2, "Строка 23 C23 (ADR, #,##0)"),
        (24, 2, "Строка 24 C24 (RevPAR, #,##0)"),
        (25, 2, "Строка 25 C25 (RevPAC, #,##0)"),
        (6,  2, "Строка 6  C6  (% плана, 0%)"),
        (28, 2, "Строка 28 C28 (загрузка, 0%)"),
        (27, 2, "Строка 27 C27 (дни, #,##0.0)"),
    ]
    for (r1, c0, label) in tests:
        fmt = get_fmt(r1 - 1, c0)
        bg  = fmt.get("backgroundColor", {})
        nf  = fmt.get("numberFormat", {})
        bg_str = f"({bg.get('red',1):.2f},{bg.get('green',1):.2f},{bg.get('blue',1):.2f})"
        nf_str = nf.get("pattern", "—")
        print(f"  {label}: bg={bg_str} nf='{nf_str}'")


if __name__ == "__main__":
    main()
