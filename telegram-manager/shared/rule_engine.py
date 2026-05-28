"""
rule_engine.py — Матчинг и применение правил к ответам ботов.
Кэш 60 сек чтобы не дёргать SQLite на каждом сообщении.
"""
import asyncio
import time
import sys
import os

_cache: dict = {}  # {bot_name: (timestamp, rules)}
CACHE_TTL = 10


def _get_db():
    _dir = os.path.dirname(os.path.abspath(__file__))
    if _dir not in sys.path:
        sys.path.insert(0, _dir)
    import rules_db
    return rules_db


def load_rules(bot_name: str) -> list[dict]:
    now = time.time()
    if bot_name in _cache:
        ts, rules = _cache[bot_name]
        if now - ts < CACHE_TTL:
            return rules
    db = _get_db()
    rules = db.get_active_rules(bot_name)
    _cache[bot_name] = (now, rules)
    return rules


def invalidate_cache(bot_name: str | None = None) -> None:
    if bot_name:
        _cache.pop(bot_name, None)
    else:
        _cache.clear()


def get_system_addons(bot_name: str) -> str:
    """Возвращает строку addons для добавления к system_msg."""
    rules = load_rules(bot_name)
    addons = [r["instruction"] for r in rules if r["rule_type"] == "system_addon"]
    return "\n".join(addons)


def _matches(rule: dict, user_input: str) -> str | None:
    """Возвращает сработавшее ключевое слово или '' если trigger_kw=None (всегда)."""
    kw_list = rule.get("trigger_kw")
    if not kw_list:
        return ""
    lower = user_input.lower()
    for kw in kw_list:
        if kw.lower() in lower:
            return kw
    return None


async def apply_rules(
    response: str,
    user_input: str,
    bot_name: str,
    ai_client=None,
) -> str:
    """Применяет активные reformat/append/prepend правила к ответу."""
    rules = load_rules(bot_name)
    db = _get_db()

    for rule in rules:
        if rule["rule_type"] == "system_addon":
            continue

        trigger = _matches(rule, user_input)
        if trigger is None:
            continue

        rule_type = rule["rule_type"]
        instruction = rule["instruction"]

        if rule_type == "append":
            response = response + "\n" + instruction
        elif rule_type == "prepend":
            response = instruction + "\n" + response
        elif rule_type == "reformat" and ai_client is not None:
            try:
                resp = await ai_client.chat.completions.create(
                    model="deepseek/deepseek-v4-pro",
                    messages=[
                        {
                            "role": "system",
                            "content": "Переформатируй следующий текст согласно инструкции. Верни только переформатированный текст.",
                        },
                        {
                            "role": "user",
                            "content": f"Инструкция: {instruction}\n\nТекст:\n{response}",
                        },
                    ],
                    max_tokens=2000,
                )
                response = (resp.choices[0].message.content or response).strip()
            except Exception:
                pass

        try:
            db.log_application(rule["id"], user_input, trigger or "always")
        except Exception:
            pass

    return response
