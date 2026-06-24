"""Генерация постов и идей через DeepSeek (RouterAI)."""
import json
import logging
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


def _safe_json_loads(text: str) -> list:
    """json.loads с фallback через json_repair — DeepSeek иногда не экранирует кавычки."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logging.warning(f"[generator] json.loads failed ({e}), trying json_repair. Raw: {text[:300]}")
    try:
        from json_repair import repair_json
        repaired = repair_json(text)
        result = json.loads(repaired)
        logging.info(f"[generator] json_repair succeeded, got {len(result)} items")
        return result
    except Exception as e:
        logging.error(f"[generator] json_repair also failed: {e}. Raw: {text[:300]}")
    return []


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

# Расширенная палитра форматов — чередуем чтобы читателям было разнообразно
_ALL_FORMATS = [
    "кейс с измеримым результатом",
    "экспертный разбор",
    "тезис-мнение с чёткой позицией",
    "личная история или разбор ошибки",
    "сравнение до/после",
    "разбор тренда или новости с авторской позицией",
    "мини-инструкция или чек-лист",
    "цитата или наблюдение + комментарий",
]

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
- Длина каждого варианта: до 700 символов (порог дочитывания на мобильном — не превышать)

Доступные форматы постов (большая палитра — каждый вариант должен использовать разный формат):
{formats_list}

Последние использованные форматы (НЕ повторяй их — выбери что-то другое из палитры):
{recent_formats}

Форматы вариантов — строго разные между собой и непохожие на «последние использованные»:
выбери 3 разных формата из доступной палитры и укажи их в поле format.

Важно для валидности JSON: если внутри текста поста нужны кавычки — используй « » или одинарные ' ',
НИКОГДА не используй символ " внутри поля text (это сломает JSON).

Ответь строго в JSON:
[
  {{"variant": 1, "audience": "Владельцы бизнеса", "format": "...", "text": "..."}},
  {{"variant": 2, "audience": "Партнёры-инвесторы", "format": "...", "text": "..."}},
  {{"variant": 3, "audience": "Владельцы бизнеса", "format": "...", "text": "..."}}
]"""

_LIFEHACK_INSTRUCTION = (
    "\nЭто пост рубрики «Лайфхак недели» — формат: конкретный промт/инструмент/техника, "
    "которую читатель может применить прямо сейчас. "
    "Длина 500–1200 символов (лайфхак подробнее — это исключение из правила 700 симв.).\n"
)


async def generate_variants(
    idea_text: str, rubric: str = "regular", recent_formats: list[str] | None = None
) -> list[dict]:
    rubric_instruction = _LIFEHACK_INSTRUCTION if rubric == "lifehack" else ""
    formats_list = "\n".join(f"- {f}" for f in _ALL_FORMATS)
    recent_str = (
        "\n".join(f"- {f}" for f in recent_formats[-10:]) if recent_formats else "(пока нет истории)"
    )
    user_prompt = _VARIANTS_USER_TEMPLATE.format(
        idea_text=idea_text,
        rubric_instruction=rubric_instruction,
        formats_list=formats_list,
        recent_formats=recent_str,
    )

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
    return _safe_json_loads(content)


_TOPICS_SYSTEM = (
    "Ты предлагаешь темы постов для Telegram-канала «ИИндустрия Развлечений».\n\n"
    f"{KNOWLEDGE}\n\n"
    "Отвечай строго в формате JSON-массива без пояснений вне JSON."
)

_TOPICS_USER_TEMPLATE = """Свежие новости ниши (используй как контекст, не пересказывай напрямую):
{search_context}

Уже опубликованные темы (НЕ повторять и не предлагать близкие по смыслу):
{published}

Последние использованные форматы постов (предлагай темы, под которые подойдут ДРУГИЕ форматы):
{recent_formats}

Заблокированные темы (НЕ предлагать):
{blacklisted}

Текущий месяц: {month}

Предложи {count} новых тем для постов с учётом тона голоса, аудитории и сезона.
Важно для валидности JSON: никогда не используй символ " внутри полей topic/description — только « » или ' '.
Ответь строго в JSON:
[
  {{"topic": "Краткая тема", "description": "1-2 строки о чём пост"}},
  ...
]"""


async def generate_topic_suggestions(
    search_context: str,
    published_history: list[str],
    blacklisted: list[str],
    recent_formats: list[str] | None = None,
    count: int = 5,
) -> list[dict]:
    month_name = datetime.now(_MSK).strftime("%B %Y")
    recent_str = (
        "\n".join(f"- {f}" for f in recent_formats[-10:]) if recent_formats else "(пока нет истории)"
    )
    user_prompt = _TOPICS_USER_TEMPLATE.format(
        search_context=search_context or "(поиск недоступен — используй базу знаний)",
        published="\n".join(f"- {t}" for t in published_history) or "(пока нет)",
        recent_formats=recent_str,
        blacklisted="\n".join(f"- {t}" for t in blacklisted) or "(пусто)",
        month=month_name,
        count=count,
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
    raw = _safe_json_loads(content)
    # Нормализуем — заполняем отсутствующие поля чтобы не падать в bot.py
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        topic = item.get("topic") or item.get("title") or item.get("name") or ""
        desc  = item.get("description") or item.get("desc") or item.get("text") or ""
        if topic:
            result.append({"topic": str(topic).strip(), "description": str(desc).strip()})
    return result


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
