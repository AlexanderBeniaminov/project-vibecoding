#!/usr/bin/env python3
"""
Создаёт лист "2025н" в финансовой таблице aihotel.
Структура строк (82 строки) — из листа "Новая структура".
Данные — из листа "2025" (недели 23-52).
RevPAR и RevPAC — формулы.
"""
import json
import re
import time

import gspread
from google.oauth2.service_account import Credentials

NEW_SHEET_NAME = "2025н"
WEEKS = list(range(23, 53))  # [23, 24, ..., 52]


def col_letter(n: int) -> str:
    """1-based column index → spreadsheet letter (1→A, 27→AA, ...)"""
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def clean(val: str) -> str:
    """Убираем неразрывные пробелы и пробелы по краям."""
    return val.replace("\xa0", "").strip()


# ---------------------------------------------------------------------------
# Маппинг: строка "Новая структура" (1-based) → строка листа "2025" (1-based)
# None  — пустая строка или заголовок раздела
# 'REVPAR' — формула =ADR * Загрузка коттеджей
# 'REVPAC' — формула =Доход / Гостей
# ---------------------------------------------------------------------------
MAPPING = {
    4:  5,          # План Общий (НФ+Кафе) на месяц
    5:  6,          # Доход общий за неделю, руб
    6:  8,          # Примерное выполнение плана в тек. месяце, %
    7:  9,          # Выручка прошлого периода (года) за месяц
    8:  10,         # Примерная выручка в месяц (динамика), руб
    9:  11,         # Выручка к факту прошлого года, %
    11: 13,         # Выручка Монблан
    12: 14,         # Чеков Монблан
    13: 17,         # F&B % от оборота
    14: 27,         # Кол-во завтраков
    15: 29,         # Конверсия завтраков
    17: 23,         # Фурако/бани
    18: 24,         # Беседки/мангалы
    19: 25,         # Прочее
    21: 55,         # Гостей всего
    22: 56,         # % повторных гостей
    23: 45,         # ADR
    24: "REVPAR",   # RevPAR = ADR × Загрузка коттеджей
    25: "REVPAC",   # RevPAC = Доход / Гостей
    27: 48,         # Ср. пребывание в коттеджах (дней)
    28: 47,         # % загрузки Коттеджей
    29: 49,         # % загрузки Даниэль
    30: 51,         # % загрузки Ален
    32: 53,         # Доля отмен по всем категориям, %
    33: 64,         # Доля бронирований через прямые продажи vs OTA
    35: 40,         # Планируемая выручка НФ на следующий месяц
    36: 41,         # Забронировано НФ на следующий месяц
    37: 42,         # Динамика с прошлым периодом
    38: 43,         # % выполнения плана на следующий месяц
    40: 67,         # Броней ДР, кол-во
    41: 69,         # Проживаний ДР, кол-во
    42: 70,         # Сумма по ДР
    44: 77,         # Броней групп (от ЕБ), кол-во
    45: 79,         # Проживаний групп (от ЕБ), кол-во
    46: 80,         # Сумма по группам
    48: 72,         # Броней корпоратив, кол-во
    49: 75,         # Сумма от корпорантов
    51: 82,         # Броней физиков (админы+бот)
    52: 85,         # Сумма по физикам
    54: 58,         # Показатель NPS
    56: 59,         # Количество отзывов Коттеджи
    57: 60,         # Доля негативных отзывов Коттеджи
    59: 61,         # Количество отзывов Хостелы
    60: 62,         # Доля негативных отзывов Хостелы
    62: 33,         # Остаток на расчётном счёте
    63: 34,         # Остаток в кассе
    65: 31,         # Кредиторская задолженность
    66: 32,         # Дебиторская задолженность
    68: 88,         # Кол-во заявок на ремонт
    69: 89,         # Из них выполнено
    70: 90,         # Невыполненных заявок
    72: 92,         # Уборки коттеджи
    73: 93,         # Из них стыковочных (кот.)
    74: 94,         # Уборки хостелы
    76: 97,         # Входящих звонков
    77: 98,         # Неотвеченных звонков
    78: 99,         # Доля без ответа %
    80: 101,        # Проверок стандартов
    81: 102,        # ФОТ горничные+техники
    82: 103,        # ФОТ F&B персонал
}


