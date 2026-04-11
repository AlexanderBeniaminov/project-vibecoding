"""
max_bot.py — работа с MAX мессенджером (max.ru, бывш. TamTam).

Документация API: https://dev.max.ru/
Base URL: https://botapi.max.ru

Авторизация:
    Все запросы: ?access_token=MAX_BOT_TOKEN

Основные методы:
    GET  /me                          — информация о боте
    POST /messages                    — отправить сообщение (user_id или chat_id)
    GET  /updates                     — получить новые обновления (long-polling)

Переменные окружения:
    MAX_BOT_TOKEN      — токен бота (из личного кабинета MAX)
    MAX_OWNER_USER_ID  — user_id собственника
    MAX_ADMIN_USER_ID  — user_id администратора
    MAX_DEV_USER_ID    — user_id разработчика (алерты)
"""

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MAX_API_BASE = "https://botapi.max.ru"
DEFAULT_TIMEOUT = 30
LONG_POLL_TIMEOUT = 60  # секунд, максимальный long-poll для одного запроса


class MaxBot:
    """Клиент для работы с MAX Bot API."""

    def __init__(self, token: str):
        if not token:
            raise ValueError("MAX_BOT_TOKEN не задан")
        self.token = token
        self._session = requests.Session()
        self._session.params = {"access_token": token}  # type: ignore[assignment]
        self._marker: Optional[int] = None  # маркер для getUpdates

    # ------------------------------------------------------------------
    # Отправка сообщений
    # ------------------------------------------------------------------

    def send_message(self, user_id: str, text: str) -> bool:
        """
        Отправить текстовое сообщение пользователю.
        Возвращает True при успехе.
        """
        if not user_id:
            logger.warning("send_message: user_id не задан, пропускаем")
            return False
        url = f"{MAX_API_BASE}/messages"
        payload = {
            "recipient": {"user_id": int(user_id)},
            "type": "message",
            "body": {"text": text},
        }
        try:
            resp = self._session.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
            if resp.ok:
                logger.info(f"MAX: сообщение отправлено user_id={user_id}")
                return True
            logger.error(f"MAX send_message ошибка {resp.status_code}: {resp.text}")
        except requests.RequestException as e:
            logger.error(f"MAX send_message сетевая ошибка: {e}")
        return False

    def send_to_many(self, user_ids: list[str], text: str):
        """Отправить одно сообщение нескольким пользователям."""
        for uid in user_ids:
            if uid:
                self.send_message(uid, text)

    # ------------------------------------------------------------------
    # Получение обновлений
    # ------------------------------------------------------------------

    def _get_updates(self, timeout: int = LONG_POLL_TIMEOUT) -> list[dict]:
        """
        Один вызов GET /updates с long-polling.
        Автоматически обновляет self._marker.
        """
        url = f"{MAX_API_BASE}/updates"
        params: dict = {"timeout": timeout}
        if self._marker is not None:
            params["marker"] = self._marker
        try:
            resp = self._session.get(url, params=params, timeout=timeout + 10)
            if not resp.ok:
                logger.error(f"MAX get_updates ошибка {resp.status_code}: {resp.text}")
                return []
            data = resp.json()
            updates = data.get("updates", [])
            if "marker" in data:
                self._marker = data["marker"]
            return updates
        except requests.RequestException as e:
            logger.error(f"MAX get_updates сетевая ошибка: {e}")
            return []

    def poll_for_reply(
        self,
        from_user_id: str,
        timeout_sec: int = 1800,  # 30 минут по умолчанию
        check_interval: int = 30,  # проверять каждые 30 сек
    ) -> Optional[str]:
        """
        Ждать текстовый ответ от конкретного пользователя.

        from_user_id — ожидаемый отправитель (администратор).
        timeout_sec  — максимальное время ожидания в секундах.
        check_interval — интервал между проверками.

        Возвращает текст первого подходящего сообщения или None при таймауте.
        """
        if not from_user_id:
            logger.warning("poll_for_reply: from_user_id не задан")
            return None

        target_id = int(from_user_id)
        deadline = time.monotonic() + timeout_sec
        logger.info(f"MAX: ожидание ответа от user_id={target_id} в течение {timeout_sec} сек...")

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            # Используем short poll, чтобы не превышать оставшееся время
            poll_time = min(check_interval, int(remaining), LONG_POLL_TIMEOUT)
            updates = self._get_updates(timeout=poll_time)

            for update in updates:
                msg = _extract_message(update)
                if msg is None:
                    continue
                sender_id = msg.get("sender_id")
                text = msg.get("text", "").strip()
                if sender_id == target_id and text:
                    logger.info(f"MAX: получен ответ от user_id={target_id}: {text[:80]!r}")
                    return text

            # Небольшая пауза, чтобы не спамить API при коротком remaining
            if time.monotonic() < deadline:
                time.sleep(min(5, deadline - time.monotonic()))

        logger.info(f"MAX: ответ от user_id={target_id} не получен за {timeout_sec} сек")
        return None

    # ------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------

    def flush_updates(self):
        """
        Слить все накопленные обновления (пропустить).
        Вызывать перед началом polling, чтобы не обработать старые сообщения.
        """
        logger.info("MAX: сброс накопленных обновлений...")
        while True:
            updates = self._get_updates(timeout=1)
            if not updates:
                break
        logger.info("MAX: очередь обновлений очищена")


def _extract_message(update: dict) -> Optional[dict]:
    """
    Извлечь полезную информацию из объекта update MAX API.
    Возвращает словарь {sender_id, text} или None.
    """
    # Тип события — входящее сообщение
    if update.get("update_type") not in ("message_created", "message_callback"):
        return None

    body = update.get("message", {}) or {}
    # Структура: update.message.sender.user_id
    sender = body.get("sender", {}) or {}
    sender_id = sender.get("user_id")
    msg_body = body.get("body", {}) or {}
    text = msg_body.get("text", "")

    if sender_id is None:
        return None

    return {"sender_id": int(sender_id), "text": text}


# ------------------------------------------------------------------
# Вспомогательные функции-обёртки (без создания экземпляра вручную)
# ------------------------------------------------------------------

def make_bot(token: str) -> MaxBot:
    """Создать экземпляр MaxBot. Выбросит ValueError если токен пустой."""
    return MaxBot(token)


def send_or_log(bot: Optional["MaxBot"], user_id: str, text: str, label: str = ""):
    """
    Отправить сообщение если бот настроен, иначе залогировать.
    Удобна для вызова в блоках, где MAX может быть не настроен.
    """
    if bot is None or not user_id:
        logger.warning(f"MAX не настроен — сообщение не отправлено [{label}]: {text[:60]!r}")
        return
    bot.send_message(user_id, text)
