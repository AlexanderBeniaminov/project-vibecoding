"""
get_user_ids.py — скрипт для получения user_id пользователей MAX.

Запуск:
    python scripts/get_user_ids.py

Что делает:
    1. Подключается к боту
    2. Ждёт входящих сообщений 5 минут
    3. Выводит user_id каждого кто написал боту

Инструкция:
    1. Запусти скрипт
    2. Скажи Максу (собственнику) — написать боту @id771605524164_bot любое сообщение
    3. Скажи администратору — написать боту любое сообщение
    4. Ты тоже напиши боту (для MAX_DEV_USER_ID)
    5. Скрипт покажет user_id каждого
"""

import time
import requests

TOKEN = "f9LHodD0cOIG6fQGeZPQp05LkshDtn6oJa67MuT13xyr_n8dyd5RVyVyCd5Vl_dL7EetD2Lo5I9fB_JAn5Cb"
BASE_URL = "https://botapi.max.ru"
HEADERS = {"Authorization": TOKEN}

def get_me():
    r = requests.get(f"{BASE_URL}/me", headers=HEADERS, timeout=10)
    return r.json()

def get_updates(marker=None, timeout=30):
    params = {"timeout": timeout}
    if marker:
        params["marker"] = marker
    r = requests.get(f"{BASE_URL}/updates", headers=HEADERS, params=params, timeout=timeout + 10)
    return r.json()

def main():
    bot = get_me()
    print(f"\n✅ Бот подключён: {bot['name']} (@{bot['username']})")
    print(f"   Bot user_id: {bot['user_id']}")
    print("\n" + "="*50)
    print("Попроси написать боту:")
    print(f"  1. Макс (собственник) → напишет @{bot['username']} любое сообщение")
    print(f"  2. Администратор → напишет @{bot['username']} любое сообщение")
    print(f"  3. Ты (разработчик) → напишешь @{bot['username']} любое сообщение")
    print("\nОжидаю сообщения 5 минут...")
    print("="*50 + "\n")

    seen_users = {}
    marker = None
    deadline = time.time() + 300  # 5 минут

    # Сначала сбрасываем старые обновления
    data = get_updates(timeout=1)
    marker = data.get("marker")

    while time.time() < deadline:
        remaining = int(deadline - time.time())
        print(f"\r⏳ Осталось: {remaining} сек... (получено {len(seen_users)} пользователей)", end="", flush=True)

        try:
            data = get_updates(marker=marker, timeout=min(30, remaining))
        except Exception as e:
            print(f"\nОшибка: {e}")
            time.sleep(2)
            continue

        if "marker" in data:
            marker = data["marker"]

        for update in data.get("updates", []):
            msg = update.get("message", {})
            sender = msg.get("sender", {})
            uid = sender.get("user_id")
            name = sender.get("name", "?")
            username = sender.get("username", "")
            text = msg.get("body", {}).get("text", "")

            if uid and uid not in seen_users:
                seen_users[uid] = {"name": name, "username": username}
                print(f"\n\n📨 Новый пользователь написал боту!")
                print(f"   Имя:      {name}")
                print(f"   Username: @{username}" if username else "   Username: нет")
                print(f"   user_id:  {uid}  ← СОХРАНИ ЭТО!")
                print(f"   Текст:    {text[:50]!r}")

    print(f"\n\n{'='*50}")
    print("Итог — user_id пользователей:")
    for uid, info in seen_users.items():
        print(f"  {info['name']:30s} → {uid}")

    if not seen_users:
        print("  Никто не написал боту за 5 минут.")

    print("\nДобавь в GitHub Secrets:")
    print(f"  MAX_BOT_TOKEN     = {TOKEN}")
    for uid, info in seen_users.items():
        print(f"  MAX_???_USER_ID   = {uid}  ({info['name']})")

if __name__ == "__main__":
    main()
