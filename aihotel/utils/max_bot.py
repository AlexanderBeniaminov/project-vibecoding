import os
import requests


def send_message(user_id: str, text: str) -> bool:
    token = os.environ['MAX_BOT_TOKEN']
    url = f"https://botapi.max.ru/messages?access_token={token}"
    payload = {"user_id": int(user_id), "text": text}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"ОШИБКА MAX: статус {response.status_code} для user_id={user_id}")
            return False
        return True
    except Exception as e:
        print(f"ОШИБКА MAX: не удалось отправить user_id={user_id}: {e}")
        return False


def send_owner(text: str) -> bool:
    owner_id = os.environ['MAX_OWNER_ID']
    return send_message(owner_id, text)


def send_to_team(messages_dict: dict) -> None:
    # messages_dict = {user_id: text}
    for user_id, text in messages_dict.items():
        ok = send_message(str(user_id), text)
        if ok:
            print(f"  ✓ Отправлено user_id={user_id}")
        else:
            print(f"  ✗ Ошибка для user_id={user_id}")
