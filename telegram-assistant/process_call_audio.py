#!/usr/bin/env python3
"""
Автономная обработка аудиозаписи звонка.
Запускается на сервере через SSH из Mac-скрипта:
  ssh server "python3 /home/parser/bots/assistant/process_call_audio.py /tmp/recordings/file.amr"

Делает: транскрипция → саммари → извлечение договорённостей → уведомление пользователя
"""
import asyncio
import sys
import os
import json
import logging
import re
import subprocess
import tempfile

sys.path.insert(0, "/home/parser/bots/assistant")
import config
from openai import AsyncOpenAI
from groq import AsyncGroq
from tools.db import add_agreement, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ai_client = AsyncOpenAI(base_url=config.ROUTERAI_BASE_URL, api_key=config.ROUTERAI_API_KEY)
groq_client = AsyncGroq(api_key=config.GROQ_API_KEY)
USER_ID = next(iter(config.ALLOWED_USER_IDS))

GROQ_SUPPORTED = {".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".opus", ".wav", ".webm"}


def convert_to_mp3(filepath: str) -> str:
    """Конвертирует AMR/неподдерживаемый формат в MP3 через ffmpeg."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in GROQ_SUPPORTED:
        return filepath
    out = tempfile.mktemp(suffix=".mp3")
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", filepath, "-ar", "16000", "-ac", "1", "-b:a", "32k", out],
        capture_output=True, timeout=60
    )
    if r.returncode != 0 or not os.path.exists(out):
        log.error(f"ffmpeg failed: {r.stderr.decode()[:200]}")
        return filepath
    log.info(f"Конвертировано в MP3: {os.path.basename(out)}")
    return out


async def transcribe(filepath: str) -> str:
    converted = convert_to_mp3(filepath)
    filename = os.path.basename(converted)
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    mime = f"audio/{ext}" if ext != "mp3" else "audio/mpeg"
    with open(converted, "rb") as f:
        audio_data = f.read()
    if converted != filepath:
        os.unlink(converted)
    for model in ("whisper-large-v3-turbo", "whisper-large-v3"):
        try:
            resp = await groq_client.audio.transcriptions.create(
                model=model,
                file=(filename, audio_data, mime),
                language="ru",
            )
            return resp.text
        except Exception as e:
            log.warning(f"Groq {model} error: {e}")
    return ""


async def summarize(transcript: str, filename: str) -> str:
    if not transcript.strip():
        return "(транскрипция пуста)"
    resp = await ai_client.chat.completions.create(
        model=config.MODEL,
        messages=[
            {"role": "system", "content": (
                "Ты — ассистент, создающий краткое резюме телефонного разговора. "
                "Выдели главные темы, договорённости, задачи и вопросы. "
                "Пиши по-русски, кратко (3-7 пунктов)."
            )},
            {"role": "user", "content": f"Расшифровка звонка ({filename}):\n\n{transcript[:6000]}"},
        ],
        temperature=0.3,
        max_tokens=600,
    )
    return resp.choices[0].message.content or "(пустой ответ)"


async def extract_agreements(summary: str) -> list[str]:
    resp = await ai_client.chat.completions.create(
        model=config.MODEL,
        messages=[
            {"role": "system", "content": (
                "Извлеки конкретные задачи и договорённости из резюме звонка. "
                "Верни JSON-массив: [{\"text\": \"...\"}]. "
                "Только конкретные действия (кто что должен сделать). Если нечего — верни []."
            )},
            {"role": "user", "content": summary},
        ],
        temperature=0.1,
        max_tokens=400,
    )
    raw = resp.choices[0].message.content or "[]"
    raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
    try:
        items = json.loads(raw)
        return [i["text"] for i in items if isinstance(i, dict) and i.get("text")]
    except Exception:
        return []


async def notify_user(text: str):
    import httpx
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={
            "chat_id": USER_ID,
            "text": text,
            "parse_mode": "HTML",
        })


async def main(filepath: str):
    if not os.path.exists(filepath):
        log.error(f"Файл не найден: {filepath}")
        sys.exit(1)

    filename = os.path.basename(filepath)
    # Извлекаем номер из имени: phone_YYYYMMDD-HHMMSS__NUMBER.amr
    parts = os.path.splitext(filename)[0].split("__")
    phone_number = parts[1] if len(parts) > 1 else None

    log.info(f"Транскрипция: {filename}")
    transcript = await transcribe(filepath)
    if not transcript.strip():
        log.warning("Транскрипция пустая — пропускаем")
        return

    log.info(f"Текст ({len(transcript)} симв) → саммари")
    summary = await summarize(transcript, filename)

    agreements = await extract_agreements(summary)
    log.info(f"Договорённостей: {len(agreements)}")

    init_db()
    for text in agreements:
        add_agreement(text, source="call")

    # Формируем сообщение пользователю
    phone_str = f"\n📱 Номер: {phone_number}" if phone_number else ""
    agr_str = ""
    if agreements:
        agr_str = "\n\n📋 <b>Договорённости (войдут в 22:00 дайджест):</b>\n" + "\n".join(f"• {a}" for a in agreements)

    msg = f"📞 <b>Звонок обработан</b>{phone_str}\n\n{summary}{agr_str}"
    await notify_user(msg)
    log.info("Готово")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: process_call_audio.py <audio_file>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
