#!/usr/bin/env python3
"""
Форматирование листа «2026 ✓»:
  - Фиксация строк 1-2 и столбцов A-B (фриз)
  - Цветовая разметка секций (Физики / ДР / Группы / Корп)
  - Выделение ★-строк (те, что идут в финансовый отчёт)
  - Ширина столбцов: B пошире, недели поуже
  - Жирные подписи, границы ячеек, чередование фона

Запуск: python3 aihotel/format_segments_sheet.py
"""

import re
import json
import os
import gspread
from google.oauth2.service_account import Credentials

# ── Credentials ───────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SCRIPT_DIR, '.env')) as f:
    _env_raw = f.read()

def _env_json(key):
    m = re.search(rf"{key}=(.*?)(?=\n[A-Z_]+=|\Z)", _env_raw, re.DOTALL)
    return json.loads(m.group(1).strip())

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_info(_env_json('GOOGLE_CREDS_JSON'), scopes=SCOPES)
gc = gspread.authorize(creds)

SEG_SHEET_ID   = '1CdeyCx0VlzqNpUSDhmIdJPZYuR_1nv33bHu5FLnHX_8'
SHEET_NAME     = '2026 ✓'
TOTAL_WEEKS    = 21   # столбцов с данными (C..W = col 3..23)

# ── Цветовые константы (RGB 0-1) ──────────────────────────────────────────────
def c(r, g, b): return {"red": r/255, "green": g/255, "blue": b/255}
def w():        return {"red": 1,     "green": 1,     "blue": 1}

CLR = {
    'hdr_bg':    c(38,  50,  56),   # очень тёмный (шапка номеров недель)
    'dates_bg':  c(69,  90, 100),   # чуть светлее (даты)
    'white':     w(),

    'fiziki':    c(0,  121, 107),   # teal-700
    'fiziki_lt': c(224, 247, 244),  # teal-50

    'dr':        c(106,  27, 154),  # purple-800
    'dr_lt':     c(243, 229, 245),  # purple-50

    'gruppy':    c(21,  101, 192),  # blue-800
    'gruppy_lt': c(227, 242, 253),  # blue-50

    'korp':      c(230,  81,   0),  # deep-orange-800
    'korp_lt':   c(255, 243, 224),  # orange-50

    'star_bg':   c(255, 253, 231),  # yellow-50 (★ строки)
    'sep_bg':    c(250, 250, 250),  # почти белый (разделители)
    'lbl_bg':    c(245, 245, 245),  # столбец B (метрики)
}

# ── Структура листа (1-based строки) ─────────────────────────────────────────
ROW = {
    'hdr':   1,   # номера недель
    'dates': 2,   # диапазоны дат

    'fiziki_sec':  3,   # 👤 ФИЗИКИ
    'fiziki_start':4, 'fiziki_end': 9,   # строки данных Физики (4..9 включительно)
    'fiziki_star': [6, 9],               # ★ строки Физики

    'sep1':  10,  # разделитель

    'dr_sec':  11,
    'dr_start':12, 'dr_end': 17,
    'dr_star': [14, 16, 17],

    'sep2':  18,

    'gruppy_sec':  19,
    'gruppy_start':20, 'gruppy_end': 25,
    'gruppy_star': [22, 24, 25],

    'sep3':  26,

    'korp_sec':  27,
    'korp_start':28, 'korp_end': 33,
    'korp_star': [30, 33],

    'total': 33,
}

TOTAL_COLS = 2 + TOTAL_WEEKS   # A + B + 21 недель = 23


def rng(sheet_id, r1, r2, c1, c2):
    """Диапазон для API (0-based, end exclusive)."""
    return {
        "sheetId": sheet_id,
        "startRowIndex": r1 - 1, "endRowIndex": r2,
        "startColumnIndex": c1 - 1, "endColumnIndex": c2,
    }


def fmt_req(sheet_id, r1, r2, c1, c2, fmt, fields=None):
    """repeatCell request."""
    if fields is None:
        fields = "userEnteredFormat"
    return {
        "repeatCell": {
            "range": rng(sheet_id, r1, r2, c1, c2),
            "cell": {"userEnteredFormat": fmt},
            "fields": fields,
        }
    }


