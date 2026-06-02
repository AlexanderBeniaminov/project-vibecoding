"""
monthly_extend.py — добавление месяцев 2026-01..2026-03 из «ЕжеМесячный исходник».

Читает столбцы 27-29 исходника (2026-01, 2026-02, 2026-03), конвертирует даты
из Excel-серийников в YYYY-MM, очищает значения (#REF! и т.д.) и записывает
в «ЕжеМесячный» как новые столбцы, затем применяет форматирование шаблона.

Запуск:
    python3 scripts/monthly_extend.py
"""

import logging
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from sheets_writer import (
    get_service, MONTHLY_SHEET,
    _find_or_create_date_column, _col_letter,
    setup_monthly_formats, setup_monthly_visual_format,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SHEETS_ID    = "1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI"
SOURCE_SHEET = "ЕжеМесячный исходник"
CREDS_PATH   = os.path.join(os.path.dirname(__file__), "credentials.json")

# Столбцы исходника (1-based) для 2026 месяцев
# col 27 = 2026-01 (serial 46023), col 28 = 2026-02 (serial 46071), col 29 = 2026-03 (serial 46095)
MONTHS_TO_ADD = [
    (27, "2026-01"),
    (28, "2026-02"),
    (29, "2026-03"),
]


def xl_to_ym(serial) -> str:
    d = date(1899, 12, 30) + timedelta(days=int(serial))
    return f"{d.year}-{d.month:02d}"


def clean_cell(val):
    if isinstance(val, str):
        if val.startswith("#"):
            return ""
        cleaned = val.replace(" ", "").replace(",", ".")
        try:
            return float(cleaned) if "." in cleaned else int(cleaned)
        except ValueError:
            return val
    return val


def copy_month(service, src_col_1based: int, month_str: str):
    """Скопировать один месяц из исходника в целевой лист."""
    col_ltr_src = _col_letter(src_col_1based)

    # Читаем строки 2-100 из исходника (строка 1 пустая, нам не нужна)
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEETS_ID,
        range=f"'{SOURCE_SHEET}'!{col_ltr_src}2:{col_ltr_src}100",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    src_vals = result.get("values", [])

    # Нормализуем до 99 строк (строки 2-100)
    while len(src_vals) < 99:
        src_vals.append([""])

    # Строка 2 (index 0 в src_vals): Excel serial → YYYY-MM
    raw_date = src_vals[0][0] if src_vals[0] else ""
    if isinstance(raw_date, (int, float)) and raw_date > 10000:
        date_val = xl_to_ym(raw_date)
    else:
        date_val = str(raw_date)

    # Строки 3-100 (index 1-98): чистим значения
    data_rows = []
    for i in range(1, 99):
        raw = src_vals[i][0] if i < len(src_vals) and src_vals[i] else ""
        data_rows.append(clean_cell(raw))

    # Находим или создаём колонку в целевом листе
    col_num = _find_or_create_date_column(
        service, SHEETS_ID, MONTHLY_SHEET, month_str, search_row=2
    )
    col_ltr_dst = _col_letter(col_num)

    # Пишем: строка 2 = дата, строки 3-100 = данные (99 строк итого)
    body = [[date_val]] + [[v] for v in data_rows]

    service.spreadsheets().values().update(
        spreadsheetId=SHEETS_ID,
        range=f"{MONTHLY_SHEET}!{col_ltr_dst}2",
        valueInputOption="RAW",
        body={"values": body},
    ).execute()

    logger.info(f"{month_str}: исходник col {src_col_1based} ({col_ltr_src}) → целевой col {col_num} ({col_ltr_dst})")


def expand_sheet_columns(service, needed_cols: int):
    """Расширить лист «ЕжеМесячный» до нужного количества столбцов."""
    meta = service.spreadsheets().get(spreadsheetId=SHEETS_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == MONTHLY_SHEET:
            sheet_id  = s["properties"]["sheetId"]
            cur_cols  = s["properties"]["gridProperties"]["columnCount"]
            if cur_cols < needed_cols:
                service.spreadsheets().batchUpdate(
                    spreadsheetId=SHEETS_ID,
                    body={"requests": [{
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": sheet_id,
                                "gridProperties": {"columnCount": needed_cols},
                            },
                            "fields": "gridProperties.columnCount",
                        }
                    }]},
                ).execute()
                logger.info(f"Лист расширен: {cur_cols} → {needed_cols} столбцов")
            else:
                logger.info(f"Столбцов достаточно: {cur_cols} (нужно {needed_cols})")
            return
    raise ValueError(f"Лист «{MONTHLY_SHEET}» не найден")


def main():
    service = get_service(credentials_path=CREDS_PATH)

    # Текущих 26 + 3 новых = 29, с запасом ставим 35
    expand_sheet_columns(service, needed_cols=35)

    for src_col, month_str in MONTHS_TO_ADD:
        copy_month(service, src_col, month_str)

    logger.info("Применяем форматирование шаблона к обновлённому листу...")
    setup_monthly_formats(service, SHEETS_ID)
    setup_monthly_visual_format(service, SHEETS_ID)

    logger.info("✅ Таблица расширена: добавлены 2026-01, 2026-02, 2026-03")


if __name__ == "__main__":
    main()
