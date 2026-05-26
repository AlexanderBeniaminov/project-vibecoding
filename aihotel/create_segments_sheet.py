#!/usr/bin/env python3
"""
Создаёт лист «2026 ✓» в файле Евгении/Надежды:
  1CdeyCx0VlzqNpUSDhmIdJPZYuR_1nv33bHu5FLnHX_8

Новая структура:
  Строка 1: «Метрика» | 1 | 2 | ... | 21  (ISO-номера недель)
  Строка 2: даты недель
  Блоки строк по сегментам (Физики, ДР, Группы, Корп)

Данные:
  - Охват/Лиды/Бронь/Оплата/Проживания — из листа «2026» файла Евгении
  - Сумма (руб.) — из финансового отчёта строки 40–52

Запуск: python3 aihotel/create_segments_sheet.py
"""

import os
import re
import sys
import json
import datetime
import gspread
from google.oauth2.service_account import Credentials

# ── ENV (читаем напрямую через regex, как в travelline_collector.py) ─────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH   = os.path.join(SCRIPT_DIR, '.env')

with open(ENV_PATH) as _f:
    _env_raw = _f.read()

def _env(key):
    return re.search(rf"{key}=(.+)", _env_raw).group(1).strip()

def _env_json(key):
    m = re.search(rf"{key}=(.*?)(?=\n[A-Z_]+=|\Z)", _env_raw, re.DOTALL)
    return json.loads(m.group(1).strip())

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

SEG_SHEET_ID     = '1CdeyCx0VlzqNpUSDhmIdJPZYuR_1nv33bHu5FLnHX_8'
FINANCE_SHEET_ID  = _env('FINANCE_SHEET_ID')
FINANCE_SHEET_GID = 2018226789   # GID листа «2026» финансового отчёта

NEW_SHEET_NAME = '2026 ✓'

# ── Конфиг парсинга источника ─────────────────────────────────────────────
# col = 0-based индекс ПЕРВОГО столбца блока месяца
# offsets внутри блока (относительно col блока)
MONTHS_CFG = [
    {'name': 'Январь',  'col': 1,  'охват': 0, 'лиды': 1, 'бронь': 3, 'оплата': 6, 'заезды': 8,
     'iso_weeks': [1, 2, 3, 4, 5]},      # 5 недель: нед.5 (26 янв) в строках 32/36
    {'name': 'Февраль', 'col': 14, 'охват': 0, 'лиды': 1, 'бронь': 3, 'оплата': 6, 'заезды': 8,
     'iso_weeks': [6, 7, 8, 9]},          # нед.6 (2 фев) … нед.9 (23 фев)
    {'name': 'Март',    'col': 25, 'охват': 0, 'лиды': 1, 'бронь': 2, 'оплата': 3, 'заезды': 4,
     'iso_weeks': [10, 11, 12, 13]},      # нед.10 (2 мар) … нед.13 (23 мар)
    {'name': 'Апрель',  'col': 32, 'охват': 0, 'лиды': 1, 'бронь': 2, 'оплата': 3, 'заезды': 4,
     'iso_weeks': [14, 15, 16, 17, 18]},  # 5 недель: нед.18 (27 апр) в строках 32/36
    {'name': 'Май',     'col': 39, 'охват': 0, 'лиды': 1, 'бронь': 3, 'оплата': 5, 'заезды': 7,
     'iso_weeks': [19, 20, 21]},          # нед.19 (4 мая) … нед.21 (18 мая)
]
# Смещение строки сегмента внутри недельного блока (7 строк/неделю, 0-indexed)
SEG_ROW_OFFSETS = {'физики': 2, 'группы': 4, 'корп': 5, 'др': 6}

ALL_WEEKS = list(range(1, 22))  # недели 1–21

# ── Строки финансового отчёта для сумм сегментов ─────────────────────────
# 1-based строки листа «2026» финансового отчёта
FINANCE_SUM_ROWS = {
    'др_сумма':     42,
    'группы_сумма': 46,
    'корп_сумма':   49,
    'физики_сумма': 52,
}


