#!/usr/bin/env python3
"""
delegate_to_planner.py — Делегирование задачи из Помощника в Планировщика.

Планировщик (@assistent_beniaminova_bot) работает 24/7 на VPS и умеет:
напоминания, Calendar, утренний дайджест.

Использование:
  python3 ~/bin/delegate_to_planner.py "напомни завтра в 10:00 позвонить Виктору"
  python3 ~/bin/delegate_to_planner.py "добавь в календарь встречу с Алексеем в пятницу в 14:00"
"""
import sys
import json
import urllib.request

# Токен Планировщика (@assistent_beniaminova_bot)
PLANNER_BOT_TOKEN = "7778266500:AAFT-5f7eJOMIBIR5o8j3RHBkhzIGNxS0F8"
USER_ID = 994743403


def delegate(task: str) -> str:
    """Отправляет задачу в чат Планировщика от имени бота с префиксом."""
    message = f"📨 *Делегировано из Помощника:*\n\n{task}"

    url = f"https://api.telegram.org/bot{PLANNER_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": USER_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    if result.get("ok"):
        return f"✅ Передано в Планировщика: {task}"
    else:
        return f"❌ Ошибка: {result.get('description', 'неизвестная ошибка')}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: delegate_to_planner.py <задача>")
        sys.exit(1)
    task = " ".join(sys.argv[1:])
    try:
        print(delegate(task))
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
