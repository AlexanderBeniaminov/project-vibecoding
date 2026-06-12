#!/usr/bin/env python3
"""
Ночной процессор знаний (запуск в 21:00 через cron/systemd timer).

Cron: 0 21 * * * /home/parser/venv/bin/python /home/parser/bots/assistant/tools/processor.py

Pipeline:
1. Читает vault/daily/YYYY-MM-DD.md (сырой поток дня)
2. DeepSeek классифицирует записи → создаёт карточки в vault
3. Обновляет vault/MEMORY.md (эволюционирует, не дополняется)
4. Отправляет Telegram-отчёт пользователю
"""
import asyncio
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, "/home/parser/bots/assistant")
import config
import openai

from vault import _vault_dir, save_card, get_daily_log

_MSK = ZoneInfo("Europe/Moscow")

ai_client = openai.AsyncOpenAI(
    base_url=config.ROUTERAI_BASE_URL,
    api_key=config.ROUTERAI_API_KEY,
    timeout=90.0,
)

_CLASSIFY_SYSTEM = """Ты система организации личных знаний. Тебе дан сырой дневной лог: голосовые заметки, мысли, задачи.

Твоя задача — вернуть JSON список карточек для сохранения.
Каждая карточка: {"type": "...", "title": "...", "content": "...", "tags": [...]}

Типы:
- idea — идея, гипотеза, что-то что хочу попробовать
- learning — вывод, инсайт, что-то чему научился
- decision — принятое решение
- note — всё остальное (задача, наблюдение, факт)

Правила:
- Объединяй связанные записи в одну карточку, не дроби на атомы
- Пропускай технические артефакты (ошибки распознавания, команды боту)
- Заголовок — короткий (3-7 слов), содержательный
- Теги — 1-3 штуки, на русском, без решётки
- Отвечай ТОЛЬКО валидным JSON массивом, без текста вокруг
"""

_MEMORY_UPDATE_SYSTEM = """Ты обновляешь файл MEMORY.md — живую память ассистента. Он ЭВОЛЮЦИОНИРУЕТ, а не дополняется.

Текущий MEMORY.md:
{current_memory}

Новые карточки за сегодня:
{new_cards}

Обнови MEMORY.md: замени устаревшее, добавь новое, удали неактуальное.
Структура (строго сохраняй заголовки):

# MEMORY.md — Активная память

## Активный контекст
(один главный фокус прямо сейчас)

## Горячие проекты
(3-5 активных проектов, статус одной строкой)

## Ключевые решения
| Дата | Решение | Почему |
|------|---------|--------|

## Финансовый контекст
(актуальная картина)

## Ключевые люди
(люди с которыми активно взаимодействую)

---
*Обновлено: {today}*

Отвечай ТОЛЬКО содержимым MEMORY.md, без обёртки.
"""


async def _classify_entries(log_text: str) -> list[dict]:
    """Отправляет дневной лог в DeepSeek → получает список карточек."""
    resp = await ai_client.chat.completions.create(
        model=config.MODEL,
        messages=[
            {"role": "system", "content": _CLASSIFY_SYSTEM},
            {"role": "user", "content": f"Дневной лог:\n\n{log_text}"},
        ],
        max_tokens=2000,
        temperature=0.2,
    )
    raw = (resp.choices[0].message.content or "").strip()
    # Вырезаем JSON из возможных markdown-блоков
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


async def _update_memory_md(new_cards: list[dict]) -> None:
    """Обновляет vault/MEMORY.md через DeepSeek."""
    vault = _vault_dir()
    memory_path = vault / "MEMORY.md"
    current = memory_path.read_text(encoding="utf-8") if memory_path.exists() else "(пусто)"

    cards_text = "\n".join(
        f"[{c.get('type','note')}] {c.get('title','')}: {c.get('content','')[:200]}"
        for c in new_cards
    )

    today = date.today().isoformat()
    prompt = _MEMORY_UPDATE_SYSTEM.format(
        current_memory=current,
        new_cards=cards_text or "(нет новых карточек)",
        today=today,
    )

    resp = await ai_client.chat.completions.create(
        model=config.MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
        temperature=0.2,
    )
    new_content = (resp.choices[0].message.content or "").strip()
    if new_content:
        vault.mkdir(parents=True, exist_ok=True)
        memory_path.write_text(new_content, encoding="utf-8")


async def _send_telegram(text: str) -> None:
    """Отправляет отчёт в Telegram через Bot API."""
    import httpx
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    for user_id in config.ALLOWED_USER_IDS:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(url, json={
                    "chat_id": user_id,
                    "text": text,
                    "parse_mode": "Markdown",
                }, timeout=10)
        except Exception as e:
            print(f"[processor] ошибка Telegram для {user_id}: {e}")


async def run():
    today = date.today().isoformat()
    print(f"[processor] запуск для {today}")

    log_text = get_daily_log(today)
    if not log_text.strip():
        await _send_telegram(f"🌙 *{today}* — дневной лог пуст, карточки не созданы.")
        return

    log_lines = [l for l in log_text.splitlines() if l.strip()]
    print(f"[processor] записей в логе: {len(log_lines)}")

    # Классификация → карточки
    cards = await _classify_entries(log_text)
    saved = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        ctype = card.get("type", "note")
        title = card.get("title", "Без названия")
        content = card.get("content", "")
        tags = card.get("tags", [])
        if title and content:
            result = save_card(ctype, title, content, tags)
            saved.append(f"• [{ctype}] {title}")
            print(f"[processor] {result}")

    # Обновление MEMORY.md
    await _update_memory_md(cards)

    # Отчёт пользователю
    summary_lines = [f"🌙 *Итоги {today}*", ""]
    summary_lines.append(f"📥 Записей в логе: {len(log_lines)}")
    if saved:
        summary_lines.append(f"📦 Создано карточек: {len(saved)}")
        summary_lines.extend(saved[:10])
    else:
        summary_lines.append("📦 Новых карточек нет")
    summary_lines.append("")
    summary_lines.append("🧠 MEMORY.md обновлён")

    await _send_telegram("\n".join(summary_lines))
    print(f"[processor] готово, создано карточек: {len(saved)}")


if __name__ == "__main__":
    asyncio.run(run())
