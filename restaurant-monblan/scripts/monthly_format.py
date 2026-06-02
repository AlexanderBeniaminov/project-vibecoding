"""
monthly_format.py — визуальное форматирование листа «ЕжеМесячный».
Применяет жёлто-оранжевую цветовую гамму + заморозку строк 1-2 и столбца A.

Запуск:
    python3 scripts/monthly_format.py
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sheets_writer import get_service, setup_monthly_formats, setup_monthly_visual_format

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SHEETS_ID  = "1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI"
CREDS_PATH = os.path.join(os.path.dirname(__file__), "credentials.json")

if __name__ == "__main__":
    service = get_service(credentials_path=CREDS_PATH)
    setup_monthly_formats(service, SHEETS_ID)       # числовые форматы (#,##0, %, 0.00)
    setup_monthly_visual_format(service, SHEETS_ID)  # цвета, заморозка, ширина колонок
    print("✅ Форматирование листа «ЕжеМесячный» применено")
