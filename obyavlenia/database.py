"""
Работа с SQLite: создание таблиц, CRUD для объявлений, очередь уведомлений.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from loguru import logger

import config


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Создаёт таблицы если их нет."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS listings (
                id              TEXT NOT NULL,
                source          TEXT NOT NULL,
                url             TEXT,
                title           TEXT,
                city            TEXT,
                area_m2         REAL,
                price_rub       REAL,
                profit_month    REAL,
                payback_months  REAL,
                location_type   TEXT DEFAULT 'не указано',
                seller_type     TEXT DEFAULT 'не указано',
                published_at    TEXT,
                first_seen_at   TEXT NOT NULL,
                last_updated_at TEXT NOT NULL,
                status          TEXT DEFAULT 'активно',
                priority_flag   INTEGER DEFAULT 0,
                area_unknown_flag INTEGER DEFAULT 0,
                change_log      TEXT DEFAULT '[]',
                content_hash    TEXT,
                PRIMARY KEY (id, source)
            );

            CREATE TABLE IF NOT EXISTS notification_queue (
                queue_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,   -- 'new' | 'changed' | 'removed'
                listing_id  TEXT NOT NULL,
                source      TEXT NOT NULL,
                payload     TEXT NOT NULL,   -- JSON с данными для сообщения
                created_at  TEXT NOT NULL,
                sent        INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
            CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source);
            CREATE INDEX IF NOT EXISTS idx_queue_sent ON notification_queue(sent);
        """)
    logger.debug("БД инициализирована: {}", config.DB_PATH)


# ─── Чтение ───────────────────────────────────────────────────────────────────

def get_listing(listing_id: str, source: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM listings WHERE id=? AND source=?",
            (listing_id, source)
        ).fetchone()


def get_all_active() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM listings WHERE status != 'снято' ORDER BY first_seen_at DESC"
        ).fetchall()


def get_active_ids_by_source(source: str) -> set[str]:
    """Возвращает множество id активных объявлений из указанного источника."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM listings WHERE source=? AND status='активно'",
            (source,)
        ).fetchall()
    return {row["id"] for row in rows}


# ─── Запись ───────────────────────────────────────────────────────────────────

def insert_listing(data: dict) -> None:
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO listings
                (id, source, url, title, city, area_m2, price_rub,
                 profit_month, payback_months, location_type, seller_type,
                 published_at, first_seen_at, last_updated_at, status,
                 priority_flag, area_unknown_flag, change_log, content_hash)
            VALUES
                (:id, :source, :url, :title, :city, :area_m2, :price_rub,
                 :profit_month, :payback_months, :location_type, :seller_type,
                 :published_at, :first_seen_at, :last_updated_at, 'активно',
                 :priority_flag, :area_unknown_flag, '[]', :content_hash)
        """, {**data, "first_seen_at": now, "last_updated_at": now})


def update_listing(listing_id: str, source: str, data: dict, changes: list[dict]) -> None:
    """Обновляет запись и дописывает изменения в change_log."""
    now = datetime.now().isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT change_log FROM listings WHERE id=? AND source=?",
            (listing_id, source)
        ).fetchone()
        existing_log = json.loads(row["change_log"]) if row else []
        existing_log.extend(changes)

        conn.execute("""
            UPDATE listings SET
                url=:url, title=:title, city=:city, area_m2=:area_m2,
                price_rub=:price_rub, profit_month=:profit_month,
                payback_months=:payback_months, location_type=:location_type,
                seller_type=:seller_type, published_at=:published_at,
                last_updated_at=:now, status='активно',
                priority_flag=:priority_flag,
                area_unknown_flag=:area_unknown_flag,
                change_log=:change_log, content_hash=:content_hash
            WHERE id=:id AND source=:source
        """, {
            **data, "id": listing_id, "source": source,
            "now": now, "change_log": json.dumps(existing_log, ensure_ascii=False)
        })


def mark_removed(listing_id: str, source: str) -> None:
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE listings SET status='снято', last_updated_at=? WHERE id=? AND source=?",
            (now, listing_id, source)
        )


def restore_listing(listing_id: str, source: str) -> None:
    """Если объявление снова появилось на сайте — восстанавливаем статус."""
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE listings SET status='активно', last_updated_at=? WHERE id=? AND source=?",
            (now, listing_id, source)
        )


# ─── Очередь уведомлений ──────────────────────────────────────────────────────

def enqueue_notification(event_type: str, listing_id: str, source: str, payload: dict) -> None:
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO notification_queue (event_type, listing_id, source, payload, created_at) VALUES (?,?,?,?,?)",
            (event_type, listing_id, source, json.dumps(payload, ensure_ascii=False), now)
        )


def get_pending_notifications() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM notification_queue WHERE sent=0 ORDER BY queue_id"
        ).fetchall()


def mark_notification_sent(queue_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE notification_queue SET sent=1 WHERE queue_id=?", (queue_id,))