def iso_week_label(week: int, year: int = 2026) -> str:
    """Возвращает «ПН-ВС» для ISO-недели."""
    # 4 января всегда в 1-й ISO-неделе года
    jan4 = datetime.date(year, 1, 4)
    # Переходим к понедельнику этой недели
    monday = jan4 - datetime.timedelta(days=jan4.weekday()) + datetime.timedelta(weeks=week - 1)
    sunday = monday + datetime.timedelta(days=6)
    return f"{monday.strftime('%d.%m')}-{sunday.strftime('%d.%m')}"


def get_credentials():
    creds_info = _env_json('GOOGLE_CREDS_JSON')
    return Credentials.from_service_account_info(creds_info, scopes=SCOPES)


def parse_source_sheet(src_sh) -> dict:
    """
    Парсит лист «2026» источника.
    Возвращает {iso_week: {сегмент: {метрика: значение}}}
    """
    print("  Читаем исходный лист...")
    data = src_sh.get_all_values()
    print(f"  Прочитано {len(data)} строк × {len(data[0]) if data else 0} столбцов")

    result = {}

    for mcfg in MONTHS_CFG:
        base_col = mcfg['col']  # 0-based
        iso_weeks = mcfg['iso_weeks']

        for i, iso_week in enumerate(iso_weeks):
            week_row_start = 1 + i * 7  # 0-based: неделя 1 → строки 1–7, неделя 2 → 8–14...

            seg_data = {}
            for seg, row_offset in SEG_ROW_OFFSETS.items():
                row_idx = week_row_start + row_offset  # 0-based
                if row_idx >= len(data):
                    continue

                row = data[row_idx]

                def get_val(off):
                    col_idx = base_col + off
                    if col_idx >= len(row):
                        return 0
                    v = row[col_idx]
                    try:
                        return int(float(str(v).replace(' ', '').replace(',', '.') or '0'))
                    except (ValueError, TypeError):
                        return 0

                seg_data[seg] = {
                    'охват':    get_val(mcfg['охват']),
                    'лиды':     get_val(mcfg['лиды']),
                    'бронь':    get_val(mcfg['бронь']),
                    'оплата':   get_val(mcfg['оплата']),
                    'заезды':   get_val(mcfg['заезды']),
                }

            result[iso_week] = seg_data

    return result


def read_finance_sums(fin_sh) -> dict:
    """
    Читает суммы сегментов из финансового листа «2026».
    Возвращает {iso_week: {ключ: сумма}}

    Строка 1 финансового листа содержит ISO-номера недель начиная с col 3 (1-based).
    """
    print("  Читаем финансовый лист (строки 1, 42, 46, 49, 52)...")
    # Читаем строку 1 (номера недель)
    row1 = fin_sh.row_values(1)  # 1-based, возвращает список

    # Строим карту: iso_week → col_idx (0-based)
    week_col = {}
    for ci, val in enumerate(row1):
        try:
            wn = int(float(str(val).strip()))
            if 1 <= wn <= 53:
                week_col[wn] = ci
        except (ValueError, TypeError):
            pass

    print(f"  Найдены недели в фин.листе: {sorted(week_col.keys())}")

    # Читаем строки с суммами (все сразу для эффективности)
    sums_by_row = {}
    for key, row_num in FINANCE_SUM_ROWS.items():
        row_vals = fin_sh.row_values(row_num)
        sums_by_row[key] = row_vals

    result = {}
    for iso_week in ALL_WEEKS:
        ci = week_col.get(iso_week)
        week_sums = {}
        for key in FINANCE_SUM_ROWS:
            if ci is not None and ci < len(sums_by_row[key]):
                v = sums_by_row[key][ci]
                try:
                    week_sums[key] = int(float(str(v).replace(' ', '').replace(',', '.') or '0'))
                except (ValueError, TypeError):
                    week_sums[key] = 0
            else:
                week_sums[key] = 0
        result[iso_week] = week_sums

    return result


