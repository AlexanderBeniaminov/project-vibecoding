"""
monthly_migrate.py — одноразовая миграция данных.
Копирует «ЕжеМесячный исходник» → «ЕжеМесячный» с конвертацией Excel-дат.

Запуск:
    python3 scripts/monthly_migrate.py
"""

import logging
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from sheets_writer import get_service, setup_monthly_formats

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SHEETS_ID    = "1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI"
SOURCE_SHEET = "ЕжеМесячный исходник"
TARGET_SHEET = "ЕжеМесячный"
CREDS_PATH   = os.path.join(os.path.dirname(__file__), "credentials.json")


def xl_to_date(serial: int) -> date:
    """Excel serial → Python date. Эпоха: 30.12.1899."""
    return date(1899, 12, 30) + timedelta(days=int(serial))


def clean_cell(val):
    """
    Вернуть числовое значение или пустую строку:
    — #REF! и другие ошибки → ""
    — строки-числа вида "1 943" → 1943
    — всё остальное → как есть
    """
    if isinstance(val, str):
        if val.startswith("#"):
            return ""
        # попытка распарсить "1 943" и подобные
        cleaned = val.replace(" ", "").replace(",", ".")
        try:
            return float(cleaned) if "." in cleaned else int(cleaned)
        except ValueError:
            return val  # оставляем как текст (заголовки секций и т.д.)
    return val


def _is_date_row(row_index: int) -> bool:
    """Строка 2 (index=1) в данных — строка дат."""
    return row_index == 1


def migrate():
    creds_path = CREDS_PATH
    service = get_service(credentials_path=creds_path)

    # --- Читаем исходник ---
    logger.info(f"Читаем «{SOURCE_SHEET}»...")
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEETS_ID,
        range=f"{SOURCE_SHEET}!A1:Z110",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    source_rows = result.get("values", [])
    if not source_rows:
        logger.error("Исходник пустой — прерываем")
        return

    logger.info(f"Строк в исходнике: {len(source_rows)}")

    # --- Собираем целевые строки ---
    target_rows = []

    for row_idx, row in enumerate(source_rows):
        new_row = []

        if _is_date_row(row_idx):
            # Строка 2: конвертируем Excel-серийные номера в YYYY-MM-01
            for col_idx, val in enumerate(row):
                if col_idx == 0:
                    new_row.append(val)  # метка "Монблан" — оставляем
                    continue
                if isinstance(val, (int, float)) and val > 10000:
                    d = xl_to_date(int(val))
                    # Только год и месяц без числа
                    new_row.append(f"{d.year}-{d.month:02d}")
                else:
                    new_row.append(clean_cell(val))
        else:
            for val in row:
                new_row.append(clean_cell(val))

        target_rows.append(new_row)

    # Выравниваем длины строк
    max_len = max((len(r) for r in target_rows), default=0)
    for r in target_rows:
        while len(r) < max_len:
            r.append("")

    # --- Очищаем и записываем в целевой лист ---
    logger.info(f"Очищаем «{TARGET_SHEET}»...")
    service.spreadsheets().values().clear(
        spreadsheetId=SHEETS_ID,
        range=f"{TARGET_SHEET}!A1:Z200",
    ).execute()

    logger.info(f"Записываем {len(target_rows)} строк × {max_len} столбцов...")
    service.spreadsheets().values().update(
        spreadsheetId=SHEETS_ID,
        range=f"{TARGET_SHEET}!A1",
        valueInputOption="RAW",
        body={"values": target_rows},
    ).execute()

    logger.info("✅ Данные скопированы")

    # --- Применяем числовые форматы ---
    logger.info("Применяем форматы (деньги / % / дробные)...")
    setup_monthly_formats(service, SHEETS_ID)

    logger.info("✅ Миграция завершена")

    # --- Проверяем первые 3 строки ---
    check = service.spreadsheets().values().get(
        spreadsheetId=SHEETS_ID,
        range=f"{TARGET_SHEET}!A1:E5",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    logger.info("Проверка (A1:E5):")
    for i, r in enumerate(check.get("values", [])):
        logger.info(f"  стр.{i+1}: {r}")


if __name__ == "__main__":
    migrate()
