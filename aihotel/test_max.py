"""
Тест отправки сообщения через MAX Bot.
Запуск: python test_max.py

Что проверяет:
1. MAX_BOT_TOKEN и MAX_OWNER_ID заданы
2. Отправляет тестовое сообщение собственнику (MAX_OWNER_ID)
3. Проверяет код ответа API

ВАЖНО: запусти этот тест когда ты сам в MAX — придёт тестовое сообщение.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check(label, ok, detail=''):
    icon = '✅' if ok else '❌'
    print(f'  {icon} {label}', f'— {detail}' if detail else '')
    return ok


def main():
    print('=== Тест MAX Bot ===\n')
    all_ok = True

    # 1. Переменные
    print('1. Переменные окружения:')
    token = os.environ.get('MAX_BOT_TOKEN', '')
    owner_id = os.environ.get('MAX_OWNER_ID', '')
    team_ids_raw = os.environ.get('MAX_TEAM_IDS', '')

    ok_token = bool(token)
    ok_owner = bool(owner_id) and owner_id.isdigit()
    all_ok &= check('MAX_BOT_TOKEN', ok_token, f'{len(token)} символов' if ok_token else 'ПУСТО')
    all_ok &= check('MAX_OWNER_ID', ok_owner,
                    f'ID = {owner_id}' if ok_owner else 'ПУСТО или не число')

    if team_ids_raw:
        ids = [x.strip() for x in team_ids_raw.split(',') if x.strip()]
        check('MAX_TEAM_IDS', True, f'{len(ids)} ID: {ids}')
    else:
        check('MAX_TEAM_IDS', False, 'ПУСТО — заполни перед рассылкой задач')

    if not (ok_token and ok_owner):
        print('\nСовет: узнай токен у @BotFather в MAX, ID — в настройках своего профиля MAX')
        return

    # 2. Тестовая отправка
    print('\n2. Отправка тестового сообщения собственнику:')
    try:
        import requests
        url = f'https://botapi.max.ru/messages?access_token={token}'
        payload = {
            'user_id': int(owner_id),
            'text': '🤖 Тест AI-системы ВК Губаха: подключение работает!'
        }
        resp = requests.post(url, json=payload, timeout=10)
        ok = resp.status_code == 200
        all_ok &= check(f'HTTP {resp.status_code}', ok,
                        'сообщение отправлено' if ok else f'ошибка: {resp.text[:200]}')

        if not ok:
            print('\nВозможные причины:')
            print('  — Токен неверный или устаревший')
            print('  — MAX_OWNER_ID неверный (нужен числовой ID, не username)')
            print('  — Бот не активирован (напиши боту /start в MAX)')
            print('  — MAX API временно недоступен')

    except Exception as e:
        all_ok = False
        check('запрос к MAX API', False, str(e))

    print('\n' + ('='*40))
    if all_ok:
        print('✅ MAX Bot работает! Проверь, пришло ли тестовое сообщение.')
    else:
        print('❌ Есть проблемы — исправь и запусти снова.')


if __name__ == '__main__':
    main()
