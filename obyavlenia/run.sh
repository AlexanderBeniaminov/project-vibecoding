#!/bin/bash
# Запуск парсера (Mac / Linux)
# Разовый запуск:        bash run.sh
# По расписанию (09:00): bash run.sh --schedule

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "❌ Виртуальное окружение не найдено. Сначала запусти: bash install.sh"
    exit 1
fi

source venv/bin/activate

if [ "$1" = "--schedule" ]; then
    echo "⏰ Запуск по расписанию (09:00 МСК ежедневно)..."
    python main.py --schedule
else
    echo "▶ Запуск парсера..."
    python main.py "$@"
fi

deactivate
