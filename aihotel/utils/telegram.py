"""Отправка уведомлений через Telegram Bot API."""
import json
import urllib.request


def send(bot_token: str, chat_id, text: str) -> bool:
    if not bot_token or not chat_id or str(chat_id).strip() in ('', '0'):
        print(f'  Telegram: пропуск (нет токена или chat_id={chat_id})')
        return False
    try:
        data = json.dumps({'chat_id': int(chat_id), 'text': text}).encode()
        req = urllib.request.Request(
            f'https://api.telegram.org/bot{bot_token}/sendMessage',
            data=data,
            headers={'Content-Type': 'application/json'},
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f'  Telegram: ошибка отправки chat_id={chat_id}: {e}')
        return False