def build_sheet_data(source_weeks: dict, finance_sums: dict) -> list:
    """
    Строит список строк для нового листа.
    Возвращает list[list] — значения ячеек.
    """
    # Ширина: 2 (A=раздел, B=метрика) + 21 недели = 23 столбца
    COLS = 2 + len(ALL_WEEKS)

    rows = []

    def make_row(section, metric, vals):
        """vals: список значений по неделям (len=21) или пустая строка"""
        if vals == 'SEP':
            return [''] * COLS
        return [section, metric] + (vals if vals else [''] * len(ALL_WEEKS))

    # ── Строка 1: заголовок с номерами недель ──────────────────────────────
    rows.append(['', 'Метрика'] + ALL_WEEKS)

    # ── Строка 2: даты недель ─────────────────────────────────────────────
    rows.append(['', ''] + [iso_week_label(w) for w in ALL_WEEKS])

    # ── ФИЗИКИ ─────────────────────────────────────────────────────────────
    rows.append(['👤 ФИЗИКИ', '', *([''] * 21)])  # заголовок блока
    rows.append(make_row('', 'Охват',              [source_weeks.get(w, {}).get('физики', {}).get('охват',  0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Лиды',               [source_weeks.get(w, {}).get('физики', {}).get('лиды',   0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Бронь ★',            [source_weeks.get(w, {}).get('физики', {}).get('бронь',  0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Оплата',             [source_weeks.get(w, {}).get('физики', {}).get('оплата', 0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Проживания',         [source_weeks.get(w, {}).get('физики', {}).get('заезды', 0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Сумма (руб.) ★',     [finance_sums.get(w, {}).get('физики_сумма',  0) for w in ALL_WEEKS]))

    # ── Пустая строка ──────────────────────────────────────────────────────
    rows.append([''] * COLS)

    # ── ДР ─────────────────────────────────────────────────────────────────
    rows.append(['🎂 ДР', '', *([''] * 21)])
    rows.append(make_row('', 'Охват',              [source_weeks.get(w, {}).get('др', {}).get('охват',  0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Лиды',               [source_weeks.get(w, {}).get('др', {}).get('лиды',   0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Бронь ★',            [source_weeks.get(w, {}).get('др', {}).get('бронь',  0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Оплата',             [source_weeks.get(w, {}).get('др', {}).get('оплата', 0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Проживания ★',       [source_weeks.get(w, {}).get('др', {}).get('заезды', 0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Сумма (руб.) ★',     [finance_sums.get(w, {}).get('др_сумма',      0) for w in ALL_WEEKS]))

    # ── Пустая строка ──────────────────────────────────────────────────────
    rows.append([''] * COLS)

    # ── ГРУППЫ ─────────────────────────────────────────────────────────────
    rows.append(['👥 ГРУППЫ', '', *([''] * 21)])
    rows.append(make_row('', 'Охват',              [source_weeks.get(w, {}).get('группы', {}).get('охват',  0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Лиды',               [source_weeks.get(w, {}).get('группы', {}).get('лиды',   0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Бронь ★',            [source_weeks.get(w, {}).get('группы', {}).get('бронь',  0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Оплата',             [source_weeks.get(w, {}).get('группы', {}).get('оплата', 0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Проживания ★',       [source_weeks.get(w, {}).get('группы', {}).get('заезды', 0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Сумма (руб.) ★',     [finance_sums.get(w, {}).get('группы_сумма',  0) for w in ALL_WEEKS]))

    # ── Пустая строка ──────────────────────────────────────────────────────
    rows.append([''] * COLS)

    # ── КОРПОРАТИВЫ ────────────────────────────────────────────────────────
    rows.append(['🏢 КОРП', '', *([''] * 21)])
    rows.append(make_row('', 'Охват',              [source_weeks.get(w, {}).get('корп', {}).get('охват',  0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Лиды',               [source_weeks.get(w, {}).get('корп', {}).get('лиды',   0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Бронь ★',            [source_weeks.get(w, {}).get('корп', {}).get('бронь',  0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Оплата',             [source_weeks.get(w, {}).get('корп', {}).get('оплата', 0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Проживания',         [source_weeks.get(w, {}).get('корп', {}).get('заезды', 0) for w in ALL_WEEKS]))
    rows.append(make_row('', 'Сумма (руб.) ★',     [finance_sums.get(w, {}).get('корп_сумма',    0) for w in ALL_WEEKS]))

    return rows


def main():
    print("=== Создание листа «2026 ✓» ===")

    creds = get_credentials()
    gc = gspread.authorize(creds)

    # ── Открываем источник (файл Евгении) ───────────────────────────────
    print(f"\n1. Открываем источник: {SEG_SHEET_ID}")
    try:
        seg_ss = gc.open_by_key(SEG_SHEET_ID)
    except Exception as e:
        print(f"❌ Ошибка доступа к источнику: {e}")
        sys.exit(1)

    src_sheets = [s.title for s in seg_ss.worksheets()]
    print(f"   Листы: {src_sheets}")

    src_sh = seg_ss.worksheet('2026')
    print(f"   Открыт лист «2026»")

    # ── Открываем финансовый лист ────────────────────────────────────────
    print(f"\n2. Открываем финансовый отчёт: {FINANCE_SHEET_ID}")
    try:
        fin_ss = gc.open_by_key(FINANCE_SHEET_ID)
    except Exception as e:
        print(f"❌ Ошибка доступа к фин.отчёту: {e}")
        sys.exit(1)

    # Находим лист по GID
    fin_sh = None
    for sh in fin_ss.worksheets():
        if sh.id == FINANCE_SHEET_GID:
            fin_sh = sh
            break
    if not fin_sh:
        print(f"❌ Лист GID={FINANCE_SHEET_GID} не найден в фин.отчёте")
        sys.exit(1)
    print(f"   Открыт лист «{fin_sh.title}»")

    # ── Парсим данные ────────────────────────────────────────────────────
    print(f"\n3. Парсим источник...")
    source_weeks = parse_source_sheet(src_sh)
    print(f"   Недели: {sorted(source_weeks.keys())}")
    # Показываем пример
    w21 = source_weeks.get(21, {})
    print(f"   Нед.21 физики: {w21.get('физики', {})}")
    print(f"   Нед.21 др:     {w21.get('др', {})}")

    print(f"\n4. Читаем суммы из финансового отчёта...")
    finance_sums = read_finance_sums(fin_sh)
    # Показываем пример
    print(f"   Нед.21 суммы: {finance_sums.get(21, {})}")

    # ── Строим данные нового листа ───────────────────────────────────────
    print(f"\n5. Строим структуру нового листа...")
    sheet_data = build_sheet_data(source_weeks, finance_sums)
    print(f"   Строк: {len(sheet_data)}, столбцов: {len(sheet_data[0]) if sheet_data else 0}")

    # ── Создаём или очищаем лист «2026 ✓» ────────────────────────────────
    print(f"\n6. Создаём лист «{NEW_SHEET_NAME}»...")
    new_sh = None
    for sh in seg_ss.worksheets():
        if sh.title == NEW_SHEET_NAME:
            new_sh = sh
            break

    if new_sh:
        print(f"   Лист уже существует — очищаем")
        new_sh.clear()
    else:
        new_sh = seg_ss.add_worksheet(
            title=NEW_SHEET_NAME,
            rows=max(50, len(sheet_data) + 5),
            cols=max(30, len(sheet_data[0]) + 2)
        )
        print(f"   Лист создан")

    # ── Записываем данные ────────────────────────────────────────────────
    print(f"\n7. Записываем данные...")
    new_sh.update('A1', sheet_data, value_input_option='USER_ENTERED')
    print(f"   ✅ Записано {len(sheet_data)} строк")

    # ── Проверка ─────────────────────────────────────────────────────────
    print(f"\n8. Проверка структуры:")
    check = new_sh.get('A1:C5')
    for i, row in enumerate(check):
        print(f"   Строка {i+1}: {row}")

    print(f"\n✅ Лист «{NEW_SHEET_NAME}» создан и заполнен.")
    print(f"   URL: https://docs.google.com/spreadsheets/d/{SEG_SHEET_ID}/edit#gid={new_sh.id}")


if __name__ == '__main__':
    main()
