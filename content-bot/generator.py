"""Генерация постов и идей через DeepSeek (RouterAI)."""
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import openai

import config

_MSK = ZoneInfo("Europe/Moscow")

ai_client = openai.AsyncOpenAI(
    base_url=config.ROUTERAI_BASE_URL,
    api_key=config.ROUTERAI_API_KEY,
    timeout=90.0,
)

# ── DSML-очистка (паттерн из assistant_bot.py:_clean_dsml) ────
_D = r'(?:[|｜]\s*)+'
_DSML_CLOSED_RE = re.compile(rf'<\s*{_D}DSML\s*{_D}tool_calls\s*>.*?</\s*{_D}DSML\s*{_D}tool_calls\s*>', re.DOTALL)
_DSML_OPEN_RE   = re.compile(rf'<\s*{_D}DSML\s*{_D}tool_calls\s*>.*', re.DOTALL)
_DSML_TAG_RE    = re.compile(rf'<\s*/?\s*{_D}DSML\s*{_D}[^>]*>', re.DOTALL)


def _clean_json_response(text: str) -> str:
    text = _DSML_CLOSED_RE.sub('', text)
    text = _DSML_OPEN_RE.sub('', text)
    text = _DSML_TAG_RE.sub('', text)
    # Модель иногда оборачивает JSON в ```json ... ```
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip(), flags=re.MULTILINE)
    return text.strip()


def _load_knowledge() -> str:
    knowledge_dir = Path(config.KNOWLEDGE_DIR)
    parts = []
    for fname in ["tone-of-voice.md", "audience.md", "business.md"]:
        fpath = knowledge_dir / fname
        if fpath.exists():
            parts.append(fpath.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)


KNOWLEDGE = _load_knowledge()

_VARIANTS_SYSTEM = (
    "Ты помогаешь Александру Бениаминову писать посты для Telegram-канала «ИИндустрия Развлечений».\n\n"
    f"{KNOWLEDGE}\n\n"
    "Отвечай строго в формате JSON-массива без пояснений вне JSON."
)

_VARIANTS_USER_TEMPLATE = """Тема поста: {idea_text}
{rubric_instruction}
Напиши 3 варианта поста для Telegram-канала «ИИндустрия Развлечений».

Требования к каждому варианту:
- Определи целевую аудиторию: «Владельцы бизнеса» или «Партнёры-инвесторы»
- Первые 2 строки должны цеплять до обрезки (без инфобизнес-клише)
- Разные призывы к действию в разных вариантах
- Соблюдай тон голоса из инструкций

Требования ко ВСЕМ вариантам:
- От первого лица, экспертным тоном
- Без приватных и семейных тем
- Без вопросов к читателю, требующих ответа

Форматы вариантов — строго разные:
- Вариант 1: кейс с измеримым результатом
- Вариант 2: экспертный разбор или профессиональная история из практики
- Вариант 3: тезис-мнение с чёткой позицией по теме ИИ/бизнеса

Ответь строго в JSON:
[
  {{"variant": 1, "audience": "Владельцы бизнеса", "format": "кейс с измеримым результатом", "text": "..."}},
  {{"variant": 2, "audience": "Партнёры-инвесторы", "format": "экспертный разбор", "text": "..."}},
  {{"variant": 3, "audience": "Владельцы бизнеса", "format": "тезис-мнение", "text": "..."}}
]"""

_LIFEHACK_INSTRUCTION = (
    "\nЭто пост рубрики «Лайфхак недели» — формат: конкретный промт/инструмент/техника, "
    "которую читатель может применить прямо сейчас. Длина 1000–1800 символов.\n"
)


async def generate_variants(idea_text: str, rubric: str = "regular") -> list[dict]:
    rubric_instruction = _LIFEHACK_INSTRUCTION if rubric == "lifehack" else ""
    user_prompt = _VARIANTS_USER_TEMPLATE.format(idea_text=idea_text, rubric_instruction=rubric_instruction)

    resp = await ai_client.chat.completions.create(
        model=config.MODEL,
        messages=[
            {"role": "system", "content": _VARIANTS_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=3000,
        temperature=0.8,
    )
    content = _clean_json_response(resp.choices[0].message.content or "[]")
    return json.loads(content)


_STRUCTURE_SYSTEM = (
    "Ты структурируешь голосовую или текстовую идею для поста в заголовок и краткое описание. "
    'Ответь строго в JSON: {"title": "...", "description": "..."} '
    "где title — короткая тема (3-7 слов), description — 1-2 строки сути."
)


async def structure_idea(raw_text: str) -> dict:
    resp = await ai_client.chat.completions.create(
        model=config.MODEL,
        messages=[
            {"role": "system", "content": _STRUCTURE_SYSTEM},
            {"role": "user", "content": raw_text},
        ],
        max_tokens=300,
        temperature=0.3,
    )
    content = _clean_json_response(resp.choices[0].message.content or "{}")
    return json.loads(content)


_TOPICS_SYSTEM = (
    "Ты предлагаешь темы постов для Telegram-канала «ИИндустрия Развлечений».\n\n"
    f"{KNOWLEDGE}\n\n"
    "Отвечай строго в формате JSON-массива без пояснений вне JSON."
)

_TOPICS_USER_TEMPLATE = """Свежие новости ниши (используй как контекст, не пересказывай напрямую):
{search_context}

Уже опубликованные темы (НЕ повторять и не предлагать близкие по смыслу):
{published}

Заблокированные темы (НЕ предлагать):
{blacklisted}

Текущий месяц: {month}

Предложи 5 новых тем для постов с учётом тона голоса, аудитории и сезона.
Ответь строго в JSON:
[
  {{"topic": "Краткая тема", "description": "1-2 строки о чём пост"}},
  ...
]"""


async def generate_topic_suggestions(
    search_context: str, published_history: list[str], blacklisted: list[str]
) -> list[dict]:
    month_name = datetime.now(_MSK).strftime("%B %Y")
    user_prompt = _TOPICS_USER_TEMPLATE.format(
        search_context=search_context or "(поиск недоступен — используй базу знаний)",
        published="\n".join(f"- {t}" for t in published_history) or "(пока нет)",
        blacklisted="\n".join(f"- {t}" for t in blacklisted) or "(пусто)",
        month=month_name,
    )
    resp = await ai_client.chat.completions.create(
        model=config.MODEL,
        messages=[
            {"role": "system", "content": _TOPICS_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1500,
        temperature=0.9,
    )
    content = _clean_json_response(resp.choices[0].message.content or "[]")
    return json.loads(content)


_CORRECTION_SYSTEM = (
    "Ты дорабатываешь пост по правке автора. Сохраняй тон голоса и структуру. "
    "Ответь только новым текстом поста, без пояснений."
)


async def apply_correction(original_text: str, correction: str) -> str:
    resp = await ai_client.chat.completions.create(
        model=config.MODEL,
        messages=[
            {"role": "system", "content": _CORRECTION_SYSTEM},
            {"role": "user", "content": f"Исходный пост:\n{original_text}\n\nПравка:\n{correction}"},
        ],
        max_tokens=1500,
        temperature=0.6,
    )
    return _clean_json_response(resp.choices[0].message.content or "").strip() or original_text
