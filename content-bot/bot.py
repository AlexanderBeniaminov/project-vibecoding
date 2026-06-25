"""Content Bot — генерация и публикация постов в Telegram-канал «ИИндустрия Развлечений»."""
import asyncio
import logging
import os
import re
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import blacklist
import config
import db
import generator
import publisher
import search
import sheets

logging.basicConfig(level=logging.INFO)
_MSK = ZoneInfo("Europe/Moscow")

bot = Bot(token=config.TELEGRAM_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

# ── Состояния в памяти ────────────────────────────────────────
_awaiting_idea_save: set[int] = set()
_awaiting_correction: dict[int, int] = {}       # user_id → gen_id
_awaiting_blacklist_text: set[int] = set()
_awaiting_blacklist_bulk: set[int] = set()
_pending_blacklist_text: dict[int, str] = {}
_pending_blacklist_bulk: dict[int, list[str]] = {}
_pending_blacklist_confirm: dict[int, dict] = {}
_pending_topics: dict[int, list[dict]] = {}     # user_id → предложенные темы (Режим 0)
_content_plan: dict[int, dict] = {}             # user_id → {topics: [...], selected: set()}

# ── Regex-паттерны команд ─────────────────────────────────────
_IDEA_TRIGGER_RE = re.compile(r'^идея(\s+для\s+поста)?\W*', re.IGNORECASE)
_LIFEHACK_RE = re.compile(r'лайфхак', re.IGNORECASE)
# Ссылка на идею по номеру: «тему 2 из идей», «идею №3», «вторую идею» и т.п.
_IDEA_REF_RE = re.compile(
    r'(?:тем[аиую]|идею?|пост\s+(?:по\s+)?(?:идее?|теме?))\s*(?:№\s*)?(\d+)\b'
    r'|(?:тем[аиую]|идею?)\s*(?:№\s*)?(\d+)\s*из\s*(?:листа\s*)?идей',
    re.IGNORECASE,
)
# Порядковые числительные РУ (для «вторую идею» и т.п.)
_RU_ORDINALS = {
    "перв": 1, "второ": 2, "второй": 2, "второю": 2, "вторую": 2,
    "треть": 3, "четвёрт": 4, "четверт": 4, "пят": 5,
    "шест": 6, "седьм": 7, "восьм": 8, "девят": 9, "десят": 10,
}
_ORDINAL_RE = re.compile(
    r'(перв|второй|второю|вторую|третью?|четвёрт\w*|четверт\w*|пят\w*|шест\w*|седьм\w*|восьм\w*|девят\w*|десят\w*)'
    r'\s+(?:идею?|тему)',
    re.IGNORECASE,
)
_INVENT_TOPIC_RE = re.compile(r'придумай\s+(?:тему|идею)', re.IGNORECASE)
# «Запомни/сохрани/добавь идею про X» → сохранить без генерации
_SAVE_SYNONYM_RE = re.compile(
    r'^(?:запомни|сохрани|добавь|зафиксируй)\s+(?:идею|тему|мысль)\s*(?:про|об?|для|:)?\s*',
    re.IGNORECASE,
)


def _extract_idea_index(text: str) -> int | None:
    """Извлекает номер идеи (0-based) из произвольной фразы. Возвращает None если не нашёл."""
    m = _IDEA_REF_RE.search(text)
    if m:
        n = int(m.group(1) or m.group(2))
        return n - 1  # 0-based
    # Порядковые числительные
    m = _ORDINAL_RE.search(text)
    if m:
        word = m.group(1).lower()
        for prefix, n in _RU_ORDINALS.items():
            if word.startswith(prefix):
                return n - 1
    return None


def is_allowed(user_id: int) -> bool:
    return not config.ALLOWED_USER_IDS or user_id in config.ALLOWED_USER_IDS


class _Typing:
    """Пока генерация идёт — Telegram показывает «печатает...» под именем бота."""
    def __init__(self, chat_id: int):
        self._chat_id = chat_id
        self._task: asyncio.Task | None = None

    async def _loop(self):
        while True:
            await bot.send_chat_action(self._chat_id, "typing")
            await asyncio.sleep(4)

    async def __aenter__(self):
        self._task = asyncio.create_task(self._loop())
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._task.cancel()


# ── Транскрипция голоса ──────────────────────────────────────
_WHISPER_HALLUCINATIONS = {"", "you", "thank you for watching", "thanks for watching"}


def _is_hallucination(text: str) -> bool:
    cleaned = text.strip().lower().rstrip(".")
    return cleaned in _WHISPER_HALLUCINATIONS or len(cleaned) < 3


async def transcribe_voice(message: Message) -> str:
    from groq import Groq

    file = await bot.get_file(message.voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        await bot.download_file(file.file_path, tmp_path)
        groq_client = Groq(api_key=config.GROQ_API_KEY)
        ru_prompt = "Это голосовое сообщение на русском языке."
        for model in ("whisper-large-v3-turbo", "whisper-large-v3"):
            with open(tmp_path, "rb") as f:
                tr = groq_client.audio.transcriptions.create(
                    model=model, file=("voice.ogg", f, "audio/ogg"), language="ru", prompt=ru_prompt,
                )
            result = tr.text.strip()
            if not _is_hallucination(result):
                return result
        return ""
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Главное меню ─────────────────────────────────────────────
def _persistent_kb() -> ReplyKeyboardMarkup:
    """Постоянная клавиатура в строке ввода — всегда доступна."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📋 Меню")]],
        resize_keyboard=True,
        input_field_placeholder="Наговори тему или напиши...",
    )


def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💡 Предложи темы", callback_data="menu:propose"),
         InlineKeyboardButton(text="📋 Мои идеи", callback_data="ideas:page:0")],
        [InlineKeyboardButton(text="🗂 Контент-план", callback_data="menu:content_plan"),
         InlineKeyboardButton(text="🚫 Блэклист", callback_data="menu:blacklist")],
        [InlineKeyboardButton(text="📅 Расписание", callback_data="menu:schedule"),
         InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
    ])


_HELP_TEXT = (
    "🤖 *Content Bot — шпаргалка*\n\n"
    "*Написать пост:* наговори или напиши тему.\n"
    "*Лайфхак:* «придумай лайфхак про X».\n"
    "*По сохранённой идее:* «напиши пост на тему 2 из идей».\n"
    "*Сохранить идею:* «идея для поста: ...».\n"
    "*Предложи тему сам:* «придумай тему».\n\n"
    "После генерации:\n"
    "💾 Сохранить → черновик падает в таблицу → правь текст, ставь дату → бот публикует в 3:00.\n"
    "🚨 СРОЧНО В КАНАЛ → публикуется немедленно.\n\n"
    "*Контент-план:* [🗂 Контент-план] — темы пачкой → утверди → черновики в таблице.\n"
    "*Блэклист тем:* /blacklist"
)


@dp.message(Command("myid"))
async def cmd_myid(message: Message):
    """Работает для всех — чтобы узнать свой user_id для добавления в бот."""
    await message.answer(f"Твой Telegram ID: `{message.from_user.id}`", parse_mode="Markdown")


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer(
        "Привет! Я помогу писать и публиковать посты для «ИИндустрия Развлечений».\n\n"
        "Наговори тему — пришлю 3 варианта. Кнопка «📋 Меню» всегда доступна в строке ввода.",
        reply_markup=_persistent_kb(),
    )
    await message.answer("Меню:", reply_markup=_main_menu_kb())


@dp.message(Command("menu"))
async def cmd_menu(message: Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer("Меню:", reply_markup=_main_menu_kb())


@dp.callback_query(F.data == "menu:help")
async def cb_help(callback: CallbackQuery):
    await callback.message.answer(_HELP_TEXT, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "menu:show")
async def cb_menu_show(callback: CallbackQuery):
    await callback.message.answer("Меню:", reply_markup=_main_menu_kb())
    await callback.answer()


# ── /schedule — расписание публикаций ────────────────────────
def _schedule_text() -> str:
    lines = []
    for dt in publisher.next_publish_dates(6):
        conn = db.get_conn()
        row = conn.execute(
            """SELECT i.text FROM generations g
               JOIN ideas i ON i.id = g.idea_id
               WHERE g.status='to_publish' AND g.scheduled_at=?""",
            (dt.isoformat(),),
        ).fetchone()
        conn.close()
        marker = "🔴" if publisher.is_lifehack_thursday(dt) else "📅"
        label = f"«{row['text']}»" if row else "свободно"
        lifehack_note = " (Лайфхак-четверг)" if publisher.is_lifehack_thursday(dt) and not row else ""
        lines.append(f"{marker} {publisher.DAY_NAMES[dt.weekday()]} {dt.strftime('%d.%m')} — {label}{lifehack_note}")
    return "\n".join(lines) or "Расписание пусто."


@dp.message(Command("schedule"))
async def cmd_schedule(message: Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer(_schedule_text())


@dp.callback_query(F.data == "menu:schedule")
async def cb_schedule(callback: CallbackQuery):
    await callback.message.answer(_schedule_text())
    await callback.answer()


# ── Мои идеи (пагинация) ─────────────────────────────────────
def _ideas_kb(page: int, ideas: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{i['text'][:40]}", callback_data=f"idea:select:{i['id']}")] for i in ideas]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="← Назад", callback_data=f"ideas:page:{page-1}"))
    if len(ideas) == 5:
        nav.append(InlineKeyboardButton(text="Вперёд →", callback_data=f"ideas:page:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔙 Меню", callback_data="menu:show")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data.startswith("ideas:page:"))
async def cb_ideas_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[-1])
    ideas = db.list_ideas(status="saved", limit=5, offset=page * 5)
    if not ideas and page == 0:
        await callback.message.answer(
            "Пока нет сохранённых идей. Скажи «идея для поста: ...» чтобы сохранить.",
            reply_markup=_main_menu_kb(),
        )
        await callback.answer()
        return
    await callback.message.answer(f"📋 Мои идеи (стр. {page+1}):", reply_markup=_ideas_kb(page, ideas))
    await callback.answer()


@dp.callback_query(F.data.startswith("idea:select:"))
async def cb_idea_select(callback: CallbackQuery):
    idea_id = int(callback.data.split(":")[-1])
    idea = db.get_idea(idea_id)
    if not idea:
        await callback.answer("Идея не найдена")
        return
    await callback.answer()
    loading = await callback.message.answer("⏳ Генерирую варианты...")
    db.update_idea_status(idea_id, "in_progress")
    recent_formats = _get_recent_formats()
    await _generate_and_render(loading, idea_id, idea["text"], idea["rubric"], recent_formats)


def _get_recent_formats() -> list[str]:
    """Читает недавние форматы из истории Sheets для ротации."""
    try:
        history = sheets.get_recent_history(limit=15)
        return [h["format"] for h in history if h.get("format")]
    except Exception:
        return []


# ── Генерация (общее ядро) ────────────────────────────────────
def _result_keyboard(generations: list[dict], idea_id: int) -> InlineKeyboardMarkup:
    rows = []
    for g in generations:
        rows.append([
            InlineKeyboardButton(text=f"💾 Сохранить вар.{g['variant_num']}", callback_data=f"save:{g['id']}"),
        ])
    rows.append([InlineKeyboardButton(text="🔄 Другие варианты", callback_data=f"regen:{idea_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _render_variants_text(generations: list[dict]) -> str:
    blocks = []
    for g in generations:
        blocks.append(f"──── Вариант {g['variant_num']} · {g['format']} ────\n{g['text']}")
    return "\n\n".join(blocks)


def _cooldown_overlap(new_text: str, published_texts: list[str]) -> str | None:
    """Возвращает первую недавно опубликованную тему с пересечением ≥3 значимых слов, иначе None."""
    new_words = {w.lower() for w in new_text.split() if len(w) > 3}
    if not new_words:
        return None
    for pub in published_texts:
        pub_words = {w.lower() for w in pub.split() if len(w) > 3}
        if len(new_words & pub_words) >= 3:
            return pub
    return None


async def _generate_and_render(
    loading_msg: Message, idea_id: int, idea_text: str, rubric: str,
    recent_formats: list[str] | None = None,
):
    # _Typing охватывает весь pipeline: проверку блэклиста + генерацию
    async with _Typing(loading_msg.chat.id):
        matched = await blacklist.check_against_blacklist(idea_text)
        if matched:
            _pending_blacklist_confirm[loading_msg.chat.id] = {
                "idea_id": idea_id, "text": idea_text, "rubric": rubric,
                "recent_formats": recent_formats,
            }
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Да, генерировать", callback_data="blconfirm:yes"),
                InlineKeyboardButton(text="Нет, отмена", callback_data="blconfirm:no"),
            ]])
            await loading_msg.edit_text(
                f"⚠️ Тема похожа на заблокированную: «{matched}». Всё равно генерировать?", reply_markup=kb
            )
            return

        # Анти-повтор: для рубрик кроме lifehack — проверяем cooldown 30 дней
        if rubric != "lifehack":
            recently = db.get_published_texts()
            overlap = _cooldown_overlap(idea_text, recently)
            if overlap:
                _pending_blacklist_confirm[loading_msg.chat.id] = {
                    "idea_id": idea_id, "text": idea_text, "rubric": rubric,
                    "recent_formats": recent_formats,
                }
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Да, генерировать", callback_data="blconfirm:yes"),
                    InlineKeyboardButton(text="Нет, отмена", callback_data="blconfirm:no"),
                ]])
                await loading_msg.edit_text(
                    f"⚠️ Похожая тема уже публиковалась (30 дней): «{overlap[:60]}». Всё равно?",
                    reply_markup=kb,
                )
                return

        await _do_generate(loading_msg, idea_id, idea_text, rubric, recent_formats)


async def _do_generate(
    loading_msg: Message, idea_id: int, idea_text: str, rubric: str,
    recent_formats: list[str] | None = None,
):
    try:
        variants = await generator.generate_variants(idea_text, rubric, recent_formats)

        if not variants:
            await loading_msg.edit_text("Не удалось сгенерировать варианты. Попробуй ещё раз.")
            return

        # Сохраняем в БД со статусом 'generated' (в Sheets НЕ пишем — только после «Сохранить»)
        generations = []
        for v in variants:
            gen_id = db.add_generation(
                idea_id,
                v.get("variant", 1),
                v.get("text", ""),
                v.get("audience", ""),
                v.get("format", ""),
            )
            generations.append(db.get_generation(gen_id))

        # Каждый вариант — отдельное сообщение (обходим лимит Telegram 4096 символов)
        for i, gen in enumerate(generations):
            text = f"──── Вариант {gen['variant_num']} · {gen['format']} ────\n{gen['text']}"
            is_last = (i == len(generations) - 1)
            rows = [[InlineKeyboardButton(
                text=f"💾 Сохранить вар.{gen['variant_num']}",
                callback_data=f"save:{gen['id']}",
            )]]
            if is_last:
                rows.append([InlineKeyboardButton(
                    text="🔄 Другие варианты",
                    callback_data=f"regen:{idea_id}",
                )])
            kb = InlineKeyboardMarkup(inline_keyboard=rows)
            if i == 0:
                await loading_msg.edit_text(text, reply_markup=kb)
            else:
                await loading_msg.answer(text, reply_markup=kb)

    except Exception as e:
        logging.exception("_do_generate error")
        try:
            await loading_msg.edit_text(f"Не удалось сгенерировать варианты: {e}")
        except Exception:
            pass


@dp.callback_query(F.data == "blconfirm:yes")
async def cb_blconfirm_yes(callback: CallbackQuery):
    pending = _pending_blacklist_confirm.pop(callback.message.chat.id, None)
    if not pending:
        await callback.answer()
        return
    await callback.answer()
    async with _Typing(callback.message.chat.id):
        await _do_generate(
            callback.message, pending["idea_id"], pending["text"], pending["rubric"],
            pending.get("recent_formats"),
        )


@dp.callback_query(F.data == "blconfirm:no")
async def cb_blconfirm_no(callback: CallbackQuery):
    pending = _pending_blacklist_confirm.pop(callback.message.chat.id, None)
    if pending:
        db.update_idea_status(pending["idea_id"], "paused")
    await callback.message.edit_text("Отменено.")
    await callback.answer()


@dp.callback_query(F.data.startswith("regen:"))
async def cb_regen(callback: CallbackQuery):
    idea_id = int(callback.data.split(":")[-1])
    idea = db.get_idea(idea_id)
    if not idea:
        await callback.answer("Идея не найдена")
        return
    await callback.answer()
    loading = await callback.message.answer("⏳ Генерирую другие варианты...")
    async with _Typing(callback.message.chat.id):
        await _do_generate(loading, idea_id, idea["text"], idea["rubric"], _get_recent_formats())


# ── Кнопка «Сохранить» ───────────────────────────────────────
@dp.callback_query(F.data.startswith("save:"))
async def cb_save(callback: CallbackQuery):
    gen_id = int(callback.data.split(":")[-1])
    gen = db.get_generation(gen_id)
    if not gen:
        await callback.answer("Вариант не найден")
        return
    if gen["status"] in ("draft", "to_publish", "published"):
        await callback.answer("Уже сохранено")
        return
    db.mark_generation_saved(gen_id)
    idea = db.get_idea(gen["idea_id"])
    try:
        sheets.push_generation_draft(idea, db.get_generation(gen_id))
    except Exception as e:
        logging.warning(f"[sheets] push_generation_draft не удался: {e}")
    await callback.answer("💾 Сохранено в таблицу")

    # Для редактора (не владельца) — кнопка отправки на согласование Александру
    if callback.from_user.id != config.OWNER_USER_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📬 На согласование → Александру", callback_data=f"review:{gen_id}"),
        ]])
        await callback.message.answer(
            "💾 Черновик в «Посты». Когда готово — отправь на согласование.",
            reply_markup=kb,
        )
    else:
        await callback.message.answer(
            "💾 Черновик в листе «Посты».\n"
            "Открой таблицу: правь текст, выбери дату из списка и поставь статус «К публикации» — "
            "бот опубликует в 3:00."
        )


# ── Кнопка «На согласование» (редактор → владелец) ──────────
@dp.callback_query(F.data.startswith("review:"))
async def cb_review_send(callback: CallbackQuery):
    gen_id = int(callback.data.split(":")[-1])
    gen = db.get_generation(gen_id)
    if not gen:
        await callback.answer("Вариант не найден")
        return

    # Обновить статус в Sheets
    loop = asyncio.get_running_loop()
    updated, row, gid = False, None, None
    try:
        updated, row, gid = await loop.run_in_executor(
            None, lambda: sheets.update_post_status_by_gen_id(gen_id, sheets._STATUS_ON_REVIEW)
        )
    except Exception as e:
        logging.warning(f"[sheets] update_post_status_by_gen_id не удался: {e}")

    # Уведомить владельца
    try:
        idea = db.get_idea(gen["idea_id"])
        topic_hint = f"«{idea['text'][:60]}»" if idea else ""
        post_link = sheets.build_post_link(row, gid) if row else config.SPREADSHEET_URL
        kb_owner = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📊 Открыть этот пост", url=post_link),
        ]])
        await bot.send_message(
            config.OWNER_USER_ID,
            f"📬 Алексей отправил пост на согласование {topic_hint}\n\n"
            f"──── {gen.get('format', '')} ────\n{gen['text']}\n\n"
            "Открой «Посты», проверь текст и дату → смени статус на «К публикации».",
            reply_markup=kb_owner,
        )
        db.mark_review_notified(gen_id)
    except Exception as e:
        logging.warning(f"[bot] уведомление владельцу не удалось: {e}")

    await callback.answer("✅ Отправлено на согласование")
    status_note = " и статус обновлён в таблице" if updated else ""
    await callback.message.answer(f"✅ Александр получил уведомление{status_note}.")


# ── Кнопка «СРОЧНО В КАНАЛ» ─────────────────────────────────
@dp.callback_query(F.data.startswith("urgent:"))
async def cb_urgent(callback: CallbackQuery):
    gen_id = int(callback.data.split(":")[-1])
    gen = db.get_generation(gen_id)
    if not gen:
        await callback.answer("Вариант не найден")
        return
    if gen["status"] == "published":
        await callback.answer("Уже опубликовано")
        return
    # Если ещё не сохранён — сохраняем в Sheets тоже
    if gen["status"] == "generated":
        db.mark_generation_saved(gen_id)
        idea = db.get_idea(gen["idea_id"])
        try:
            sheets.push_generation_draft(idea, db.get_generation(gen_id))
        except Exception as e:
            logging.warning(f"[sheets] push при СРОЧНО не удался: {e}")
    result = await publisher.publish_now(gen_id)
    await callback.message.answer(result)
    await callback.answer()


# ── Корректировка ─────────────────────────────────────────────
@dp.callback_query(F.data.startswith("corr:"))
async def cb_correct(callback: CallbackQuery):
    gen_id = int(callback.data.split(":")[-1])
    gen = db.get_generation(gen_id)
    if not gen:
        await callback.answer("Вариант не найден")
        return
    _awaiting_correction[callback.from_user.id] = gen_id
    await callback.message.answer(
        f"Текущий текст (скопируй, исправь и пришли целиком — или напиши что изменить):\n\n{gen['text']}"
    )
    await callback.answer()


async def _handle_correction(message: Message, gen_id: int):
    gen = db.get_generation(gen_id)
    if not gen:
        await message.answer("Вариант не найден.")
        return
    correction_text = message.text or message.caption or ""
    if message.voice:
        correction_text = await transcribe_voice(message)
    async with _Typing(message.chat.id):
        new_text = await generator.apply_correction(gen["text"], correction_text)
    db.update_generation_text(gen_id, new_text)
    gen = db.get_generation(gen_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚙️ Скорректировать", callback_data=f"corr:{gen_id}"),
        InlineKeyboardButton(text="💾 Сохранить", callback_data=f"save:{gen_id}"),
        InlineKeyboardButton(text="🚨 СРОЧНО В КАНАЛ", callback_data=f"urgent:{gen_id}"),
    ]])
    await message.answer(f"Обновлённый вариант:\n\n{new_text}", reply_markup=kb)


# ── Режим 0 — бот сам предлагает темы ─────────────────────────
async def _run_propose_topics(msg_to_edit: Message, user_id: int):
    """Общий код для 'Предложи темы' и 'Предложить ещё темы'."""
    async with _Typing(msg_to_edit.chat.id):
        loop = asyncio.get_running_loop()
        search_context = await loop.run_in_executor(None, search.search_niche_trends)
        if not search_context:
            await msg_to_edit.edit_text("🔍 Поиск недоступен — генерирую из базы знаний...")
        published = db.get_published_texts()
        blacklisted = [e["text"] for e in blacklist.list_active()]
        recent_formats = _get_recent_formats()
        try:
            topics = await generator.generate_topic_suggestions(
                search_context, published, blacklisted, recent_formats
            )
        except Exception as e:
            logging.exception("generate_topic_suggestions error")
            await msg_to_edit.edit_text(f"Не удалось сгенерировать темы: {e}")
            return

    if not topics:
        await msg_to_edit.edit_text("Не удалось получить темы. Попробуй ещё раз.")
        return

    _pending_topics[user_id] = topics
    desc = lambda t: (f" — {t['description']}" if t.get("description") else "")
    lines = [f"{i+1}. «{t['topic']}»{desc(t)}" for i, t in enumerate(topics)]
    rows = []
    for i in range(len(topics)):
        rows.append([
            InlineKeyboardButton(text=f"📝 Написать #{i+1}", callback_data=f"topic:write:{i}"),
            InlineKeyboardButton(text=f"💾 Сохранить #{i+1}", callback_data=f"topic:save:{i}"),
        ])
    rows.append([InlineKeyboardButton(text="🔄 Предложить ещё темы", callback_data="topics:refresh")])
    rows.append([InlineKeyboardButton(text="🔙 Меню", callback_data="menu:show")])
    await msg_to_edit.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data == "menu:propose")
async def cb_propose(callback: CallbackQuery):
    await callback.answer()
    loading = await callback.message.answer("🔍 Ищу тренды и формирую идеи...")
    await _run_propose_topics(loading, callback.from_user.id)


@dp.callback_query(F.data == "topics:refresh")
async def cb_topics_refresh(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("🔍 Ищу новые темы...")
    await _run_propose_topics(callback.message, callback.from_user.id)


@dp.callback_query(F.data.startswith("topic:write:"))
async def cb_topic_write(callback: CallbackQuery):
    idx = int(callback.data.split(":")[-1])
    topics = _pending_topics.get(callback.from_user.id, [])
    if idx >= len(topics):
        await callback.answer("Тема устарела, предложи заново")
        return
    topic = topics[idx]
    await callback.answer()
    idea_text = f"{topic['topic']}: {topic.get('description', '')}"
    idea_id = db.add_idea(idea_text, source="text", status="in_progress")
    loading = await callback.message.answer("⏳ Генерирую варианты...")
    await _generate_and_render(loading, idea_id, idea_text, "regular", _get_recent_formats())


@dp.callback_query(F.data.startswith("topic:save:"))
async def cb_topic_save(callback: CallbackQuery):
    idx = int(callback.data.split(":")[-1])
    topics = _pending_topics.get(callback.from_user.id, [])
    if idx >= len(topics):
        await callback.answer("Тема устарела, предложи заново")
        return
    topic = topics[idx]
    idea_text = f"{topic['topic']}: {topic['description']}"
    idea_id = db.add_idea(idea_text, source="text", status="saved")
    try:
        sheets.push_idea(db.get_idea(idea_id))
    except Exception as e:
        logging.warning(f"[sheets] push_idea не удался: {e}")
    await callback.answer("Сохранено в идеи")


# ── Контент-план (пакетная генерация) ────────────────────────
def _content_plan_kb(topics: list[dict], selected: set) -> InlineKeyboardMarkup:
    rows = []
    for i, t in enumerate(topics):
        mark = "✅" if i in selected else "☐"
        rows.append([InlineKeyboardButton(
            text=f"{mark} {i+1}. {t['topic'][:35]}",
            callback_data=f"cp:toggle:{i}",
        )])
    rows.append([
        InlineKeyboardButton(text="✍️ Написать черновики", callback_data="cp:confirm"),
        InlineKeyboardButton(text="🔙 Меню", callback_data="menu:show"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data == "menu:content_plan")
async def cb_content_plan(callback: CallbackQuery):
    await callback.answer()
    loading = await callback.message.answer("🗂 Формирую контент-план...")
    free_slots = publisher.get_free_slots(4)
    count = max(len(free_slots), 3)
    # _Typing с самого начала — охватывает поиск + генерацию тем
    async with _Typing(callback.message.chat.id):
        loop = asyncio.get_running_loop()
        search_context = await loop.run_in_executor(None, search.search_niche_trends)
        published = db.get_published_texts()
        blacklisted = [e["text"] for e in blacklist.list_active()]
        recent_formats = _get_recent_formats()
        try:
            topics = await generator.generate_topic_suggestions(
                search_context, published, blacklisted, recent_formats, count=count
            )
        except Exception as e:
            await loading.edit_text(f"Не удалось сгенерировать темы: {e}")
            return

    if not topics:
        await loading.edit_text("Не удалось получить темы. Попробуй ещё раз.")
        return

    user_id = callback.from_user.id
    _content_plan[user_id] = {"topics": topics, "selected": set()}

    desc = lambda t: (f" — {t['description']}" if t.get("description") else "")
    lines = [f"{i+1}. «{t['topic']}»{desc(t)}" for i, t in enumerate(topics)]
    await loading.edit_text(
        "Выбери темы (нажми чтобы отметить ✅), потом «✍️ Написать черновики»:\n\n"
        + "\n".join(lines),
        reply_markup=_content_plan_kb(topics, set()),
    )


@dp.callback_query(F.data.startswith("cp:toggle:"))
async def cb_cp_toggle(callback: CallbackQuery):
    idx = int(callback.data.split(":")[-1])
    user_id = callback.from_user.id
    plan = _content_plan.get(user_id)
    if not plan:
        await callback.answer("Сессия устарела — запусти контент-план заново")
        return
    selected = plan["selected"]
    if idx in selected:
        selected.discard(idx)
    else:
        selected.add(idx)
    await callback.message.edit_reply_markup(reply_markup=_content_plan_kb(plan["topics"], selected))
    await callback.answer()


@dp.callback_query(F.data == "cp:confirm")
async def cb_cp_confirm(callback: CallbackQuery):
    user_id = callback.from_user.id
    plan = _content_plan.pop(user_id, None)
    if not plan or not plan["selected"]:
        await callback.answer("Ни одна тема не выбрана")
        return
    topics = plan["topics"]
    approved = [topics[i] for i in sorted(plan["selected"]) if i < len(topics)]
    recent_formats = _get_recent_formats()

    await callback.answer()
    status_msg = await callback.message.answer(f"⏳ Пишу черновики для {len(approved)} тем...")

    saved_count = 0
    for topic in approved:
        idea_text = f"{topic['topic']}: {topic.get('description', '')}"
        idea_id = db.add_idea(idea_text, source="text", status="in_progress")
        idea = db.get_idea(idea_id)
        try:
            async with _Typing(callback.message.chat.id):
                variants = await generator.generate_variants(idea_text, recent_formats=recent_formats)

            if not variants:
                await callback.message.answer(f"❌ Пустой ответ для «{topic['topic'][:40]}». Пропускаю.")
                continue

            for v in variants:
                gen_id = db.add_generation(
                    idea_id,
                    v.get("variant", 1),
                    v.get("text", ""),
                    v.get("audience", ""),
                    v.get("format", ""),
                )
                db.mark_generation_saved(gen_id)
                gen = db.get_generation(gen_id)
                try:
                    sheets.push_generation_draft(idea, gen)
                except Exception as e:
                    logging.warning(f"[sheets] push_generation_draft для контент-плана не удался: {e}")
            saved_count += 1
        except Exception as e:
            logging.exception(f"cp_confirm error for topic {topic['topic']}")
            await callback.message.answer(f"❌ Ошибка для «{topic['topic'][:40]}»: {e}")
            continue

    if saved_count > 0:
        await status_msg.edit_text(
            f"✅ {saved_count} из {len(approved)} тем → по 3 черновика в листе «Посты».\n"
            "Открой таблицу: правь тексты, выставляй даты и статус «К публикации»."
        )
    else:
        await status_msg.edit_text("❌ Не удалось написать ни одного черновика. Попробуй ещё раз.")


# ── Блэклист ──────────────────────────────────────────────────
def _blacklist_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить тему", callback_data="bl:add")],
        [InlineKeyboardButton(text="📋 Заблокированные темы", callback_data="bl:list")],
        [InlineKeyboardButton(text="📥 Добавить пачкой", callback_data="bl:bulk")],
        [InlineKeyboardButton(text="🔙 Меню", callback_data="menu:show")],
    ])


@dp.message(Command("blacklist"))
async def cmd_blacklist(message: Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer("🚫 Блэклист тем:", reply_markup=_blacklist_menu_kb())


@dp.callback_query(F.data == "menu:blacklist")
async def cb_blacklist_menu(callback: CallbackQuery):
    await callback.message.answer("🚫 Блэклист тем:", reply_markup=_blacklist_menu_kb())
    await callback.answer()


@dp.callback_query(F.data == "bl:add")
async def cb_bl_add(callback: CallbackQuery):
    _awaiting_blacklist_text.add(callback.from_user.id)
    await callback.message.answer("Напиши тему, которую нужно заблокировать:")
    await callback.answer()


@dp.callback_query(F.data == "bl:bulk")
async def cb_bl_bulk(callback: CallbackQuery):
    _awaiting_blacklist_bulk.add(callback.from_user.id)
    await callback.message.answer("Пришли темы через перенос строки (каждая с новой строки):")
    await callback.answer()


@dp.callback_query(F.data == "bl:list")
async def cb_bl_list(callback: CallbackQuery):
    entries = blacklist.list_active()
    if not entries:
        await callback.message.answer("Блэклист пуст.")
        await callback.answer()
        return
    rows = []
    for e in entries:
        mode_label = "⏳" if e["mode"] == "temporary" else "♾"
        until = f" до {e['blocked_until'][:10]}" if e["blocked_until"] else ""
        rows.append([InlineKeyboardButton(text=f"❌ {mode_label} {e['text'][:30]}{until}", callback_data=f"bl:del:{e['id']}")])
    await callback.message.answer("Заблокированные темы:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@dp.callback_query(F.data.startswith("bl:del:"))
async def cb_bl_del(callback: CallbackQuery):
    entry_id = int(callback.data.split(":")[-1])
    blacklist.remove(entry_id)
    await callback.message.edit_text("Удалено из блэклиста.")
    await callback.answer()


def _blacklist_mode_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="До конца месяца", callback_data="bl:mode:temporary"),
        InlineKeyboardButton(text="Навсегда", callback_data="bl:mode:permanent"),
    ]])


def _end_of_month() -> str:
    now = datetime.now(_MSK).replace(tzinfo=None)
    if now.month == 12:
        nxt = now.replace(year=now.year + 1, month=1, day=1)
    else:
        nxt = now.replace(month=now.month + 1, day=1)
    from datetime import timedelta
    return (nxt - timedelta(days=1)).isoformat()


@dp.callback_query(F.data.startswith("bl:mode:"))
async def cb_bl_mode(callback: CallbackQuery):
    mode = callback.data.split(":")[-1]
    user_id = callback.from_user.id
    blocked_until = _end_of_month() if mode == "temporary" else None

    if user_id in _pending_blacklist_bulk:
        lines = _pending_blacklist_bulk.pop(user_id)
        for line in lines:
            entry_id = blacklist.add_to_blacklist(line, mode, blocked_until)
            conn = db.get_conn()
            row = conn.execute("SELECT * FROM blacklist WHERE id=?", (entry_id,)).fetchone()
            conn.close()
            try:
                sheets.push_blacklist_entry(dict(row))
            except Exception as e:
                logging.warning(f"[sheets] push_blacklist не удался: {e}")
        await callback.message.edit_text(f"Добавлено {len(lines)} тем в блэклист.")
    elif user_id in _pending_blacklist_text:
        text = _pending_blacklist_text.pop(user_id)
        entry_id = blacklist.add_to_blacklist(text, mode, blocked_until)
        conn = db.get_conn()
        row = conn.execute("SELECT * FROM blacklist WHERE id=?", (entry_id,)).fetchone()
        conn.close()
        try:
            sheets.push_blacklist_entry(dict(row))
        except Exception as e:
            logging.warning(f"[sheets] push_blacklist не удался: {e}")
        await callback.message.edit_text(f"🚫 «{text}» добавлено в блэклист.")
    await callback.answer()


# ── Сохранение идеи (Режим 2) ─────────────────────────────────
async def _save_idea_flow(message: Message, raw_text: str, source: str):
    """Сохраняет идею как есть — без AI-структурирования."""
    idea_id = db.add_idea(raw_text, source=source, status="saved")
    try:
        sheets.push_idea(db.get_idea(idea_id))
    except Exception as e:
        logging.warning(f"[sheets] push_idea не удался: {e}")
    await message.answer(f"💾 Сохранено:\n{raw_text}")


# ── Главный роутер сообщений ──────────────────────────────────
@dp.message(F.text | F.voice)
async def handle_message(message: Message):
    if not is_allowed(message.from_user.id):
        return
    user_id = message.from_user.id

    # Reply-кнопка «📋 Меню» в строке ввода
    if message.text and message.text.strip() in ("📋 Меню", "Меню", "/menu"):
        await message.answer("Меню:", reply_markup=_main_menu_kb())
        return

    if user_id in _awaiting_correction:
        gen_id = _awaiting_correction.pop(user_id)
        await _handle_correction(message, gen_id)
        return

    if user_id in _awaiting_blacklist_text:
        _awaiting_blacklist_text.discard(user_id)
        text = message.text or (await transcribe_voice(message) if message.voice else "")
        _pending_blacklist_text[user_id] = text.strip()
        await message.answer(f"Тема: «{text.strip()}». На какой срок заблокировать?", reply_markup=_blacklist_mode_kb())
        return

    if user_id in _awaiting_blacklist_bulk:
        _awaiting_blacklist_bulk.discard(user_id)
        text = message.text or ""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        _pending_blacklist_bulk[user_id] = lines
        await message.answer(f"{len(lines)} тем. На какой срок заблокировать?", reply_markup=_blacklist_mode_kb())
        return

    if message.voice:
        text = await transcribe_voice(message)
        source = "voice"
    else:
        text = message.text or ""
        source = "text"

    if not text:
        await message.answer("Не удалось распознать голос. Попробуй ещё раз или напиши текстом.")
        return

    # 1. Сохранить идею — «идея для поста: ...» / «запомни/сохрани идею про ...»
    m = _IDEA_TRIGGER_RE.match(text) or _SAVE_SYNONYM_RE.match(text)
    if m:
        idea_text = text[m.end():].strip()
        await _save_idea_flow(message, idea_text, source)
        return

    if user_id in _awaiting_idea_save:
        _awaiting_idea_save.discard(user_id)
        await _save_idea_flow(message, text, source)
        return

    # 2. Ссылка на сохранённую идею по номеру — «напиши пост на тему 2 из идей»
    idea_idx = _extract_idea_index(text)
    if idea_idx is not None:
        ideas = db.list_ideas(status="saved", limit=50)
        if idea_idx < len(ideas):
            idea = ideas[idea_idx]
            loading = await message.answer(f"⏳ Генерирую по идее #{idea_idx+1}: «{idea['text'][:40]}»...")
            db.update_idea_status(idea["id"], "in_progress")
            rubric = "lifehack" if _LIFEHACK_RE.search(text) else idea.get("rubric", "regular")
            await _generate_and_render(loading, idea["id"], idea["text"], rubric, _get_recent_formats())
        else:
            await message.answer(f"Идея #{idea_idx+1} не найдена. Всего сохранено {len(ideas)}.")
        return

    # 3. Лайфхак — любое сообщение со словом «лайфхак»
    if _LIFEHACK_RE.search(text):
        # Извлекаем тему после слова «лайфхак»
        idea_text = _LIFEHACK_RE.sub("", text).strip()
        idea_text = re.sub(r'^(придумай|напиши|сделай|про|на\s+тему|как)\s*', '', idea_text, flags=re.IGNORECASE).strip()
        idea_text = idea_text or "Лайфхак: как использовать ИИ для экономии времени"
        loading = await message.answer("⏳ Готовлю лайфхак...")
        idea_id = db.add_idea(idea_text, source=source, rubric="lifehack", status="in_progress")
        await _generate_and_render(loading, idea_id, idea_text, "lifehack", _get_recent_formats())
        return

    # 4. «Придумай тему сам» — без конкретики
    if _INVENT_TOPIC_RE.match(text.strip()):
        rest = _INVENT_TOPIC_RE.sub("", text, count=1).strip()
        if not rest or len(rest) < 5:
            # Бот сам придумывает тему через generate_topic_suggestions и сразу пишет
            loading = await message.answer("🔍 Придумываю тему и пишу варианты...")
            published = db.get_published_texts()
            blacklisted = [e["text"] for e in blacklist.list_active()]
            recent_formats = _get_recent_formats()
            try:
                async with _Typing(message.chat.id):
                    topics = await generator.generate_topic_suggestions(
                        "", published, blacklisted, recent_formats, count=1
                    )
                if topics:
                    t = topics[0]
                    idea_text = f"{t['topic']}: {t['description']}"
                    idea_id = db.add_idea(idea_text, source=source, status="in_progress")
                    await _generate_and_render(loading, idea_id, idea_text, "regular", recent_formats)
                else:
                    await loading.edit_text("Не удалось придумать тему. Попробуй ещё раз.")
            except Exception as e:
                await loading.edit_text(f"Ошибка: {e}")
            return

    # 5. Обычная генерация — текст как тема
    loading = await message.answer("⏳ Обрабатываю, генерирую варианты...")
    idea_id = db.add_idea(text, source=source, status="in_progress")
    await _generate_and_render(loading, idea_id, text, "regular", _get_recent_formats())


# ── Запуск ────────────────────────────────────────────────────
async def _periodic_sheets_sync():
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, sheets.sync_from_sheets)


REVIEW_POLL_MINUTES = 3  # хардкод, не в config.py — VPS-конфиг не входит в деплой


async def _periodic_review_poll():
    """Ловит ручные правки статуса на «На согласование» прямо в Sheets (минуя кнопку бота)."""
    loop = asyncio.get_running_loop()
    try:
        pending = await loop.run_in_executor(None, sheets.get_pending_reviews)
    except Exception as e:
        logging.warning(f"[sheets] review poll не удался: {e}")
        return

    for item in pending:
        gen = db.get_generation(item["gen_id"])
        if not gen or gen.get("notified_about_review_at"):
            continue  # уже уведомлён — кнопкой или предыдущим поллингом

        try:
            link = sheets.build_post_link(item["row"], item["gid"])
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📊 Открыть этот пост", url=link),
            ]])
            await bot.send_message(
                config.OWNER_USER_ID,
                f"📬 Статус поста изменён на «На согласование» вручную в таблице\n\n"
                f"──── {gen.get('format', '')} ────\n{gen['text']}\n\n"
                "Открой «Посты», проверь текст и дату → смени статус на «К публикации».",
                reply_markup=kb,
            )
            db.mark_review_notified(item["gen_id"])
        except Exception as e:
            logging.warning(f"[bot] уведомление о ручной правке не удалось (gen_id={item['gen_id']}): {e}")


async def main():
    db.init_db()
    try:
        sheets.ensure_sheets()
    except Exception as e:
        logging.warning(f"[sheets] инициализация листов не удалась: {e}")

    publisher.init(bot, scheduler)
    scheduler.add_job(
        _periodic_sheets_sync, "cron",
        hour=config.SHEETS_SYNC_HOUR, minute=0, id="sheets_sync",
    )
    scheduler.add_job(
        _periodic_review_poll, "interval",
        minutes=REVIEW_POLL_MINUTES, id="review_poll",
    )
    scheduler.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
