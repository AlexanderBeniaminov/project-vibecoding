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
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
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

# ── Состояния в памяти (паттерн как в assistant_bot.py — простые dict, без aiogram FSM) ──
_awaiting_idea_save: set[int] = set()           # пользователь нажал «Сохранить идею», ждём текст/голос
_awaiting_correction: dict[int, int] = {}       # user_id → gen_id, ждём текст правки
_awaiting_blacklist_text: set[int] = set()      # ждём тему для добавления в блэклист
_awaiting_blacklist_bulk: set[int] = set()      # ждём список тем через перенос строки
_pending_blacklist_text: dict[int, str] = {}    # user_id → тема, ждём выбор режима
_pending_blacklist_bulk: dict[int, list[str]] = {}
_pending_blacklist_confirm: dict[int, dict] = {}  # user_id → {"idea_id":..., "text":..., "rubric":...}
_pending_topics: dict[int, list[dict]] = {}     # user_id → предложенные темы (Режим 0)
_ideas_page: dict[int, int] = {}

_IDEA_TRIGGER_RE = re.compile(r'^идея(\s+для\s+поста)?\W*', re.IGNORECASE)


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


# ── Транскрипция голоса (паттерн из assistant_bot.py, упрощённо) ──
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


# ── Главное меню ──────────────────────────────────────────────
def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💡 Предложи темы", callback_data="menu:propose"),
         InlineKeyboardButton(text="📋 Мои идеи", callback_data="ideas:page:0")],
        [InlineKeyboardButton(text="📅 Расписание", callback_data="menu:schedule"),
         InlineKeyboardButton(text="🚫 Блэклист", callback_data="menu:blacklist")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
    ])


_HELP_TEXT = (
    "🤖 *Content Bot — шпаргалка*\n\n"
    "*Сразу написать пост:* наговори или напиши тему — пришлю 3 варианта.\n"
    "*Сохранить идею на потом:* «идея для поста: ...» или кнопка [📋 Мои идеи].\n"
    "*Бот сам предложит темы:* кнопка [💡 Предложи темы].\n"
    "*Расписание публикаций:* /schedule\n"
    "*Блэклист тем:* /blacklist\n\n"
    "Публикация — кнопками [✅ Запланировать] или [⚡ Сейчас] под каждым вариантом."
)


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer(
        "Привет! Я помогу писать и публиковать посты для «ИИндустрия Развлечений».\n\n"
        "Наговори тему — пришлю 3 варианта. Или выбери действие в меню:",
        reply_markup=_main_menu_kb(),
    )


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


# ── /schedule ─────────────────────────────────────────────────
def _schedule_text() -> str:
    lines = []
    for dt in publisher.next_publish_dates(6):
        conn = db.get_conn()
        row = conn.execute(
            "SELECT text FROM ideas WHERE status='scheduled' AND scheduled_at=?", (dt.isoformat(),)
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
    loading = await callback.message.answer("⏳ Обрабатываю, генерирую варианты...")
    db.update_idea_status(idea_id, "in_progress")
    await _generate_and_render(loading, idea_id, idea["text"], idea["rubric"])
    await callback.answer()


# ── Генерация (общее ядро для Режима 1 и выбора сохранённой идеи) ──
def _variant_format_label(fmt: str) -> str:
    return fmt


def _result_keyboard(generations: list[dict], idea_id: int) -> InlineKeyboardMarkup:
    rows = []
    for g in generations:
        rows.append([
            InlineKeyboardButton(text="⚙️ Скорректировать", callback_data=f"corr:{g['id']}"),
            InlineKeyboardButton(text="✅ Запланировать", callback_data=f"sched:{g['id']}"),
            InlineKeyboardButton(text="⚡ Сейчас", callback_data=f"now:{g['id']}"),
        ])
    rows.append([InlineKeyboardButton(text="🔄 Другие варианты", callback_data=f"regen:{idea_id}")])
    rows.append([InlineKeyboardButton(text="🔙 Меню", callback_data="menu:show")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _render_variants_text(generations: list[dict]) -> str:
    blocks = []
    for g in generations:
        blocks.append(f"──── Вариант {g['variant_num']} · {_variant_format_label(g['format'])} ────\n{g['text']}")
    return "\n\n".join(blocks)


async def _generate_and_render(loading_msg: Message, idea_id: int, idea_text: str, rubric: str):
    matched = await blacklist.check_against_blacklist(idea_text)
    if matched:
        _pending_blacklist_confirm[loading_msg.chat.id] = {"idea_id": idea_id, "text": idea_text, "rubric": rubric}
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Да, генерировать", callback_data="blconfirm:yes"),
            InlineKeyboardButton(text="Нет, отмена", callback_data="blconfirm:no"),
        ]])
        await loading_msg.edit_text(f"⚠️ Тема похожа на заблокированную: «{matched}». Всё равно генерировать?", reply_markup=kb)
        return
    await _do_generate(loading_msg, idea_id, idea_text, rubric)


