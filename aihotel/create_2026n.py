#!/usr/bin/env python3
"""
Создаёт лист "2026н" в финансовой таблице aihotel.
Структура строк (82 строки) — из листа "Новая структура".
Данные — из листа "2026" (недели 1–16).
RevPAR и RevPAC — формулы.
Форматирование — цвета, числа, проценты (идентично "2025н").
"""
import json
import re
import time

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ---------------------------------------------------------------------------
# Параметры
# ---------------------------------------------------------------------------
SOURCE_SHEET  = "2026"
NEW_SHEET     = "2026н"
YEAR_LABEL    = "2026"
WEEK_MIN, WEEK_MAX = 1, 52  # диапазон допустимых номеров недель

# ---------------------------------------------------------------------------
# Маппинг: строка "Новая структура" (1-based) → строка источника (1-based)
# ---------------------------------------------------------------------------
MAPPING = {
    4:  5,    5:  6,    6:  8,    7:  9,    8:  10,   9:  11,
    11: 13,   12: 14,   13: 17,   14: 27,   15: 29,
    17: 23,   18: 24,   19: 25,
    21: 55,   22: 56,   23: 45,
    24: "REVPAR",   # = ADR (стр.23) × Загрузка коттеджей (стр.28)
    25: "REVPAC",   # = Доход (стр.5) / Гостей (стр.21)
    27: 48,   28: 47,   29: 49,   30: 51,
    32: 53,   33: 64,
    35: 40,   36: 41,   37: 42,   38: 43,
    40: 67,   41: 69,   42: 70,
    44: 77,   45: 79,   46: 80,
    48: 72,   49: 75,
    51: 82,   52: 85,
    54: 58,   56: 59,   57: 60,   59: 61,   60: 62,
    62: 33,   63: 34,   65: 31,   66: 32,
    68: 88,   69: 89,   70: 90,
    72: 92,   73: 93,   74: 94,
    76: 97,   77: 98,   78: 99,
    80: 101,  81: 102,  82: 103,
}

# ---------------------------------------------------------------------------
# Форматирование (идентично "2025н")
# ---------------------------------------------------------------------------
SECTION_HEADERS = [
    # (row_1based, col_start_0based, r, g, b, font_size)
    (1,  0, 0.129, 0.286, 0.529, 16),
    (2,  1, 0.129, 0.286, 0.529, 16),
    (3,  0, 0.129, 0.486, 0.267, 14),
    (20, 0, 0.129, 0.298, 0.647, 14),
    (39, 0, 0.349, 0.200, 0.600, 14),
    (53, 0, 1.000, 0.498, 0.549, 14),
    (61, 0, 0.349, 0.420, 0.549, 14),
]
PERCENT_ROWS = {6, 9, 13, 15, 22, 28, 29, 30, 32, 33, 37, 38, 54, 57, 60, 78}
NUMBER_ROWS  = {
    4, 5, 7, 8, 11, 12, 14, 17, 18, 19, 21, 23, 24, 25, 35, 36,
    40, 41, 42, 44, 45, 46, 48, 49, 51, 52, 56, 59,
    62, 63, 65, 66, 68, 69, 70, 72, 73, 74, 76, 77, 80, 81, 82,
}
DECIMAL_ROWS = {27}


def col_letter(n: int) -> str:
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def clean(v: str) -> str:
    return v.replace("\xa0", "").strip()


def make_color(r, g, b):
    return {"red": r, "green": g, "blue": b}


