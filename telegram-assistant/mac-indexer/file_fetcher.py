#!/usr/bin/env python3
"""
file_fetcher.py — проверяет запросы на отправку файлов с Mac.
Запускается каждые 2 минуты через LaunchAgent.
"""
import json
import smtplib
import subprocess
import sys
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ── Пути ──────────────────────────────────────────────────────
REMOTE_REQUEST = "server:/home/parser/bots/assistant/data/file_request.json"
LOCAL_REQUEST = Path("~/file-indexer/file_request.json").expanduser()
EMAIL_CONFIG = Path("~/file-indexer/email_config.json").expanduser()
LOG_FILE = Path("~/file-indexer/fetcher.log").expanduser()


def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _push_request(req: dict):
    LOCAL_REQUEST.write_text(json.dumps(req, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run(["rsync", "-az", str(LOCAL_REQUEST), REMOTE_REQUEST],
                   capture_output=True, text=True)


def _send_email(cfg: dict, to_addr: str, subject: str, file_path: Path):
    msg = MIMEMultipart()
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText("Файл отправлен через ассистента Александра.", "plain", "utf-8"))

    with open(file_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
    msg.attach(part)

    with smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"]) as server:
        server.login(cfg["login"], cfg["password"])
        server.sendmail(cfg["from_addr"], to_addr, msg.as_string())


def main():
    # Скачиваем запрос с сервера
    result = subprocess.run(
        ["rsync", "-az", REMOTE_REQUEST, str(LOCAL_REQUEST)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not LOCAL_REQUEST.exists():
        return  # нет запроса — нормально

    try:
        req = json.loads(LOCAL_REQUEST.read_text(encoding="utf-8"))
    except Exception:
        return

    if req.get("status") != "pending":
        return

    _log(f"Запрос: {req['file_path']} → {req['to_email']}")

    file_path = Path(req["file_path"])
    if not file_path.exists():
        _log(f"Файл не найден: {file_path}")
        req["status"] = "error"
        req["error"] = f"Файл не найден: {file_path}"
        _push_request(req)
        return

    if not EMAIL_CONFIG.exists():
        _log("email_config.json не найден, пропускаем")
        return

    cfg = json.loads(EMAIL_CONFIG.read_text(encoding="utf-8"))

    try:
        _send_email(cfg, req["to_email"], req.get("subject", file_path.name), file_path)
        req["status"] = "done"
        _log(f"Отправлено: {file_path.name} → {req['to_email']}")
    except Exception as e:
        req["status"] = "error"
        req["error"] = str(e)
        _log(f"Ошибка: {e}")

    _push_request(req)


if __name__ == "__main__":
    main()
