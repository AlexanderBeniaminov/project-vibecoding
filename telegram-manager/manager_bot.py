"""
manager_bot.py — Управляющий бот для Напоминатора и Помощника.

Команды:
  /rules [assistant|helper|all]  — список правил
  /rule <id>                      — детали правила
  /delete_rule <id>               — удалить правило
  /toggle_rule <id>               — вкл/выкл правило
  /history <id>                   — последние 20 применений
  /help                           — справка

NLP (через LLM):
  "Напоминатор, сделай ответы короче"        → system_addon для assistant
  "Помощник, всегда уточняй приоритет"       → system_addon для helper
  reply на сообщение + "переделай — ..."     → reformat_now + offer to save
"""
import asyncio
import json
import logging
import re
import sys

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from groq import Groq
from openai import AsyncOpenAI

sys.path.insert(0, "/home/parser/bots/shared")
import rules_db
import rule_engine

import config

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.TELEGRAM_TOKEN)
dp = Dispatcher()

ai_client = AsyncOpenAI(
    base_url=config.ROUTERAI_BASE_URL,
    api_key=config.ROUTERAI_API_KEY,
)

async def _keep_typing(chat_id: int, stop: asyncio.Event) -> None:
    while not stop.is_set():
        await bot.send_chat_action(chat_id, "typing")
        try:
            await asyncio.wait_for(stop.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass


async def transcribe_voice(message: Message) -> str:
    voice = message.voice
    if not voice:
        return ""
    file = await bot.get_file(voice.file_id)
    file_bytes = await bot.download_file(file.file_path)
    groq_client = Groq(api_key=config.GROQ_API_KEY)
    try:
        tr = groq_client.audio.transcriptions.create(
            file=("voice.ogg", file_bytes.read(), "audio/ogg"),
            model="whisper-large-v3-turbo",
            language="ru",
        )
        return tr.text.strip()
    except Exception as e:
        return f"[Не удалось распознать: {e}]"


BOT_NAMES = {
    "assistant": "Напоминатор",
    "helper": "Помощник",
    "all": "Все боты",
}
RULE_TYPE_NAMES = {
    "system_addon": "📌 В промпт",
    "reformat": "✏️ Переформат",
    "append": "➕ Дописать в конец",
    "prepend": "⬆️ Вставить в начало",
}

# Pending reformat results waiting for "Сохранить как правило"
# {chat_id: {original_text, instruction, reformatted}}
_pending_reformat: dict[int, dict] = {}

# Текст пользователя ожидающий выбора бота (когда NLP не распознал)
_pending_rule_text: dict[int, str] = {}


def _auth(message: Message) -> bool:
    return message.from_user.id in config.ALLOWED_USER_IDS


# ── /help ─────────────────────────────────────────────────────────────────────

@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not _auth(message):
        return
    await message.answer(
        "🤖 *Управляющий бот*\n\n"
        "*Команды:*\n"
        "/rules — все правила\n"
        "/rules assistant — правила Напоминатора\n"
        "/rules helper — правила Помощника\n"
        "/rule 5 — детали правила №5\n"
        "/delete\\_rule 5 — удалить правило\n"
        "/toggle\\_rule 5 — вкл/выкл правило\n"
        "/history 5 — когда применялось\n\n"
        "*NLP-команды:*\n"
        "Напоминатор, сделай ответы короче\n"
        "Помощник, всегда уточняй дедлайн\n"
        "добавь правило для всех: отвечай по-русски\n\n"
        "*Переделай:*\n"
        "Процитируй сообщение бота → напиши «переделай — инструкция»",
        parse_mode="Markdown",
    )


# ── /rules ────────────────────────────────────────────────────────────────────

@dp.message(Command("rules"))
async def cmd_rules(message: Message):
    if not _auth(message):
        return
    args = (message.text or "").split(maxsplit=1)
    bot_filter = args[1].strip() if len(args) > 1 else None
    if bot_filter and bot_filter not in ("assistant", "helper", "all"):
        await message.answer("Укажи: assistant, helper или all")
        return

    rules = rules_db.list_rules(bot_filter)
    if not rules:
        target = BOT_NAMES.get(bot_filter, "всем ботам") if bot_filter else "всем ботам"
        await message.answer(f"Правил для «{target}» нет.")
        return

    lines = []
    for r in rules:
        status = "✅" if r["active"] else "❌"
        bot_label = BOT_NAMES.get(r["target_bot"], r["target_bot"])
        type_label = RULE_TYPE_NAMES.get(r["rule_type"], r["rule_type"])
        desc = r["description"] or r["instruction"][:60]
        lines.append(f"{status} #{r['id']} [{bot_label}] {type_label}\n    {desc}")

    await message.answer("📋 *Правила:*\n\n" + "\n\n".join(lines), parse_mode="Markdown")


# ── /rule <id> ────────────────────────────────────────────────────────────────

@dp.message(Command("rule"))
async def cmd_rule(message: Message):
    if not _auth(message):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /rule <id>")
        return
    rule_id = int(parts[1])
    rule = rules_db.get_rule(rule_id)
    if not rule:
        await message.answer(f"Правило #{rule_id} не найдено.")
        return

    kw = ", ".join(rule["trigger_kw"]) if rule["trigger_kw"] else "всегда"
    status = "активно ✅" if rule["active"] else "выключено ❌"
    text = (
        f"*Правило #{rule['id']}* — {status}\n\n"
        f"*Бот:* {BOT_NAMES.get(rule['target_bot'], rule['target_bot'])}\n"
        f"*Тип:* {RULE_TYPE_NAMES.get(rule['rule_type'], rule['rule_type'])}\n"
        f"*Триггер:* {kw}\n"
        f"*Применений:* {rule['use_count']}\n"
        f"*Создано:* {rule['created_at']}\n\n"
        f"*Инструкция:*\n{rule['instruction']}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 Вкл/Выкл", callback_data=f"toggle:{rule_id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_confirm:{rule_id}"),
    ]])
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


