#!/usr/bin/env python3
"""
sheets_query.py — Голосовые запросы к Google Sheets.

Использование:
  python3 ~/bin/sheets_query.py "какая выручка Монблан за прошлую неделю?"
  python3 ~/bin/sheets_query.py "сколько гостей Монблан в мае?"
  python3 ~/bin/sheets_query.py "загрузка Губаха на этой неделе"
"""
import sys
import os
import json
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ── Конфиги таблиц ────────────────────────────────────────────
SHEETS = {
    "monblan": {
        "id": "1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI",
        "sa": "/Users/user/.config/google/monblan_service_account.json",
        "worksheets": {
            "weekly": "ЕжеНедельно",
            "daily": "ЕжеДневно",
            "monthly": "ЕжеМесячный",
            "dashboard_w": "Дашборд ЕН",
            "dashboard_m": "Дашборд ЕМ",
        },
        "keywords": ["монблан", "ресторан", "monblan"],
    },
    "gubaha_finance": {
        "id": "1Ohm7tst750zDzSeIewJFj_cPC6vl0-5J0UiuNfZvY_k",
        "sa": "/Users/user/.config/google/aihotel_service_account.json",
        "worksheets": {
            "current_2026": "2026",
            "current_2025": "2025",
            "digest": "Дайджест",
            "analysis": "Анализ",
        },
        "keywords": ["губаха", "отель", "курорт", "загрузка", "бронь", "заезд"],
    },
    "gubaha_strategy": {
        "id": "11eaWcbY1pFMfniACcpZkodJgLOzTRpbXmyejSK9LEQ4",
        "sa": "/Users/user/.config/google/aihotel_service_account.json",
        "worksheets": {
            "tasks": "Задачи недели",
            "goals": "Цели",
        },
        "keywords": ["задачи", "kpi", "стратег", "цели"],
    },
}

ROUTERAI_BASE = "https://routerai.ru/api/v1"
ROUTERAI_KEY = "sk-f61V-MK6PAPbGrYSYFAMEnU4i9AtrP0-"
MODEL = "deepseek/deepseek-v4-pro"


def _svc(sa_path: str):
    creds = Credentials.from_service_account_file(
        sa_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _read_range(sa_path: str, sheet_id: str, range_str: str) -> list:
    result = _svc(sa_path).spreadsheets().values().get(
        spreadsheetId=sheet_id, range=range_str
    ).execute()
    return result.get("values", [])


def _detect_source(query: str) -> str:
    q = query.lower()
    if any(k in q for k in SHEETS["monblan"]["keywords"]):
        return "monblan"
    if any(k in q for k in SHEETS["gubaha_strategy"]["keywords"]):
        return "gubaha_strategy"
    return "gubaha_finance"


def _get_monblan_weekly(query: str) -> str:
    cfg = SHEETS["monblan"]
    data = _read_range(cfg["sa"], cfg["id"], f"{cfg['worksheets']['weekly']}!A1:CZ30")
    return _format_for_ai(data, query, "Монблан еженедельная таблица (строка 1 = год, строка 2 = №недели, строка 3 = даты, далее метрики)")


def _get_monblan_daily(query: str) -> str:
    cfg = SHEETS["monblan"]
    data = _read_range(cfg["sa"], cfg["id"], f"{cfg['worksheets']['daily']}!A1:AZ15")
    return _format_for_ai(data, query, "Монблан ежедневная таблица (строка 1 = даты, колонка A = метрики)")


def _get_monblan_monthly(query: str) -> str:
    cfg = SHEETS["monblan"]
    data = _read_range(cfg["sa"], cfg["id"], f"{cfg['worksheets']['monthly']}!A1:Z30")
    return _format_for_ai(data, query, "Монблан ежемесячная таблица")


def _get_gubaha_finance(query: str) -> str:
    cfg = SHEETS["gubaha_finance"]
    try:
        data = _read_range(cfg["sa"], cfg["id"], f"{cfg['worksheets']['digest']}!A1:D50")
        if data:
            return _format_for_ai(data, query, "Губаха финансовый дайджест")
    except Exception:
        pass
    data = _read_range(cfg["sa"], cfg["id"], f"{cfg['worksheets']['current_2026']}!A1:Z30")
    return _format_for_ai(data, query, "Губаха финансовые данные 2026")


def _get_gubaha_strategy(query: str) -> str:
    cfg = SHEETS["gubaha_strategy"]
    data = _read_range(cfg["sa"], cfg["id"], f"{cfg['worksheets']['tasks']}!A1:F50")
    return _format_for_ai(data, query, "Губаха задачи недели (колонки: Исполнитель, Блок, Задача, Результат, Как проверить, Срок)")


def _format_for_ai(table_data: list, query: str, context: str) -> str:
    """Передаёт данные таблицы в DeepSeek и получает ответ на вопрос."""
    import urllib.request

    rows_text = []
    for row in table_data[:40]:
        rows_text.append(" | ".join(str(c) for c in row[:20]))
    table_str = "\n".join(rows_text)
    today = datetime.now().strftime("%d.%m.%Y")

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": f"Ты аналитик. Сегодня {today}. Отвечай коротко и конкретно — только цифры и факты."},
            {"role": "user", "content": f"Данные: {context}\n\n{table_str}\n\nВопрос: {query}"}
        ],
        "max_tokens": 2000,   # DeepSeek V4 Pro тратит ~500-1500 на reasoning — нужен запас
        "temperature": 0.1,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{ROUTERAI_BASE}/chat/completions",
        data=data,
        headers={"Authorization": f"Bearer {ROUTERAI_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    msg = result["choices"][0]["message"]
    # DeepSeek V4 Pro: content может быть пустым если все токены ушли в reasoning
    content = (msg.get("content") or "").strip()
    if not content:
        # Фолбэк: берём последние 500 символов из reasoning (итог размышлений)
        reasoning = (msg.get("reasoning") or "").strip()
        content = reasoning[-500:] if reasoning else "Нет данных"
    return content


def query(question: str) -> str:
    q = question.lower()
    source = _detect_source(question)

    # Определяем нужный лист по ключевым словам в вопросе
    if source == "monblan":
        if any(w in q for w in ["месяц", "мес", "январ", "феврал", "март", "апрел", "май", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"]):
            return _get_monblan_monthly(question)
        elif any(w in q for w in ["сегодня", "вчера", "день", "дневн"]):
            return _get_monblan_daily(question)
        else:
            return _get_monblan_weekly(question)
    elif source == "gubaha_strategy":
        return _get_gubaha_strategy(question)
    else:
        return _get_gubaha_finance(question)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: sheets_query.py <вопрос>")
        sys.exit(1)
    question = " ".join(sys.argv[1:])
    try:
        print(query(question))
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