def repeat_cell(gid, row0, col_start, col_end, cell_fmt, fields):
    return {
        "repeatCell": {
            "range": {
                "sheetId": gid,
                "startRowIndex": row0, "endRowIndex": row0 + 1,
                "startColumnIndex": col_start, "endColumnIndex": col_end,
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

    creds   = Credentials.from_service_account_info(
        creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client  = gspread.Client(auth=creds)
    service = build("sheets", "v4", credentials=creds)
    ss      = client.open_by_key(sheet_id)

    # --- Чтение источников ---
    novstr = ss.worksheet("Новая структура").get_all_values()   # 82 × 3
    src    = ss.worksheet(SOURCE_SHEET).get_all_values()        # 105 × N

    # Определяем столбцы недель (строка 2)
    week_cols = {}
    for ci, v in enumerate(src[1]):
        s = v.strip()
        if s.isdigit():
            wn = int(s)
            if WEEK_MIN <= wn <= WEEK_MAX:
                week_cols[wn] = ci

    weeks = sorted(week_cols.keys())
    print(f"Источник: '{SOURCE_SHEET}', найдено недель: {weeks}")

    # Даты (строка 3)
    week_dates = {
        wn: clean(src[2][ci]) if ci < len(src[2]) else ""
        for wn, ci in week_cols.items()
    }

    # --- Удаляем старый лист, если есть ---
    try:
        ss.del_worksheet(ss.worksheet(NEW_SHEET))
        print(f"Удалён старый лист '{NEW_SHEET}'")
        time.sleep(1)
    except gspread.WorksheetNotFound:
        pass

    total_cols = 2 + len(weeks)
    ws_new = ss.add_worksheet(title=NEW_SHEET, rows=82, cols=total_cols)
    print(f"Создан лист '{NEW_SHEET}' (82 × {total_cols})")
    time.sleep(1)

    # --- Строим матрицу данных ---
    rows_out = []
    for ri in range(82):
        row_num = ri + 1
        ns  = novstr[ri]
        row = [""] * total_cols
        row[0] = ns[0]
        row[1] = ns[1]

        if row_num == 1:
            row[0] = YEAR_LABEL
            row[1] = "Неделя"
            for i, wn in enumerate(weeks):
                row[2 + i] = str(wn)
            rows_out.append(row)
            continue

        if row_num == 2:
            row[1] = "Даты"
            for i, wn in enumerate(weeks):
                row[2 + i] = week_dates.get(wn, "")
            rows_out.append(row)
            continue

        source = MAPPING.get(row_num)

        if source == "REVPAR":
            for i in range(len(weeks)):
                c = col_letter(3 + i)
                row[2 + i] = f"={c}23*{c}28"

        elif source == "REVPAC":
            for i in range(len(weeks)):
                c = col_letter(3 + i)
                row[2 + i] = f'=IFERROR({c}5/{c}21;"")'

        elif isinstance(source, int):
            src_row = src[source - 1]
            for i, wn in enumerate(weeks):
                ci = week_cols.get(wn)
                if ci is not None and ci < len(src_row):
                    row[2 + i] = clean(src_row[ci])

        rows_out.append(row)

    print("Записываю данные...")
    ws_new.update(range_name="A1", values=rows_out, value_input_option="USER_ENTERED")
    print("Данные записаны.")
    time.sleep(2)

    # --- Форматирование ---
    gid = ws_new.id
    col_end = total_cols   # AF (или меньше)
    requests = []

    for (row1, col_start, r, g, b, fs) in SECTION_HEADERS:
        cell_fmt = {
            "backgroundColor": make_color(r, g, b),
            "textFormat": {
                "bold": True, "fontSize": fs,
                "foregroundColorStyle": {"rgbColor": make_color(1, 1, 1)},
            },
        }
        requests.append(repeat_cell(
            gid, row1 - 1, col_start, col_end, cell_fmt,
            "userEnteredFormat(backgroundColor,textFormat(bold,fontSize,foregroundColorStyle))",
        ))

    for row1 in PERCENT_ROWS:
        requests.append(repeat_cell(
            gid, row1 - 1, 2, col_end,
            {"numberFormat": {"type": "PERCENT", "pattern": "0%"}},
            "userEnteredFormat.numberFormat",
        ))
    for row1 in NUMBER_ROWS:
        requests.append(repeat_cell(
            gid, row1 - 1, 2, col_end,
            {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
            "userEnteredFormat.numberFormat",
        ))
    for row1 in DECIMAL_ROWS:
        requests.append(repeat_cell(
            gid, row1 - 1, 2, col_end,
            {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.0"}},
            "userEnteredFormat.numberFormat",
        ))

    print(f"Отправляю {len(requests)} запросов форматирования...")
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id, body={"requests": requests}
    ).execute()
    print("Форматирование применено.")
    time.sleep(1)

    # --- Верификация ---
    data = ws_new.get_all_values()
    print(f"\n=== ПРОВЕРКА ===")
    print(f"Размер: {len(data)} строк × {len(data[0])} колонок")
    print(f"Строка 1: {data[0]}")
    print(f"Строка 2: {data[1][:6]}...")
    print()
    print(f"{'Метка':<40} | {'нед.1':>10} | {'нед.8':>10} | {'нед.16':>10}")
    print("-" * 80)
    check_rows = [5, 6, 11, 21, 23, 24, 25, 28, 40, 42, 62, 81]
    for r in check_rows:
        row = data[r - 1]
        label = row[1][:40]
        # cols for week 1, week 8, week 16
        w1  = row[2]  if len(row) > 2  else ""
        w8  = row[9]  if len(row) > 9  else ""
        w16 = row[17] if len(row) > 17 else ""
        print(f"  {r:2d}: {label:<40} | {w1:>10} | {w8:>10} | {w16:>10}")


if __name__ == "__main__":
    main()
