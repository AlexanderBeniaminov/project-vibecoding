#!/usr/bin/env python3
"""
mail.py (alias: gmail.py) — Деловая почта ab@entens.ru через Mail.ru IMAP/SMTP.

Использование:
  python3 ~/bin/gmail.py compose "Виктор" "Закупки" "текст голосом"
  python3 ~/bin/gmail.py send --last
  python3 ~/bin/gmail.py send <draft_id>
  python3 ~/bin/gmail.py reply <uid> "текст ответа"
  python3 ~/bin/gmail.py forward <uid> "email или имя"
  python3 ~/bin/gmail.py digest
  python3 ~/bin/gmail.py search "ключевые слова"
"""
import sys
import os
import json
import imaplib
import smtplib
import email as email_lib
import email.header
import email.utils
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path

# ── Конфиг ────────────────────────────────────────────────────────
MAIL_CFG_PATH = Path.home() / ".config" / "mailru.json"
LAST_DRAFT_FILE = Path("/tmp") / "mail_last_draft.json"

def _cfg() -> dict:
    return json.loads(MAIL_CFG_PATH.read_text())

# ── Контакты (имя → email) ─────────────────────────────────────────
CONTACTS = {
    "виктор": "karpenko@entens.ru",
    "алексей": "ap@entens.ru",
    "катя": "info@entens.ru",
    "алексей личная": "aprosandeev@mail.ru",
    "себе": "ab@entens.ru",
    "сам себе": "ab@entens.ru",
}

# ── RouterAI ───────────────────────────────────────────────────────
ROUTERAI_BASE = "https://routerai.ru/api/v1"
ROUTERAI_KEY = "sk-f61V-MK6PAPbGrYSYFAMEnU4i9AtrP0-"
MODEL = "deepseek/deepseek-v4-pro"


# ── Helpers ────────────────────────────────────────────────────────
def _resolve_email(name_or_email: str) -> str:
    if "@" in name_or_email:
        return name_or_email
    key = name_or_email.lower().strip()
    if key in CONTACTS:
        return CONTACTS[key]
    for k, v in CONTACTS.items():
        if key in k or k in key:
            return v
    raise ValueError(f"Контакт не найден: '{name_or_email}'. Укажите email напрямую.")