def border_req(sheet_id, r1, r2, c1, c2, style="SOLID", color=None):
    """updateBorders request — внешняя + внутренняя сетка."""
    if color is None:
        color = c(200, 200, 200)
    b = {"style": style, "color": color, "width": 1}
    return {
        "updateBorders": {
            "range": rng(sheet_id, r1, r2, c1, c2),
            "top": b, "bottom": b, "left": b, "right": b,
            "innerHorizontal": b, "innerVertical": b,
        }
    }


def col_width_req(sheet_id, col_0based, px):
    """setDimensionProperties — ширина столбца."""
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": col_0based,
                "endIndex": col_0based + 1,
            },
            "properties": {"pixelSize": px},
            "fields": "pixelSize",
        }
    }


def row_height_req(sheet_id, row_0based, px):
    """setDimensionProperties — высота строки."""
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": row_0based,
                "endIndex": row_0based + 1,
            },
            "properties": {"pixelSize": px},
            "fields": "pixelSize",
        }
    }


def freeze_req(sheet_id, rows, cols):
    """Заморозить rows строк и cols столбцов."""
    return {
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {
                    "frozenRowCount": rows,
                    "frozenColumnCount": cols,
                },
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }
    }


def cell_fmt(bg=None, bold=False, italic=False, halign="LEFT", valign="MIDDLE",
             text_color=None, font_size=10, wrap="WRAP"):
    fmt = {
        "horizontalAlignment": halign,
        "verticalAlignment": valign,
        "wrapStrategy": wrap,
        "textFormat": {
            "bold": bold,
            "italic": italic,
            "fontSize": font_size,
        },
    }
    if bg:
        fmt["backgroundColor"] = bg
    if text_color:
        fmt["textFormat"]["foregroundColor"] = text_color
    return fmt


