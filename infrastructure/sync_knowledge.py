#!/usr/bin/env python3
"""
Синхронизация knowledge-файлов telegram-ассистента с CLAUDE.md.
Запускается автоматически из auto_commit.sh после каждой сессии.
"""

import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_CLAUDE = os.path.join(REPO, "CLAUDE.md")
KNOWLEDGE_DIR = os.path.join(REPO, "telegram-assistant", "knowledge")


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def write_if_changed(path, content):
    """Записывает файл только если содержимое изменилось."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing = read_file(path)
    if existing != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    return False


def extract_section(text, header, stop_headers=None):
    """Извлекает секцию между header и следующим ## заголовком."""
    if stop_headers:
        stop_pattern = "|".join(re.escape(h) for h in stop_headers)
        pattern = rf"## {re.escape(header)}\n(.*?)(?=\n## (?:{stop_pattern})|\Z)"
    else:
        pattern = rf"## {re.escape(header)}\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""


def sync_user_md():
    content = read_file(ROOT_CLAUDE)
    owner = extract_section(content, "Владелец")

    user_md = f"""# Профиль: Александр Бениаминов

## Роль и деятельность
- Предприниматель, управляет несколькими проектами в сфере HoReCa и IT
- Внедряет AI-инструменты в управление бизнесом (отели, рестораны)
- Управляет командами удалённо и на объектах

## Контакты и аккаунты
{owner}

## Предпочтения в работе с ботом
- Ответы короткие и по делу — максимум 2-3 предложения
- Голосовые сообщения используются активно
- Напоминания повторяются каждые 5 минут до явного подтверждения

## Стиль коммуникации
- Прямой и конкретный стиль
- Предпочитает факты и действия, а не описания
- Максимальная автономия — бот делает сам всё что может

## Техническое окружение
- Mac M2 локально + VPS Германия 185.184.122.158
- SSH алиас: `ssh server`
- Python venv на сервере: `/home/parser/venv`
- Боты: `/home/parser/bots/`

## Текущие приоритеты
<!-- Бот дополняет этот раздел через remember_fact -->
"""
    changed = write_if_changed(os.path.join(KNOWLEDGE_DIR, "user.md"), user_md)
    if changed:
        print("  user.md — обновлён")


def sync_projects_md():
    content = read_file(ROOT_CLAUDE)

    projects = extract_section(content, "Проекты",
                               stop_headers=["Общая инфраструктура"])
    infra = extract_section(content, "Общая инфраструктура",
                            stop_headers=["Git"])

    projects_md = f"""# Проекты Александра Бениаминова

{projects}

---

## Общая инфраструктура

{infra}
"""
    changed = write_if_changed(os.path.join(KNOWLEDGE_DIR, "projects.md"), projects_md)
    if changed:
        print("  projects.md — обновлён")


if __name__ == "__main__":
    print("Синхронизация knowledge-файлов...")
    sync_user_md()
    sync_projects_md()
    print("Готово.")