# ── /delete_rule <id> ─────────────────────────────────────────────────────────

@dp.message(Command("delete_rule"))
async def cmd_delete_rule(message: Message):
    if not _auth(message):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /delete_rule <id>")
        return
    rule_id = int(parts[1])
    rule = rules_db.get_rule(rule_id)
    if not rule:
        await message.answer(f"Правило #{rule_id} не найдено.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_confirm:{rule_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
    ]])
    desc = rule["description"] or rule["instruction"][:60]
    await message.answer(f"Удалить правило #{rule_id}?\n_{desc}_", parse_mode="Markdown", reply_markup=kb)


# ── /toggle_rule <id> ─────────────────────────────────────────────────────────

@dp.message(Command("toggle_rule"))
async def cmd_toggle_rule(message: Message):
    if not _auth(message):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /toggle_rule <id>")
        return
    rule_id = int(parts[1])
    new_state = rules_db.toggle_rule(rule_id)
    if new_state is None:
        await message.answer(f"Правило #{rule_id} не найдено.")
        return
    rule_engine.invalidate_cache()
    emoji = "✅" if new_state else "❌"
    state_text = "активно" if new_state else "выключено"
    await message.answer(f"{emoji} Правило #{rule_id} теперь {state_text}.")


# ── /history <id> ─────────────────────────────────────────────────────────────

@dp.message(Command("history"))
async def cmd_history(message: Message):
    if not _auth(message):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /history <id>")
        return
    rule_id = int(parts[1])
    log = rules_db.get_rule_log(rule_id)
    if not log:
        await message.answer(f"Правило #{rule_id} ещё не применялось.")
        return
    lines = []
    for entry in log:
        snippet = entry["input_snippet"] or ""
        trigger = entry["trigger_hit"] or "always"
        lines.append(f"🕐 {entry['applied_at']}\n   триггер: `{trigger}`\n   запрос: _{snippet[:80]}_")
    await message.answer(
        f"*История правила #{rule_id}* (последние {len(log)}):\n\n" + "\n\n".join(lines),
        parse_mode="Markdown",
    )


# ── Callback кнопки ───────────────────────────────────────────────────────────

@dp.callback_query(F.data.startswith("delete_confirm:"))
async def cb_delete_confirm(callback: CallbackQuery):
    rule_id = int(callback.data.split(":")[1])
    ok = rules_db.delete_rule(rule_id)
    rule_engine.invalidate_cache()
    await callback.message.edit_text(
        f"{'🗑 Правило #' + str(rule_id) + ' удалено.' if ok else 'Правило не найдено.'}"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle:"))
async def cb_toggle(callback: CallbackQuery):
    rule_id = int(callback.data.split(":")[1])
    new_state = rules_db.toggle_rule(rule_id)
    rule_engine.invalidate_cache()
    state_text = "активно ✅" if new_state else "выключено ❌"
    await callback.answer(f"Правило #{rule_id} — {state_text}")
    await callback.message.edit_reply_markup(reply_markup=None)


@dp.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery):
    await callback.message.edit_text("Отменено.")
    await callback.answer()


