"""Отправка уведомлений через MAX (platform-api.max.ru)."""
import os
import urllib.request
import json


MAX_PLATFORM_API = "https://platform-api.max.ru"


def send(user_id, text: str) -> bool:
    token = os.environ.get('MAX_BOT_TOKEN', '')
    if not token or not user_id or str(user_id).strip() in ('', '0'):
        print(f'  MAX: пропуск (нет токена или user_id={user_id})')
        return False
    try:
        url = f"{MAX_PLATFORM_API}/messages?user_id={int(user_id)}"
        data = json.dumps({"text": text}).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token}',
            },
        )
        resp = urllib.request.urlopen(req, timeout=10)
        if resp.status < 300:
            return True
        print(f'  MAX: ошибка {resp.status}')
        return False
    except Exception as e:
        print(f'  MAX: ошибка отправки user_id={user_id}: {e}')
        return False
