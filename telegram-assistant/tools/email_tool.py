"""
email_tool.py — поиск файлов на Mac и отправка по email через SMTP.
"""
import json
from pathlib import Path

import config

CONTACTS: dict[str, str] = getattr(config, "EMAIL_CONTACTS", {})


def find_contact(name: str) -> str | None:
    name_lower = name.lower()
    for k, v in CONTACTS.items():
        if k.lower() == name_lower:
            return v
    for k, v in CONTACTS.items():
        if name_lower in k.lower() or k.lower() in name_lower:
            return v
    return None


def search_files(query: str) -> str:
    index_path = Path(getattr(config, "FILE_INDEX_PATH", "/home/parser/bots/assistant/data/file_index.json"))
    if not index_path.exists():
        return "Индекс файлов не найден. Mac-индексер ещё не запускался или файл не синхронизирован."

    data = json.loads(index_path.read_text(encoding="utf-8"))
    query_lower = query.lower()

    matches = [
        f for f in data.get("files", [])
        if query_lower in f["name"].lower() or query_lower in f.get("snippet", "").lower()
    ]

    if not matches:
        return f"Файлы по запросу «{query}» не найдены. Индекс от {data.get('indexed_at', '?')}."

    lines = [f"Найдено {len(matches)} файл(ов):"]
    for i, f in enumerate(matches[:5], 1):
        lines.append(f"{i}. {f['name']} ({f['size_mb']} MB, изменён {f['modified'][:10]})\n   {f['path']}")
    if len(matches) > 5:
        lines.append(f"... и ещё {len(matches) - 5}")
    return "\n".join(lines)


def send_file_email(file_path: str, to_name: str, subject: str = "") -> str:
    if "@" in to_name:
        to_email = to_name
    else:
        to_email = find_contact(to_name)
        if not to_email:
            contacts_list = ", ".join(CONTACTS.keys()) or "список пуст"
            return f"Контакт «{to_name}» не найден. Известные контакты: {contacts_list}"

    request_path = Path(getattr(config, "FILE_REQUEST_PATH", "/home/parser/bots/assistant/data/file_request.json"))
    request = {
        "status": "pending",
        "file_path": file_path,
        "to_email": to_email,
        "to_name": to_name,
        "subject": subject or Path(file_path).name,
        "from_email": getattr(config, "MAIL_FROM", ""),
    }
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"Запрос создан. Файл «{Path(file_path).name}» будет отправлен на {to_email}. Mac подхватит в течение 2 минут."


def check_send_status() -> str:
    request_path = Path(getattr(config, "FILE_REQUEST_PATH", "/home/parser/bots/assistant/data/file_request.json"))
    if not request_path.exists():
        return "Активных запросов на отправку нет."
    data = json.loads(request_path.read_text(encoding="utf-8"))
    fname = Path(data.get("file_path", "?")).name
    to = data.get("to_email", "?")
    status = data.get("status", "?")
    if status == "pending":
        return f"Ожидание: «{fname}» → {to}. Mac ещё не обработал запрос."
    elif status == "done":
        return f"Отправлено: «{fname}» → {to}."
    elif status == "error":
        return f"Ошибка отправки «{fname}»: {data.get('error', 'неизвестно')}"
    return f"Статус: {status}"