@dp.callback_query(F.data.startswith("save_rule:"))
async def cb_save_rule(callback: CallbackQuery):
    """Сохранить переформатированный ответ как правило для выбранного бота."""
    _, bot_name = callback.data.split(":", 1)
    chat_id = callback.message.chat.id
    pending = _pending_reformat.get(chat_id)
    if not pending:
        await callback.answer("Данные истекли — повтори переделай.")
        return

    rule_id = rules_db.create_rule(
        target_bot=bot_name,
        rule_type="reformat",
        instruction=pending["instruction"],
        description=f"Авто: {pending['instruction'][:60]}",
    )
    rule_engine.invalidate_cache(bot_name)
    _pending_reformat.pop(chat_id, None)
    bot_label = BOT_NAMES.get(bot_name, bot_name)
    await callback.message.edit_text(
        f"💾 Правило #{rule_id} сохранено для «{bot_label}».\n"
        f"Следующие похожие ответы будут переформатированы автоматически."
    )
    await callback.answer()


@dp.callback_query(F.data == "save_rule_cancel")
async def cb_save_rule_cancel(callback: CallbackQuery):
    _pending_reformat.pop(callback.message.chat.id, None)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Не сохранено.")


@dp.callback_query(F.data.startswith("rule_for:"))
async def cb_rule_for(callback: CallbackQuery):
    """Fallback: пользователь выбирает бота вручную когда NLP не распознал."""
    target = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    if target == "cancel":
        _pending_rule_text.pop(chat_id, None)
        await callback.message.edit_text("Отменено.")
        await callback.answer()
        return

    original_text = _pending_rule_text.pop(chat_id, None)
    if not original_text:
        await callback.answer("Данные истекли — повтори команду.")
        return

    rule_id = rules_db.create_rule(
        target_bot=target,
        rule_type="system_addon",
        instruction=original_text,
        description=original_text[:80],
    )
    rule_engine.invalidate_cache(target if target != "all" else None)
    bot_label = BOT_NAMES.get(target, target)
    await callback.message.edit_text(
        f"✅ Правило #{rule_id} создано для «{bot_label}».\n\n"
        f"_Инструкция:_ {original_text[:120]}",
        parse_mode="Markdown",
    )
    await callback.answer()


# ── NLP + "Переделай" ─────────────────────────────────────────────────────────

_NLP_SYSTEM = """Ты менеджер правил для двух Telegram-ботов: Напоминатор (assistant) и Помощник (helper).

Получаешь команду на русском. Определи:
- action: "create_rule" | "reformat_now"
- target_bot: "assistant" | "helper" | "all"
- rule_type: "system_addon" | "reformat" | "append" | "prepend"
- instruction: точная инструкция (что делать с текстом или добавить в промпт)
- trigger_kw: массив ключевых слов-триггеров или null (если правило применяется всегда)
- description: короткое описание правила (1 строка)

Правила определения target_bot:
- "Напоминатор" / "напоминатор" / "планировщик" → "assistant"
- "Помощник" / "помощник" → "helper"
- "для всех" / "оба" / "оба бота" → "all"
- Если бот не упомянут → "all"

Если запрос начинается с "переделай" или содержит инструкцию переформатировать конкретный текст —
верни action="reformat_now" (правило не создаётся).

Отвечай ТОЛЬКО валидным JSON без markdown-обёртки.

Пример 1:
Вход: "Напоминатор, сделай ответы короче"
Ответ: {"action":"create_rule","target_bot":"assistant","rule_type":"system_addon","instruction":"Отвечай максимально кратко — не более одного предложения.","trigger_kw":null,"description":"Короткие ответы"}

Пример 2:
Вход: "переделай — добавь процентное изменение"
Ответ: {"action":"reformat_now","instruction":"Добавь в конец процентное изменение относительно предыдущего периода"}
"""


async def _parse_nlp(user_text: str) -> dict | None:
    try:
        resp = await ai_client.chat.completions.create(
            model=config.MODEL,
            messages=[
                {"role": "system", "content": _NLP_SYSTEM},
                {"role": "user", "content": user_text},
            ],
            max_tokens=400,
            temperature=0,
            response_format={"type": "json_object"},
        )
        msg = resp.choices[0].message
        raw = (msg.content or "").strip()
        if not raw:
            logging.warning("NLP: пустой content от LLM, raw=%r", raw)
            return None
        raw = re.sub(r"^```[a-z]*\n?|```$", "", raw, flags=re.MULTILINE).strip()
        return json.loads(raw)
    except Exception as e:
        logging.warning("NLP parse error: %s | raw=%r", e, locals().get("raw", ""))
        return None


async def _reformat_with_llm(original: str, instruction: str) -> str:
    try:
        resp = await ai_client.chat.completions.create(
            model=config.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Переформатируй текст согласно инструкции. Верни только результат.",
                },
                {
                    "role": "user",
                    "content": f"Инструкция: {instruction}\n\nТекст:\n{original}",
                },
            ],
            max_tokens=2000,
        )
        msg = resp.choices[0].message
        result = (msg.content or "").strip()
        if not result and hasattr(msg, "reasoning"):
            result = (msg.reasoning or "").strip()
        return result or original
    except Exception:
        return original