def _decode_header(raw: str) -> str:
    """Декодирует MIME-заголовок (Base64/QP)."""
    parts = email.header.decode_header(raw or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _imap_connect() -> imaplib.IMAP4_SSL:
    cfg = _cfg()
    mail = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"])
    mail.login(cfg["email"], cfg["password"])
    return mail


def _smtp_send(to: str, subject: str, body: str, reply_to_msg_id: str = None) -> None:
    cfg = _cfg()
    from email.header import Header
    msg = MIMEText(body, "plain", "utf-8")
    # Кодируем From с кириллическим именем в Base64
    display_name = cfg.get("display_name", "")
    if display_name:
        from_header = f"{Header(display_name, 'utf-8').encode()} <{cfg['email']}>"
    else:
        from_header = cfg["email"]
    msg["From"] = from_header
    msg["To"] = to
    msg["Subject"] = Header(subject, "utf-8").encode()
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["MIME-Version"] = "1.0"
    if reply_to_msg_id:
        msg["In-Reply-To"] = reply_to_msg_id
        msg["References"] = reply_to_msg_id

    with smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"]) as server:
        server.login(cfg["email"], cfg["password"])
        server.sendmail(cfg["email"], [to], msg.as_string().encode("utf-8"))


def _extract_text(msg) -> str:
    """Извлекает текст из email.message.Message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
    else:
        charset = msg.get_content_charset() or "utf-8"
        return msg.get_payload(decode=True).decode(charset, errors="replace")
    return ""


# ── AI полировка письма ────────────────────────────────────────────
def _ai_compose(recipient_name: str, subject_hint: str, voice_text: str) -> tuple[str, str]:
    import urllib.request
    today = datetime.now().strftime("%d.%m.%Y")
    system = (
        "Ты помощник по деловой переписке. Пиши кратко, деловым стилем на русском. "
        f"Сегодня {today}. Отправитель — Александр Бениаминов (ab@entens.ru). "
        "Ответ — JSON: {\"subject\": \"тема\", \"body\": \"текст письма\"}"
    )
    user_msg = (
        f"Напиши деловое письмо.\nПолучатель: {recipient_name}\n"
        f"Тема/идея: {subject_hint}\nСодержание (голосом): {voice_text}\n\n"
        "Верни только JSON без пояснений."
    )
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
        "max_tokens": 1500,
        "temperature": 0.3,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{ROUTERAI_BASE}/chat/completions", data=data,
        headers={"Authorization": f"Bearer {ROUTERAI_KEY}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    msg = result["choices"][0]["message"]
    content = (msg.get("content") or "").strip() or (msg.get("reasoning") or "")[-1000:]
    try:
        clean = content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean)
        return parsed.get("subject", subject_hint), parsed.get("body", voice_text)
    except Exception:
        return subject_hint, content


# ── Compose (черновик) ─────────────────────────────────────────────
def compose(recipient: str, subject_hint: str, voice_text: str) -> str:
    to_email = _resolve_email(recipient)
    subject, body = _ai_compose(recipient, subject_hint, voice_text)

    # Сохраняем черновик в /tmp для последующей отправки
    draft_id = f"draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    LAST_DRAFT_FILE.write_text(json.dumps({
        "draft_id": draft_id,
        "to": to_email,
        "subject": subject,
        "body": body,
        "created": datetime.now().isoformat(),
    }))

    return (
        f"📧 Черновик готов (ID: {draft_id})\n"
        f"Кому: {to_email}\n"
        f"Тема: {subject}\n\n"
        f"{body}\n\n"
        f"──────────────────────\n"
        f"Отправить? → python3 ~/bin/gmail.py send --last\n"
        f"Отменить? → удали файл /tmp/mail_last_draft.json"
    )


# ── Send ───────────────────────────────────────────────────────────
def send_draft(draft_id_or_last: str) -> str:
    if not LAST_DRAFT_FILE.exists():
        return "❌ Нет сохранённого черновика. Сначала выполните compose."
    info = json.loads(LAST_DRAFT_FILE.read_text())
    _smtp_send(info["to"], info["subject"], info["body"])
    LAST_DRAFT_FILE.unlink(missing_ok=True)
    return f"✅ Письмо отправлено!\nКому: {info['to']}\nТема: {info['subject']}"


# ── Cancel draft ───────────────────────────────────────────────────
def cancel_draft() -> str:
    LAST_DRAFT_FILE.unlink(missing_ok=True)
    return "🗑 Черновик удалён."


# ── Reply ──────────────────────────────────────────────────────────
def reply(uid: str, voice_text: str) -> str:
    mail = _imap_connect()
    mail.select("INBOX")
    status, data = mail.fetch(uid, "(RFC822)")
    mail.logout()
    if status != "OK":
        return f"❌ Письмо UID {uid} не найдено."

    raw_email = data[0][1]
    msg = email_lib.message_from_bytes(raw_email)
    original_from = _decode_header(msg.get("From", ""))
    original_subject = _decode_header(msg.get("Subject", ""))
    msg_id = msg.get("Message-ID", "")

    to_email = email.utils.parseaddr(original_from)[1]
    subject = original_subject if original_subject.startswith("Re:") else f"Re: {original_subject}"
    _, body = _ai_compose(original_from, subject, voice_text)

    draft_id = f"reply_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    LAST_DRAFT_FILE.write_text(json.dumps({
        "draft_id": draft_id,
        "to": to_email,
        "subject": subject,
        "body": body,
        "reply_to_msg_id": msg_id,
        "created": datetime.now().isoformat(),
    }))

    return (
        f"📧 Ответ готов (ID: {draft_id})\n"
        f"Кому: {to_email}\n"
        f"Тема: {subject}\n\n"
        f"{body}\n\n"
        f"──────────────────────\n"
        f"Отправить? → python3 ~/bin/gmail.py send --last"
    )


# ── Forward ────────────────────────────────────────────────────────
def forward(uid: str, to_name_or_email: str) -> str:
    mail = _imap_connect()
    mail.select("INBOX")
    status, data = mail.fetch(uid, "(RFC822)")
    mail.logout()
    if status != "OK":
        return f"❌ Письмо UID {uid} не найдено."

    raw_email = data[0][1]
    msg = email_lib.message_from_bytes(raw_email)
    original_subject = _decode_header(msg.get("Subject", ""))
    original_from = _decode_header(msg.get("From", ""))
    original_date = msg.get("Date", "")
    body_text = _extract_text(msg)[:3000]

    to_email = _resolve_email(to_name_or_email)
    subject = f"Fwd: {original_subject}" if not original_subject.startswith("Fwd:") else original_subject
    fwd_body = (
        f"---------- Forwarded message ----------\n"
        f"From: {original_from}\nDate: {original_date}\n"
        f"Subject: {original_subject}\n\n{body_text}"
    )

    draft_id = f"fwd_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    LAST_DRAFT_FILE.write_text(json.dumps({
        "draft_id": draft_id, "to": to_email, "subject": subject, "body": fwd_body,
        "created": datetime.now().isoformat(),
    }))

    return (
        f"📧 Пересылка готова (ID: {draft_id})\n"
        f"Кому: {to_email}\nТема: {subject}\n\n"
        f"Отправить? → python3 ~/bin/gmail.py send --last"
    )


# ── Digest ─────────────────────────────────────────────────────────
def digest() -> str:
    import urllib.request
    mail = _imap_connect()
    mail.select("INBOX")

    # Письма за последние 24 часа
    since_date = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
    status, uids = mail.search(None, f'(SINCE "{since_date}" UNSEEN)')
    mail_uids = uids[0].split() if uids[0] else []

    if not mail_uids:
        mail.logout()
        return "📭 Нет новых писем за последние 24 часа."

    summaries = []
    for uid in mail_uids[-15:]:  # последние 15
        status, data = mail.fetch(uid, "(RFC822.HEADER BODY.PEEK[TEXT]<0.300>)")
        if status != "OK":
            continue
        msg = email_lib.message_from_bytes(data[0][1])
        summaries.append({
            "uid": uid.decode(),
            "from": _decode_header(msg.get("From", "?"))[:60],
            "subject": _decode_header(msg.get("Subject", "(без темы)"))[:80],
            "date": msg.get("Date", "")[:20],
        })
    mail.logout()

    today = datetime.now().strftime("%d.%m.%Y")
    inbox_text = "\n".join(
        f"[{i+1}] UID:{s['uid']} От:{s['from']} Тема:{s['subject']}"
        for i, s in enumerate(summaries)
    )
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": f"Ты помощник. Сегодня {today}. Кратко по-русски."},
            {"role": "user", "content": (
                f"Входящие письма:\n{inbox_text}\n\n"
                "Выдели только требующие ответа или действия. "
                "Для каждого: от кого, тема, что нужно сделать, UID письма. "
                "Если таких нет — скажи об этом."
            )},
        ],
        "max_tokens": 1500, "temperature": 0.2,
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{ROUTERAI_BASE}/chat/completions", data=data_bytes,
        headers={"Authorization": f"Bearer {ROUTERAI_KEY}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    msg_res = result["choices"][0]["message"]
    content = (msg_res.get("content") or "").strip() or (msg_res.get("reasoning") or "")[-800:]

    return f"📬 Дайджест ({len(summaries)} непрочитанных):\n\n{content}"


# ── Search ─────────────────────────────────────────────────────────
def search(query: str) -> str:
    mail = _imap_connect()
    mail.select("INBOX")

    # Поиск с явным charset=UTF-8 для кириллицы
    try:
        status, uids = mail.search("UTF-8", f'(SUBJECT "{query}")'.encode("utf-8"))
    except Exception:
        status, uids = mail.search(None, "ALL")
        # Фолбэк — пустой
        uids = [b""]
    if not uids[0]:
        try:
            status, uids = mail.search("UTF-8", f'(FROM "{query}")'.encode("utf-8"))
        except Exception:
            uids = [b""]

    mail_uids = (uids[0].split() if uids[0] else [])[-10:]
    if not mail_uids:
        mail.logout()
        return f"Писем по запросу '{query}' не найдено."

    lines = [f"🔍 Найдено {len(mail_uids)} писем по '{query}':"]
    for uid in reversed(mail_uids):
        status, data = mail.fetch(uid, "(RFC822.HEADER)")
        if status != "OK":
            continue
        msg = email_lib.message_from_bytes(data[0][1])
        date = msg.get("Date", "")[:20]
        from_ = _decode_header(msg.get("From", "?"))[:50]
        subj = _decode_header(msg.get("Subject", "(без темы)"))[:60]
        lines.append(f"  • [{date}] {from_} — {subj}  (UID: {uid.decode()})")
    mail.logout()
    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    try:
        if cmd == "compose" and len(sys.argv) >= 5:
            print(compose(sys.argv[2], sys.argv[3], sys.argv[4]))
        elif cmd == "send" and len(sys.argv) >= 3:
            print(send_draft(sys.argv[2]))
        elif cmd == "reply" and len(sys.argv) >= 4:
            print(reply(sys.argv[2], sys.argv[3]))
        elif cmd == "forward" and len(sys.argv) >= 4:
            print(forward(sys.argv[2], sys.argv[3]))
        elif cmd == "cancel":
            print(cancel_draft())
        elif cmd == "digest":
            print(digest())
        elif cmd == "search" and len(sys.argv) >= 3:
            print(search(sys.argv[2]))
        else:
            print("Неверная команда. Запустите без аргументов для справки.")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
