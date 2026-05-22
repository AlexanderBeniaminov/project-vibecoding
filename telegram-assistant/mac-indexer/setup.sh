#!/bin/bash
# setup.sh — Установка индексатора файлов на Mac
# Запускать один раз: bash telegram-assistant/mac-indexer/setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INDEX_DIR="$HOME/file-indexer"
PLIST_SRC="$SCRIPT_DIR/com.alexander.file-indexer.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.alexander.file-indexer.plist"

echo "=== Установка File Indexer ==="

# 1. Создаём рабочую папку
mkdir -p "$INDEX_DIR"
echo "✓ Создана папка: $INDEX_DIR"

# 2. Копируем скрипт индексатора
cp "$SCRIPT_DIR/indexer.py" "$INDEX_DIR/indexer.py"
chmod +x "$INDEX_DIR/indexer.py"
echo "✓ Скрипт скопирован: $INDEX_DIR/indexer.py"

# 3. Устанавливаем зависимости
echo "Устанавливаю зависимости Python..."
pip3 install --quiet python-pptx python-docx pdfplumber openpyxl 2>&1 | tail -5
echo "✓ Зависимости установлены"

# 4. Устанавливаем LaunchAgent
mkdir -p "$HOME/Library/LaunchAgents"

# Выгружаем если уже был загружен
if launchctl list | grep -q "com.alexander.file-indexer"; then
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    echo "✓ Старый LaunchAgent выгружен"
fi

cp "$PLIST_SRC" "$PLIST_DST"
launchctl load "$PLIST_DST"
echo "✓ LaunchAgent установлен и запущен"

echo ""
echo "=== Готово ==="
echo "Индексация запустится сейчас и далее каждые 2 часа."
echo "Индекс: $INDEX_DIR/file_index.json"
echo "Логи:   $INDEX_DIR/indexer.log"
echo ""
echo "Проверить статус: launchctl list | grep file-indexer"
echo "Запустить вручную: python3 $INDEX_DIR/indexer.py"