def main():
    # --- Загрузка учётных данных ---
    with open(".env") as f:
        env_text = f.read()

    m = re.search(r"GOOGLE_CREDS_JSON=(.*?)(?=\n[A-Z_]+=|\Z)", env_text, re.DOTALL)
    creds_info = json.loads(m.group(1).strip())
    sheet_id = re.search(r"FINANCE_SHEET_ID=(.+)", env_text).group(1).strip()

    creds = Credentials.from_service_account_info(
        creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.Client(auth=creds)
    ss = client.open_by_key(sheet_id)

    # --- Чтение источников ---
    novstr = ss.worksheet("Новая структура").get_all_values()  # 82 × 3
    src = ss.worksheet("2025").get_all_values()                # 105 × 62

    # Находим столбцы недель в листе 2025 (строка 2, 0-indexed)
    week_cols = {}  # week → col_index (0-based)
    for ci, val in enumerate(src[1]):
        stripped = val.strip()
        if stripped.isdigit():
            wn = int(stripped)
            if 23 <= wn <= 52:
                week_cols[wn] = ci

    missing = [w for w in WEEKS if w not in week_cols]
    if missing:
        print(f"ПРЕДУПРЕЖДЕНИЕ: не найдены недели {missing}")

    # Даты недель (строка 3)
    week_dates = {wn: clean(src[2][ci]) if ci < len(src[2]) else ""
                  for wn, ci in week_cols.items()}

    print("Найдено недель:", len(week_cols))
    print("Первые 3:", {w: week_dates[w] for w in WEEKS[:3] if w in week_dates})

    # --- Удаляем старый лист, если есть ---
    try:
        ss.del_worksheet(ss.worksheet(NEW_SHEET_NAME))
        print(f"Удалён старый лист '{NEW_SHEET_NAME}'")
        time.sleep(1)
    except gspread.WorksheetNotFound:
        pass

    total_cols = 2 + len(WEEKS)  # A(итоги) + B(метки) + 30 недель
    ws_new = ss.add_worksheet(title=NEW_SHEET_NAME, rows=82, cols=total_cols)
    print(f"Создан лист '{NEW_SHEET_NAME}' (82 × {total_cols})")
    time.sleep(1)

    # --- Строим матрицу данных ---
    rows_out = []

    for ri in range(82):
        novstr_row = ri + 1      # 1-based номер строки
        ns = novstr[ri]          # [A, B, C] из Новая структура
        row = [""] * total_cols

        # Колонка A — итоговые данные (пока пусто, сохраняем из источника)
        row[0] = ns[0]
        # Колонка B — метки строк
        row[1] = ns[1]

        # --- Строка 1: год + номера недель ---
        if novstr_row == 1:
            row[0] = "2025"
            row[1] = "Неделя"
            for i, wn in enumerate(WEEKS):
                row[2 + i] = str(wn)
            rows_out.append(row)
            continue

        # --- Строка 2: даты ---
        if novstr_row == 2:
            row[1] = "Даты"
            for i, wn in enumerate(WEEKS):
                row[2 + i] = week_dates.get(wn, "")
            rows_out.append(row)
            continue

        # --- Остальные строки: данные или формулы ---
        source = MAPPING.get(novstr_row)

        if source == "REVPAR":
            # RevPAR = ADR (строка 23) × Загрузка коттеджей (строка 28)
            for i in range(len(WEEKS)):
                c = col_letter(3 + i)
                row[2 + i] = f"={c}23*{c}28"

        elif source == "REVPAC":
            # RevPAC = Доход (строка 5) / Гостей (строка 21)
            # IFERROR с ; — корректно для русской локали Google Sheets
            for i in range(len(WEEKS)):
                c = col_letter(3 + i)
                row[2 + i] = f'=IFERROR({c}5/{c}21;"")'

        elif isinstance(source, int):
            src_row = src[source - 1]  # 0-based
            for i, wn in enumerate(WEEKS):
                ci = week_cols.get(wn)
                if ci is not None and ci < len(src_row):
                    row[2 + i] = clean(src_row[ci])

        rows_out.append(row)

    # --- Записываем всё одним батчем ---
    print("Записываю данные...")
    ws_new.update(
        range_name="A1",
        values=rows_out,
        value_input_option="USER_ENTERED",
    )
    print("Запись завершена.")
    time.sleep(2)

    # --- Верификация ---
    check = ws_new.get_all_values()
    print(f"\n=== Проверка: {len(check)} строк × {len(check[0])} колонок ===")
    print("Строка 1 (год+недели):", check[0][:6], "...")
    print("Строка 2 (даты):      ", check[1][:6], "...")
    print("Строка 5 (Доход):     ", check[4][:5], "...")
    print("Строка 23 (ADR):      ", check[22][:5], "...")
    print("Строка 24 (RevPAR):   ", check[23][:5], "...")
    print("Строка 25 (RevPAC):   ", check[24][:5], "...")
    print("Строка 28 (Загрузка): ", check[27][:5], "...")
    print("Строка 82 (ФОТ F&B):  ", check[81][:4], "...")


if __name__ == "__main__":
    main()
