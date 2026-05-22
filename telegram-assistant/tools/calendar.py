from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build

_MSK = ZoneInfo("Europe/Moscow")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def _service(sa_json: str):
    creds = service_account.Credentials.from_service_account_file(sa_json, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)

def get_schedule_for_date(calendar_id: str, sa_json: str, date_iso: str) -> list[dict]:
    """Возвращает события на конкретную дату. date_iso: '2026-05-26'"""
    from datetime import date as date_type
    svc = _service(sa_json)
    d = date_type.fromisoformat(date_iso)
    day_start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=_MSK)
    day_end   = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=_MSK)
    result = svc.events().list(
        calendarId=calendar_id,
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])


def get_today_events(calendar_id: str, sa_json: str) -> list[dict]:
    """Возвращает события календаря на сегодня (МСК)."""
    svc = _service(sa_json)
    today = datetime.now(_MSK).date()
    day_start = datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=_MSK)
    day_end   = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=_MSK)
    result = svc.events().list(
        calendarId=calendar_id,
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])


def get_events(calendar_id: str, sa_json: str, days: int = 7) -> str:
    svc = _service(sa_json)
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=days)
    result = svc.events().list(
        calendarId=calendar_id,
        timeMin=now.isoformat(),
        timeMax=until.isoformat(),
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    items = result.get("items", [])
    if not items:
        return f"На ближайшие {days} дней событий нет."
    lines = []
    for ev in items:
        start = ev["start"].get("dateTime", ev["start"].get("date", ""))
        if "T" in start:
            dt = datetime.fromisoformat(start)
            start_str = dt.strftime("%d.%m %H:%M")
        else:
            start_str = start
        lines.append(f"• {start_str} — {ev.get('summary', '(без названия)')}")
    return "\n".join(lines)

def create_event(
    calendar_id: str,
    sa_json: str,
    title: str,
    start: str,
    end: str | None = None,
    description: str = "",
) -> str:
    """start/end: ISO8601, например 2026-05-20T18:00:00"""
    svc = _service(sa_json)
    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError:
        return f"Неверный формат start: {start}"
    if not end:
        end_dt = start_dt + timedelta(hours=1)
        end = end_dt.isoformat()
    tz = "Europe/Moscow"
    event = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start, "timeZone": tz},
        "end": {"dateTime": end, "timeZone": tz},
    }
    created = svc.events().insert(calendarId=calendar_id, body=event).execute()
    link = created.get("htmlLink", "")
    return f"Событие «{title}» создано на {start_dt.strftime('%d.%m.%Y %H:%M')}. {link}"
