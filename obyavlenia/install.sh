#!/bin/bash
# Установка парсера объявлений (Mac / Linux)
# Запуск: bash install.sh

set -e

echo ""
echo "=================================================="
echo "  Установка парсера объявлений о продаже бизнеса"
echo "=================================================="
echo ""

# Проверяем Python
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 не найден!"
    echo "   Mac:   brew install python3"
    echo "   Linux: sudo apt install python3 python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Python $PYTHON_VERSION найден"

# Создаём виртуальное окружение
if [ ! -d "venv" ]; then
    echo "📦 Создаём виртуальное окружение venv..."
    python3 -m venv venv
fi

# Активируем и устанавливаем зависимости
source venv/bin/activate

echo "📥 Устанавливаем зависимости из requirements.txt..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# Устанавливаем Playwright браузер
echo "🌐 Устанавливаем Playwright (Chromium)..."
playwright install chromium

# Создаём .env если нет
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "📝 Создан файл .env — нужно заполнить своими данными!"
    echo "   Открой .env в текстовом редакторе и заполни:"
    echo "   - TELEGRAM_BOT_TOKEN"
    echo "   - TELEGRAM_CHAT_ID"
    echo "   - GOOGLE_SPREADSHEET_ID"
fi

deactivate

echo ""
echo "=================================================="
echo "✅ Установка завершена!"
echo ""
echo "Следующие шаги:"
echo "  1. Заполни файл .env (открой в любом редакторе)"
echo "  2. Положи credentials.json рядом с main.py"
echo "  3. Запусти парсер: bash run.sh"
echo "  4. Для запуска по расписанию: bash run.sh --schedule"
echo "=================================================="
echo ""