def build_requests(sheet_id):
    reqs = []

    # ── 0. Фриз ───────────────────────────────────────────────────────────────
    reqs.append(freeze_req(sheet_id, rows=2, cols=2))

    # ── 1. Ширины столбцов ────────────────────────────────────────────────────
    reqs.append(col_width_req(sheet_id, 0, 35))     # A — иконка секции (узкий)
    reqs.append(col_width_req(sheet_id, 1, 195))    # B — название метрики
    for i in range(TOTAL_WEEKS):
        reqs.append(col_width_req(sheet_id, 2 + i, 82))  # C..W — недели

    # ── 2. Высоты строк ───────────────────────────────────────────────────────
    reqs.append(row_height_req(sheet_id, ROW['hdr'] - 1,   34))   # шапка недель
    reqs.append(row_height_req(sheet_id, ROW['dates'] - 1, 26))   # даты
    for sec_row in [ROW['fiziki_sec'], ROW['dr_sec'], ROW['gruppy_sec'], ROW['korp_sec']]:
        reqs.append(row_height_req(sheet_id, sec_row - 1, 30))
    for sep_row in [ROW['sep1'], ROW['sep2'], ROW['sep3']]:
        reqs.append(row_height_req(sheet_id, sep_row - 1, 8))    # тонкий разделитель

    # ── 3. Шапка: строка 1 (номера недель) ───────────────────────────────────
    # AB — пустые ячейки шапки
    reqs.append(fmt_req(sheet_id, 1, 1, 1, 2,
                        cell_fmt(bg=CLR['hdr_bg'], bold=True, text_color=CLR['white'],
                                 halign="CENTER", font_size=11, wrap="CLIP")))
    # C..W — номера недель
    reqs.append(fmt_req(sheet_id, 1, 1, 3, TOTAL_COLS + 1,
                        cell_fmt(bg=CLR['hdr_bg'], bold=True, text_color=CLR['white'],
                                 halign="CENTER", font_size=11, wrap="CLIP")))
    # Нижняя граница-разделитель
    reqs.append({
        "updateBorders": {
            "range": rng(sheet_id, 1, 1, 1, TOTAL_COLS + 1),
            "bottom": {"style": "SOLID_MEDIUM", "color": c(100, 181, 246), "width": 2},
        }
    })

    # ── 4. Строка 2 (даты) ────────────────────────────────────────────────────
    reqs.append(fmt_req(sheet_id, 2, 2, 1, TOTAL_COLS + 1,
                        cell_fmt(bg=CLR['dates_bg'], italic=True, text_color=CLR['white'],
                                 halign="CENTER", font_size=9, wrap="CLIP")))
    reqs.append({
        "updateBorders": {
            "range": rng(sheet_id, 2, 2, 1, TOTAL_COLS + 1),
            "bottom": {"style": "SOLID_MEDIUM", "color": c(150, 150, 150), "width": 2},
        }
    })

    # ── Вспомогательная функция для секции ───────────────────────────────────
    def add_section(sec_row, data_start, data_end, star_rows,
                    clr_dark, clr_light):
        # Заголовок секции (вся строка)
        reqs.append(fmt_req(sheet_id, sec_row, sec_row, 1, TOTAL_COLS + 1,
                            cell_fmt(bg=clr_dark, bold=True, text_color=CLR['white'],
                                     halign="LEFT", font_size=10, wrap="CLIP")))
        reqs.append({
            "updateBorders": {
                "range": rng(sheet_id, sec_row, sec_row, 1, TOTAL_COLS + 1),
                "bottom": {"style": "SOLID", "color": c(200, 200, 200)},
            }
        })

        # Все строки данных — базовый фон
        for r in range(data_start, data_end + 1):
            is_star = r in star_rows
            bg_data = CLR['star_bg'] if is_star else CLR['white']

            # Столбец A (иконка/пусто)
            reqs.append(fmt_req(sheet_id, r, r, 1, 1,
                                cell_fmt(bg=clr_dark, text_color=CLR['white'],
                                         halign="CENTER", font_size=10)))

            # Столбец B (название метрики)
            reqs.append(fmt_req(sheet_id, r, r, 2, 2,
                                cell_fmt(bg=clr_light, bold=is_star, font_size=10,
                                         halign="LEFT", wrap="CLIP")))

            # Столбцы данных C..W
            reqs.append(fmt_req(sheet_id, r, r, 3, TOTAL_COLS + 1,
                                cell_fmt(bg=bg_data, bold=is_star, font_size=10,
                                         halign="CENTER")))

        # Границы всего блока данных (секция + строки)
        reqs.append(border_req(sheet_id, sec_row, data_end, 1, TOTAL_COLS + 1,
                               style="SOLID", color=c(180, 180, 180)))
        # Жирная граница снизу всего блока
        reqs.append({
            "updateBorders": {
                "range": rng(sheet_id, data_end, data_end, 1, TOTAL_COLS + 1),
                "bottom": {"style": "SOLID_MEDIUM", "color": clr_dark, "width": 2},
            }
        })

    # ── 5. Секции ─────────────────────────────────────────────────────────────
    add_section(ROW['fiziki_sec'], ROW['fiziki_start'], ROW['fiziki_end'],
                ROW['fiziki_star'], CLR['fiziki'], CLR['fiziki_lt'])

    add_section(ROW['dr_sec'], ROW['dr_start'], ROW['dr_end'],
                ROW['dr_star'], CLR['dr'], CLR['dr_lt'])

    add_section(ROW['gruppy_sec'], ROW['gruppy_start'], ROW['gruppy_end'],
                ROW['gruppy_star'], CLR['gruppy'], CLR['gruppy_lt'])

    add_section(ROW['korp_sec'], ROW['korp_start'], ROW['korp_end'],
                ROW['korp_star'], CLR['korp'], CLR['korp_lt'])

    # ── 6. Разделители между секциями ────────────────────────────────────────
    for sep_row in [ROW['sep1'], ROW['sep2'], ROW['sep3']]:
        reqs.append(fmt_req(sheet_id, sep_row, sep_row, 1, TOTAL_COLS + 1,
                            cell_fmt(bg=CLR['sep_bg'])))

    return reqs


def main():
    print("=== Форматирование «2026 ✓» ===")
    ss = gc.open_by_key(SEG_SHEET_ID)
    sh = ss.worksheet(SHEET_NAME)
    sheet_id = sh.id
    print(f"  Sheet GID: {sheet_id}")

    reqs = build_requests(sheet_id)
    print(f"  Запросов к API: {len(reqs)}")

    ss.batch_update({"requests": reqs})
    print("  ✅ Форматирование применено")

    print(f"\nURL: https://docs.google.com/spreadsheets/d/{SEG_SHEET_ID}/edit#gid={sheet_id}")


if __name__ == '__main__':
    main()
