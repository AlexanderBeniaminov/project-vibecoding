"""Реестр нежелательных тем: проверка перед генерацией + управление списком."""
import json

import openai

import config
import db

ai_client = openai.AsyncOpenAI(
    base_url=config.ROUTERAI_BASE_URL,
    api_key=config.ROUTERAI_API_KEY,
    timeout=30.0,
)

_CHECK_SYSTEM = (
    "Ты проверяешь, похожа ли новая тема поста на темы из блэклиста по смыслу "
    "(не только по словам). Ответь строго в JSON: "
    '{"matched": true/false, "matched_text": "точная строка блэклиста или пустая строка"}'
)


async def check_against_blacklist(idea_text: str) -> str | None:
    """Возвращает текст совпавшей записи блэклиста, либо None если совпадений нет."""
    entries = db.list_blacklist()
    if not entries:
        return None

    blacklist_text = "\n".join(f"- {e['text']}" for e in entries)
    user_prompt = f"Блэклист:\n{blacklist_text}\n\nНовая тема: {idea_text}"

    try:
        resp = await ai_client.chat.completions.create(
            model=config.MODEL,
            messages=[
                {"role": "system", "content": _CHECK_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=150,
            temperature=0,
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        if data.get("matched"):
            return data.get("matched_text") or idea_text
        return None
    except Exception:
        # Сбой проверки не должен блокировать генерацию — пропускаем тему дальше
        return None


def add_to_blacklist(text: str, mode: str, blocked_until: str | None = None, reason: str = "") -> int:
    return db.add_blacklist_entry(text, mode, blocked_until, reason)


def list_active() -> list[dict]:
    return db.list_blacklist()


def remove(entry_id: int):
    db.delete_blacklist_entry(entry_id)
