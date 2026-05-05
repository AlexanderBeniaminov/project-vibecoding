"""
Тест подключения к Groq API.
Запуск: python test_claude.py
"""
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check(label, ok, detail=''):
    icon = '✅' if ok else '❌'
    print(f'  {icon} {label}', f'— {detail}' if detail else '')
    return ok


def main():
    print('=== Тест Groq API ===\n')
    all_ok = True

    print('1. Переменная окружения:')
    api_key = os.environ.get('GROQ_API_KEY', '')
    ok = bool(api_key) and api_key.startswith('gsk_')
    all_ok &= check('GROQ_API_KEY', ok,
                    f'начинается с gsk_... ({len(api_key)} символов)' if ok else 'ПУСТО или неверный формат')
    if not ok:
        print('\nСовет: ключ берётся на console.groq.com → API Keys')
        return

    print('\n2. Тестовый запрос к API:')
    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        start = time.time()
        response = client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            max_tokens=32,
            messages=[
                {'role': 'system', 'content': 'Ты — тестовый бот.'},
                {'role': 'user', 'content': 'Скажи только "ОК" и ничего больше.'},
            ],
        )
        elapsed = time.time() - start
        text = response.choices[0].message.content.strip()

        all_ok &= check('API ответил', True, f'{elapsed:.1f} сек')
        all_ok &= check('текст получен', bool(text), f'"{text}"')
        all_ok &= check('модель', True, response.model)

    except Exception as e:
        all_ok = False
        check('запрос к API', False, str(e))

    print('\n' + ('='*40))
    if all_ok:
        print('✅ Groq API работает!')
    else:
        print('❌ Есть проблемы — исправь и запусти снова.')


if __name__ == '__main__':
    main()
