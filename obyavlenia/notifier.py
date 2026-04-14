"""
Уведомления через Макс (ICQ New) Bot API.
Документация: https://icq.com/botapi/

Бот создаётся через @metabot в приложении Макс.
API не требует сторонних библиотек — только requests.

Все сообщения идут через очередь в БД: если сеть недоступна,
сообщения отправятся при следующем запуске.
"""
import json
from datetime import datetime
from typing import Optional
from loguru import logger

import requests as _requests

import config
import database as db


# ─── Форматирование чисел ─────────────────────────────────────────────────────

def _fmt_money(val: Optional[float]) -> str:
    if val is None:
        return "не указана"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f} млн руб."
    if val >= 1_000:
        return f"{val / 1_000:.0f} тыс. руб."
    return f"{val:.0f} руб."


def _fmt_area(val: Optional[float], unknown_flag: bool) -> str:
    if unknown_flag or val is None:
        return "не указана ❓"
    return f"{val:.0f} м²"


def _fmt_payback(val: Optional[float]) -> str:
    if val is None:
        return "не указана"
    if val >= 12:
        years = val / 12
        return f"{years:.1f} лет ({val:.0f} мес.)"
    return f"{val:.0f} мес."


# ─── Шаблоны сообщений ───────────────────────────────────────────────────────

def _build_new_message(data: dict) -> str:
    priority_line = ""
    if data.get("priority_flag"):
        priority_line = "⭐ ПРИОРИТЕТ — площадь ≥ 1000 м²\n"

    return (
        f"🆕 НОВОЕ ОБЪЯВЛЕНИЕ\n"
        f"{priority_line}"
        f"📍 Город: {data.get('city', 'не указан')}\n"
        f"🏢 {data.get('title', '—')}\n"
        f"📐 Площадь: {_fmt_area(data.get('area_m2'), bool(data.get('area_unknown_flag')))}\n"
        f"💰 Цена: {_fmt_money(data.get('price_rub'))}\n"
        f"📈 Прибыль: {_fmt_money(data.get('profit_month'))}/мес\n"
        f"⏱ Окупаемость: {_fmt_payback(data.get('payback_months'))}\n"
        f"🏬 Расположение: {data.get('location_type', 'не указано')}\n"
        f"👤 Продавец: {data.get('seller_type', 'не указано')}\n"
        f"📌 Источник: {data.get('source', '—')}\n"
        f"🔗 {data.get('url', '')}"
    )


def _build_changed_message(data: dict) -> str:
    price_change = next((c for c in data.get("changes", []) if c["field"] == "price_rub"), None)
    if price_change:
        old_price = _fmt_money(price_change.get("old"))
        new_price = _fmt_money(price_change.get("new"))
        try:
            old_f = float(price_change["old"])
            new_f = float(price_change["new"])
            diff = old_f - new_f
            diff_line = f"  Было: {old_price}\n  Стало: {new_price}\n  Скидка: {_fmt_money(diff)}\n"
        except Exception:
            diff_line = f"  {old_price} → {new_price}\n"
        changes_text = diff_line
    else:
        changes_text = ""

    return (
        f"📉 СНИЖЕНИЕ ЦЕНЫ\n"
        f"📍 {data.get('city', '—')} — {data.get('title', '—')}\n"
        f"{changes_text}"
        f"📌 Источник: {data.get('source', '—')}\n"
        f"🔗 {data.get('url', '')}"
    )


def _build_removed_message(data: dict) -> str:
    return (
        f"📭 СНЯТО С ПРОДАЖИ\n"
        f"Источник: {data.get('source')} | ID: {data.get('id')}"
    )


def build_summary_message(stats: dict) -> str:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    errors = stats.get("errors", 0)
    error_line = f"\n⚠️ Ошибок при парсинге: {errors}" if errors else ""
    return (
        f"📊 Итоги сканирования {now}\n"
        f"🆕 Новых: {stats.get('new', 0)}\n"
        f"🔄 Изменено: {stats.get('changed', 0)}\n"
        f"✅ Без изменений: {stats.get('unchanged', 0)}\n"
        f"📭 Снято с продажи: {stats.get('removed', 0)}"
        f"{error_line}"
    )


# ─── Отправка через Макс Bot API ─────────────────────────────────────────────

def send_message(text: str) -> bool:
    """
    Отправляет сообщение через Макс (ICQ New) Bot API.
    Возвращает True при успехе.
    """
    if not config.ICQ_BOT_TOKEN or not config.ICQ_CHAT_ID:
        logger.warning("ICQ_BOT_TOKEN или ICQ_CHAT_ID не заполнены в .env — уведомление пропущено")
        return False

    url = f"{config.ICQ_API_BASE}/messages"
    headers = {
        "Authorization": config.ICQ_BOT_TOKEN,
        "Content-Type": "application/json",
    }

    try:
        resp = _requests.post(
            url,
            headers=headers,
            params={"chat_id": config.ICQ_CHAT_ID},
            json={"text": text},
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("message"):
            return True
        logger.warning("Макс API вернул ошибку: {}", result)
        return False
    except Exception as e:
        logger.warning("Ошибка отправки в Макс: {}", e)
        return False


# ─── Обработка очереди ───────────────────────────────────────────────────────

def send_pending_notifications() -> None:
    """Отправляет все накопленные в очереди уведомления."""
    if not config.ICQ_BOT_TOKEN or not config.ICQ_CHAT_ID:
        logger.warning("Макс не настроен (нет токена или chat_id). Уведомления не отправляются.")
        return

    pending = db.get_pending_notifications()
    if not pending:
        return

    logger.info("Отправка {} уведомлений в Макс...", len(pending))
    for row in pending:
        payload = json.loads(row["payload"])
        event_type = row["event_type"]

        if event_type == "new":
            text = _build_new_message(payload)
        elif event_type == "changed":
            text = _build_changed_message(payload)
        elif event_type == "removed":
            text = _build_removed_message(payload)
        else:
            continue

        if send_message(text):
            db.mark_notification_sent(row["queue_id"])
        else:
            logger.warning("Не удалось отправить уведомление queue_id={}. Попробуем позже.", row["queue_id"])
            break  # прекращаем, отправим при следующем запуске


def send_summary(stats: dict) -> None:
    text = build_summary_message(stats)
    send_message(text)


def send_error_alert(error_text: str) -> None:
    text = f"⚠️ Парсер завершился с ошибкой:\n{error_text[:500]}"
    send_message(text)