@dp.message(F.text | F.voice)
async def handle_message(message: Message):
    if not _auth(message):
        return

    # ── Транскрипция голосового ────────────────────────────────────────────────
    if message.voice:
        stop = asyncio.Event()
        typing = asyncio.create_task(_keep_typing(message.chat.id, stop))
        try:
            text = await transcribe_voice(message)
        finally:
            stop.set(); typing.cancel()
            try: await typing
            except asyncio.CancelledError: pass
        if not text or text.startswith("[Не удалось"):
            await message.answer(text or "Не удалось распознать голосовое.")
            return
        await message.answer(f"🎙 _{text}_", parse_mode="Markdown")
    else:
        text = (message.text or "").strip()

    if not text:
        return

    # ── "Переделай" flow: reply на сообщение ─────────────────────────────────
    if message.reply_to_message:
        original_text = (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or ""
        ).strip()
        if original_text and re.match(r"^переделай", text, re.IGNORECASE):
            instruction = re.sub(r"^переделай\s*[—–-]?\s*", "", text, flags=re.IGNORECASE).strip()
            if not instruction:
                await message.answer("Укажи инструкцию: «переделай — добавь процентное изменение»")
                return

            stop = asyncio.Event()
            typing = asyncio.create_task(_keep_typing(message.chat.id, stop))
            try:
                reformatted = await _reformat_with_llm(original_text, instruction)
            finally:
                stop.set(); typing.cancel()
                try: await typing
                except asyncio.CancelledError: pass

            _pending_reformat[message.chat.id] = {
                "original": original_text,
                "instruction": instruction,
                "reformatted": reformatted,
            }

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="💾 Для Напоминатора", callback_data="save_rule:assistant"),
                    InlineKeyboardButton(text="💾 Для Помощника", callback_data="save_rule:helper"),
                ],
                [
                    InlineKeyboardButton(text="💾 Для обоих", callback_data="save_rule:all"),
                    InlineKeyboardButton(text="✅ Готово", callback_data="save_rule_cancel"),
                ],
            ])
            await message.answer(
                f"*Результат:*\n\n{reformatted}\n\n_Сохранить как правило?_",
                parse_mode="Markdown",
                reply_markup=kb,
            )
            return

    # ── NLP: создание правила ─────────────────────────────────────────────────
    stop = asyncio.Event()
    typing = asyncio.create_task(_keep_typing(message.chat.id, stop))
    try:
        parsed = await _parse_nlp(text)
    finally:
        stop.set(); typing.cancel()
        try: await typing
        except asyncio.CancelledError: pass

    if not parsed or parsed.get("action") not in ("create_rule", "reformat_now"):
        # LLM не распознал → предлагаем выбрать бота вручную и создадим system_addon
        _pending_rule_text[message.chat.id] = text
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📌 Напоминатор", callback_data="rule_for:assistant"),
                InlineKeyboardButton(text="📌 Помощник", callback_data="rule_for:helper"),
            ],
            [
                InlineKeyboardButton(text="📌 Оба бота", callback_data="rule_for:all"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="rule_for:cancel"),
            ],
        ])
        await message.answer(
            "Для какого бота создать правило?",
            reply_markup=kb,
        )
        return

    if parsed["action"] == "create_rule":
        rule_id = rules_db.create_rule(
            target_bot=parsed.get("target_bot", "all"),
            rule_type=parsed.get("rule_type", "system_addon"),
            instruction=parsed["instruction"],
            trigger_kw=parsed.get("trigger_kw"),
            description=parsed.get("description"),
        )
        rule_engine.invalidate_cache()
        bot_label = BOT_NAMES.get(parsed.get("target_bot", "all"), "Все боты")
        type_label = RULE_TYPE_NAMES.get(parsed.get("rule_type", "system_addon"), "")
        kw_text = ""
        if parsed.get("trigger_kw"):
            kw_text = f"\n*Триггер:* {', '.join(parsed['trigger_kw'])}"
        await message.answer(
            f"✅ *Правило #{rule_id} создано*\n\n"
            f"*Бот:* {bot_label}\n"
            f"*Тип:* {type_label}{kw_text}\n"
            f"*Инструкция:* {parsed['instruction']}",
            parse_mode="Markdown",
        )
    else:
        # reformat_now без reply — попросим процитировать
        await message.answer(
            "Чтобы переделать — процитируй (reply) нужное сообщение бота и напиши:\n"
            "«переделай — [инструкция]»"
        )


# ── Запуск ────────────────────────────────────────────────────────────────────

async def main():
    rules_db.init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