async def _do_generate(loading_msg: Message, idea_id: int, idea_text: str, rubric: str):
    try:
        async with _Typing(loading_msg.chat.id):
            variants = await generator.generate_variants(idea_text, rubric)
    except Exception as e:
        await loading_msg.edit_text(f"Не удалось сгенерировать варианты: {e}")
        return
    generations = []
    for v in variants:
        gen_id = db.add_generation(idea_id, v["variant"], v["text"], v["audience"], v["format"])
        generations.append(db.get_generation(gen_id))

    idea = db.get_idea(idea_id)
    try:
        sheets.push_idea(idea)
        sheets.push_generations(idea, generations)
    except Exception as e:
        logging.warning(f"[sheets] push не удался: {e}")

    await loading_msg.edit_text(_render_variants_text(generations), reply_markup=_result_keyboard(generations, idea_id))


@dp.callback_query(F.data == "blconfirm:yes")
async def cb_blconfirm_yes(callback: CallbackQuery):
    pending = _pending_blacklist_confirm.pop(callback.message.chat.id, None)
    if not pending:
        await callback.answer()
        return
    await _do_generate(callback.message, pending["idea_id"], pending["text"], pending["rubric"])
    await callback.answer()


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
    loading = await callback.message.answer("⏳ Генерирую другие варианты...")
    await _do_generate(loading, idea_id, idea["text"], idea["rubric"])
    await callback.answer()


# ── Корректировка ────────────────────────────────────────────
@dp.callback_query(F.data.startswith("corr:"))
async def cb_correct(callback: CallbackQuery):
    gen_id = int(callback.data.split(":")[-1])
    gen = db.get_generation(gen_id)
    if not gen:
        await callback.answer("Вариант не найден")
        return
    _awaiting_correction[callback.from_user.id] = gen_id
    await callback.message.answer(
        f"Текущий текст (скопируй, исправь и пришли целиком — или просто напиши что изменить):\n\n{gen['text']}"
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
    idea = db.get_idea(gen["idea_id"])
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚙️ Скорректировать", callback_data=f"corr:{gen_id}"),
        InlineKeyboardButton(text="✅ Запланировать", callback_data=f"sched:{gen_id}"),
        InlineKeyboardButton(text="⚡ Сейчас", callback_data=f"now:{gen_id}"),
    ]])
    await message.answer(f"Обновлённый вариант:\n\n{new_text}", reply_markup=kb)


# ── Публикация ────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("now:"))
async def cb_publish_now(callback: CallbackQuery):
    gen_id = int(callback.data.split(":")[-1])
    gen = db.get_generation(gen_id)
    if not gen:
        await callback.answer("Вариант не найден")
        return
    result = await publisher.publish_now(gen["idea_id"], gen_id)
    idea = db.get_idea(gen["idea_id"])
    try:
        sheets.push_published(idea, gen)
    except Exception as e:
        logging.warning(f"[sheets] push_published не удался: {e}")
    await callback.message.answer(result)
    await callback.answer()


@dp.callback_query(F.data.startswith("sched:"))
async def cb_schedule_pick(callback: CallbackQuery):
    gen_id = int(callback.data.split(":")[-1])
    slots = publisher.get_free_slots(3)
    if not slots:
        await callback.answer("Нет свободных слотов")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{publisher.DAY_NAMES[dt.weekday()]} {dt.strftime('%d.%m')} {dt.strftime('%H:%M')}",
                               callback_data=f"slot:{gen_id}:{dt.isoformat()}")]
        for dt in slots
    ])
    await callback.message.answer("Выбери слот публикации:", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("slot:"))
async def cb_slot_pick(callback: CallbackQuery):
    _, gen_id_raw, dt_raw = callback.data.split(":", 2)
    gen_id = int(gen_id_raw)
    dt = datetime.fromisoformat(dt_raw)
    gen = db.get_generation(gen_id)
    if not gen:
        await callback.answer("Вариант не найден")
        return
    publisher.schedule_post(gen["idea_id"], gen_id, dt)
    idea = db.get_idea(gen["idea_id"])
    try:
        sheets.push_scheduled(idea, gen, dt)
    except Exception as e:
        logging.warning(f"[sheets] push_scheduled не удался: {e}")
    await callback.message.answer(f"📅 Запланировано на {dt.strftime('%d.%m.%Y %H:%M')} — можешь редактировать в таблице")
    await callback.answer()


