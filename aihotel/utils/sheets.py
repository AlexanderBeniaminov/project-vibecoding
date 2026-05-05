import os
import re
import json
import gspread
from google.oauth2.service_account import Credentials


def _read_multiline_env(key):
    env_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '.env'))
    if not os.path.exists(env_path):
        return None
    with open(env_path) as f:
        content = f.read()
    m = re.search(rf'^{re.escape(key)}=(.*?)(?=\n[A-Z][A-Z_]+=|\Z)', content, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else None


def get_client() -> gspread.Client:
    raw = os.environ.get('GOOGLE_CREDS_JSON', '')
    try:
        creds_info = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raw = _read_multiline_env('GOOGLE_CREDS_JSON') or ''
        creds_info = json.loads(raw)
    creds = Credentials.from_service_account_info(
        creds_info,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return gspread.Client(auth=creds)


def get_worksheet(client: gspread.Client, sheet_id: str, worksheet_name: str) -> gspread.Worksheet:
    return client.open_by_key(sheet_id).worksheet(worksheet_name)


COLORS = {
    'red':    {'red': 1.0,  'green': 0.8,  'blue': 0.8},
    'yellow': {'red': 1.0,  'green': 1.0,  'blue': 0.6},
    'green':  {'red': 0.78, 'green': 0.94, 'blue': 0.81},
    'white':  {'red': 1.0,  'green': 1.0,  'blue': 1.0},
}


def get_color_name(delta_pct: float) -> str:
    if delta_pct < -10:
        return 'red'
    elif delta_pct < -3:
        return 'yellow'
    elif delta_pct > 5:
        return 'green'
    return 'white'


def paint_cell(worksheet: gspread.Worksheet, cell: str, color_name: str) -> None:
    worksheet.format(cell, {'backgroundColor': COLORS[color_name]})


def get_flag(ws_status: gspread.Worksheet, key: str) -> str:
    records = ws_status.get_all_records()
    for row in records:
        if row.get('ключ') == key:
            return str(row.get('значение', 'нет'))
    return 'нет'


def set_flag(ws_status: gspread.Worksheet, key: str, value: str) -> None:
    all_values = ws_status.get_all_values()
    for i, row in enumerate(all_values):
        if row and row[0] == key:
            ws_status.update_cell(i + 1, 2, value)
            return


def reset_weekly_flags(ws_status: gspread.Worksheet, current_week: str) -> None:
    saved_week = get_flag(ws_status, 'неделя')
    if saved_week != current_week:
        print(f"Новая неделя {current_week} (была {saved_week}), сбрасываем флаги")
        set_flag(ws_status, 'неделя', current_week)
        for key in ['данные_внесены', 'анализ_готов', 'дайджест_записан', 'задачи_сформированы']:
            set_flag(ws_status, key, 'нет')
    else:
        print(f"Неделя {current_week} — флаги сохранены")
