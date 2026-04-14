"""
Запись данных в Google Sheets через gspread.
Два листа: «Все объявления» и «История изменений».
Условное форматирование: приоритет=зелёный, изменено=жёлтый, без площади=серый.
"""
import json
from datetime import datetime
from typing import Optional
from loguru import logger

import config
import database as db

# Цвета для условного форматирования (RGB 0–1)
COLOR_PRIORITY = {"red": 0.85, "green": 0.97, "blue": 0.85}     # светло-зелёный
COLOR_CHANGED  = {"red": 1.0,  "green": 0.97, "blue": 0.80}     # светло-жёлтый
COLOR_UNKNOWN  = {"red": 0.90, "green": 0.90, "blue": 0.90}     # светло-серый
COLOR_WHITE    = {"red": 1.0,  "green": 1.0,  "blue": 1.0}

# Заголовки листа «Все объявления»
HEADERS = [
    "Статус", "Источник", "Город", "Заголовок",
    "Площадь м²", "Цена руб", "Прибыль/мес", "Окупаемость мес",
    "Расположение", "Продавец", "Дата публикации",
    "Первый раз найдено", "Изменения", "Ссылка",
]

HISTORY_HEADERS = [
    "Дата изменения", "Источник", "Город", "Заголовок",
    "Что изменилось", "Было", "Стало", "Ссылка",
]


def _get_client():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(config.GOOGLE_CREDENTIALS_FILE), scopes=scopes)
    return gspread.authorize(creds)


def _fmt_money(val: Optional[float]) -> str:
    if val is None:
        return ""
    return f"{val:,.0f}".replace(",", " ")


def _fmt_area(val: Optional[float]) -> str:
    return f"{val:.0f}" if val is not None else ""


def _status_label(row) -> str:
    if row["status"] == "снято":
        return "📭 Снято"
    change_log = json.loads(row["change_log"] or "[]")
    if change_log:
        return "🔄 Изменено"
    if row["priority_flag"]:
        return "⭐ Приоритет"
    if row["area_unknown_flag"]:
        return "❓ Нет площади"
    return "✅ Активно"


def _row_color(row) -> dict:
    change_log = json.loads(row["change_log"] or "[]")
    if change_log:
        return COLOR_CHANGED
    if row["priority_flag"]:
        return COLOR_PRIORITY
    if row["area_unknown_flag"]:
        return COLOR_UNKNOWN
    return COLOR_WHITE


def _changes_summary(row) -> str:
    change_log = json.loads(row["change_log"] or "[]")
    if not change_log:
        return ""
    last = change_log[-1]
    date = last.get("changed_at", "")[:10]
    return f"{date}: {last.get('field')} {last.get('old')} → {last.get('new')}"


def update_sheets() -> None:
    """Полное обновление таблицы из БД."""
    if not config.GOOGLE_SPREADSHEET_ID:
        logger.warning("GOOGLE_SPREADSHEET_ID не задан — пропускаем Google Sheets")
        return
    if not config.GOOGLE_CREDENTIALS_FILE.exists():
        logger.warning("credentials.json не найден — пропускаем Google Sheets")
        return

    try:
        client = _get_client()
        spreadsheet = client.open_by_key(config.GOOGLE_SPREADSHEET_ID)
        _update_all_listings_sheet(spreadsheet)
        _update_history_sheet(spreadsheet)
        logger.info("Google Sheets обновлён")
    except Exception as e:
        logger.error("Ошибка обновления Google Sheets: {}", e)
        raise


def _get_or_create_sheet(spreadsheet, title: str):
    try:
        return spreadsheet.worksheet(title)
    except Exception:
        return spreadsheet.add_worksheet(title=title, rows=2000, cols=20)


def _update_all_listings_sheet(spreadsheet) -> None:
    import gspread

    ws = _get_or_create_sheet(spreadsheet, config.SHEET_ALL_LISTINGS)
    listings = db.get_all_active()

    # Строим данные
    rows = [HEADERS]
    row_colors = [None]  # заголовок — без цвета

    for listing in listings:
        rows.append([
            _status_label(listing),
            listing["source"],
            listing["city"] or "",
            listing["title"] or "",
            _fmt_area(listing["area_m2"]),
            _fmt_money(listing["price_rub"]),
            _fmt_money(listing["profit_month"]),
            f"{listing['payback_months']:.0f}" if listing["payback_months"] else "",
            listing["location_type"] or "",
            listing["seller_type"] or "",
            (listing["published_at"] or "")[:10],
            (listing["first_seen_at"] or "")[:10],
            _changes_summary(listing),
            listing["url"] or "",
        ])
        row_colors.append(_row_color(listing))

    # Очищаем и записываем
    ws.clear()
    ws.update("A1", rows, value_input_option="RAW")

    # Заморозка заголовка
    ws.freeze(rows=1)

    # Форматирование заголовка: жирный
    ws.format("A1:N1", {"textFormat": {"bold": True}})

    # Цвет строк (пакетный запрос для скорости)
    requests_body = []
    sheet_id = ws._properties["sheetId"]

    for i, color in enumerate(row_colors[1:], start=1):  # i=0 — заголовок
        if color is None:
            continue
        requests_body.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": i,
                    "endRowIndex": i + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(HEADERS),
                },
                "cell": {"userEnteredFormat": {"backgroundColor": color}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        })

    if requests_body:
        spreadsheet.batch_update({"requests": requests_body})

    logger.debug("Лист '{}' обновлён: {} строк", config.SHEET_ALL_LISTINGS, len(rows) - 1)


def _update_history_sheet(spreadsheet) -> None:
    ws = _get_or_create_sheet(spreadsheet, config.SHEET_HISTORY)
    listings = db.get_all_active()

    rows = [HISTORY_HEADERS]
    for listing in listings:
        change_log = json.loads(listing["change_log"] or "[]")
        for ch in change_log:
            rows.append([
                (ch.get("changed_at") or "")[:19],
                listing["source"],
                listing["city"] or "",
                listing["title"] or "",
                ch.get("field", ""),
                str(ch.get("old", "")),
                str(ch.get("new", "")),
                listing["url"] or "",
            ])

    ws.clear()
    ws.update("A1", rows, value_input_option="RAW")
    ws.freeze(rows=1)
    ws.format("A1:H1", {"textFormat": {"bold": True}})

    logger.debug("Лист '{}' обновлён: {} строк", config.SHEET_HISTORY, len(rows) - 1)