# ── Режим 0 — бот сам предлагает темы ───────────────────────
@dp.callback_query(F.data == "menu:propose")
async def cb_propose(callback: CallbackQuery):
    loading = await callback.message.answer("🔍 Ищу тренды и формирую идеи...")
    loop = asyncio.get_running_loop()
    search_context = await loop.run_in_executor(None, search.search_niche_trends)
    if not search_context:
        await loading.edit_text("🔍 Поиск недоступен — генерирую из базы знаний...")
    published = db.get_published_texts()
    blacklisted = [e["text"] for e in blacklist.list_active()]
    try:
        async with _Typing(callback.message.chat.id):
            topics = await generator.generate_topic_suggestions(search_context, published, blacklisted)
    except Exception as e:
        await loading.edit_text(f"Не удалось сгенерировать темы: {e}")
        await callback.answer()
        return
    _pending_topics[callback.from_user.id] = topics

    lines = [f"{i+1}. «{t['topic']}» — {t['description']}" for i, t in enumerate(topics)]
    rows = []
    for i in range(len(topics)):
        rows.append([
            InlineKeyboardButton(text=f"📝 Написать #{i+1}", callback_data=f"topic:write:{i}"),
            InlineKeyboardButton(text=f"💾 Сохранить #{i+1}", callback_data=f"topic:save:{i}"),
        ])
    rows.append([InlineKeyboardButton(text="🔙 Меню", callback_data="menu:show")])
    await loading.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@dp.callback_query(F.data.startswith("topic:write:"))
async def cb_topic_write(callback: CallbackQuery):
    idx = int(callback.data.split(":")[-1])
    topics = _pending_topics.get(callback.from_user.id, [])
    if idx >= len(topics):
        await callback.answer("Тема устарела, предложи заново")
        return
    topic = topics[idx]
    idea_text = f"{topic['topic']}: {topic['description']}"
    idea_id = db.add_idea(idea_text, source="text", status="in_progress")
    loading = await callback.message.answer("⏳ Обрабатываю, генерирую варианты...")
    await _generate_and_render(loading, idea_id, idea_text, "regular")
    await callback.answer()


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


# ── Сохранение идеи (Режим 2) ───────────────────────────────
async def _save_idea_flow(message: Message, raw_text: str, source: str):
    try:
        async with _Typing(message.chat.id):
            structured = await generator.structure_idea(raw_text)
        title = structured.get("title") or raw_text[:60]
        desc = structured.get("description", "")
    except Exception:
        title, desc = raw_text[:60], ""
    idea_text = f"{title}: {desc}" if desc else title
    idea_id = db.add_idea(idea_text, source=source, status="saved")
    try:
        sheets.push_idea(db.get_idea(idea_id))
    except Exception as e:
        logging.warning(f"[sheets] push_idea не удался: {e}")
    await message.answer(f"💾 Сохранено:\n📌 Тема: {title}\n📝 Суть: {desc}" if desc else f"💾 Сохранено:\n📌 Тема: {title}")


# ── Главный роутер сообщений ─────────────────────────────────
@dp.message(F.text | F.voice)
async def handle_message(message: Message):
    if not is_allowed(message.from_user.id):
        return
    user_id = message.from_user.id

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

    m = _IDEA_TRIGGER_RE.match(text)
    if m:
        idea_text = text[m.end():].strip()
        await _save_idea_flow(message, idea_text, source)
        return

    if user_id in _awaiting_idea_save:
        _awaiting_idea_save.discard(user_id)
        await _save_idea_flow(message, text, source)
        return

    loading = await message.answer("⏳ Обрабатываю, генерирую варианты...")
    idea_id = db.add_idea(text, source=source, status="in_progress")
    await _generate_and_render(loading, idea_id, text, "regular")


# ── Запуск ────────────────────────────────────────────────────
async def _periodic_sheets_sync():
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, sheets.sync_from_sheets)


async def main():
    db.init_db()
    try:
        sheets.ensure_sheets()
    except Exception as e:
        logging.warning(f"[sheets] инициализация листов не удалась: {e}")

    publisher.init(bot, scheduler)
    for hour in config.SHEETS_SYNC_HOURS:
        scheduler.add_job(_periodic_sheets_sync, "cron", hour=hour, minute=0, id=f"sheets_sync_{hour}")
    scheduler.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
