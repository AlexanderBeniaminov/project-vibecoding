"""
Дедупликация: MD5-хэш от ключевых полей, сравнение с БД, логирование изменений.
"""
import hashlib
import json
from datetime import datetime
from typing import Optional
from loguru import logger

import database as db


def compute_hash(price_rub: Optional[float], area_m2: Optional[float], title: str) -> str:
    """MD5 от (цена + площадь + заголовок)."""
    raw = f"{price_rub}|{area_m2}|{title.strip().lower()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _diff_fields(old_row, new_data: dict) -> list[dict]:
    """Сравнивает старую запись с новыми данными, возвращает список изменений."""
    tracked = ["price_rub", "area_m2", "title", "city", "profit_month", "payback_months", "status"]
    changes = []
    now = datetime.now().isoformat()
    for field in tracked:
        old_val = old_row[field]
        new_val = new_data.get(field)
        if str(old_val) != str(new_val):
            changes.append({
                "field": field,
                "old": old_val,
                "new": new_val,
                "changed_at": now,
            })
    return changes


def process_listing(listing_data: dict) -> str:
    """
    Обрабатывает одно объявление через логику дедупликации.

    Returns:
        'new'       — добавлено впервые
        'changed'   — обновлено (был изменён контент)
        'unchanged' — без изменений
        'restored'  — было снято, снова появилось
    """
    listing_id = listing_data["id"]
    source = listing_data["source"]
    new_hash = compute_hash(
        listing_data.get("price_rub"),
        listing_data.get("area_m2"),
        listing_data.get("title", ""),
    )
    listing_data["content_hash"] = new_hash

    existing = db.get_listing(listing_id, source)

    if existing is None:
        # Совсем новое объявление
        db.insert_listing(listing_data)
        logger.info("НОВОЕ [{}] {}", source, listing_data.get("title", "")[:60])
        db.enqueue_notification("new", listing_id, source, listing_data)
        return "new"

    if existing["status"] == "снято":
        # Объявление вернулось на сайт — обновляем БД, но НЕ уведомляем
        # (это не новое объявление, мы его уже видели раньше)
        db.restore_listing(listing_id, source)
        changes = _diff_fields(existing, listing_data)
        db.update_listing(listing_id, source, listing_data, changes)
        logger.info("ВОССТАНОВЛЕНО [{}] {}", source, listing_data.get("title", "")[:60])
        return "restored"

    if existing["content_hash"] == new_hash:
        return "unchanged"

    # Изменилось содержимое
    changes = _diff_fields(existing, listing_data)
    db.update_listing(listing_id, source, listing_data, changes)
    logger.info("ИЗМЕНЕНО [{}] {} → {} изменений", source, listing_data.get("title", "")[:60], len(changes))

    # Уведомляем только если цена снизилась
    price_change = next((c for c in changes if c["field"] == "price_rub"), None)
    price_dropped = (
        price_change is not None
        and price_change["old"] is not None
        and price_change["new"] is not None
        and float(price_change["new"]) < float(price_change["old"])
    )
    if price_dropped:
        db.enqueue_notification(
            "changed", listing_id, source,
            {**listing_data, "changes": [price_change]}
        )
    return "changed"


def mark_gone_listings(source: str, seen_ids: set[str]) -> int:
    """
    Помечает 'снято' все активные объявления источника, которых нет в seen_ids.
    Возвращает количество снятых.
    """
    active_ids = db.get_active_ids_by_source(source)
    removed_ids = active_ids - seen_ids
    for rid in removed_ids:
        db.mark_removed(rid, source)
        logger.info("СНЯТО [{}] id={}", source, rid)
        db.enqueue_notification("removed", rid, source, {"id": rid, "source": source})
    return len(removed_ids)
