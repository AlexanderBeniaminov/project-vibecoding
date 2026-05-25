#!/bin/bash
# setup.sh — Установка и настройка OpenClaw на Mac
# Запускать один раз

set -e

echo "=== OpenClaw Setup ==="

# 1. Установка OpenClaw
echo ""
echo "1. Устанавливаем OpenClaw..."
if command -v openclaw &>/dev/null; then
    echo "   OpenClaw уже установлен: $(openclaw --version 2>/dev/null || echo 'версия неизвестна')"
else
    npm install -g @openclaw/openclaw
    echo "   ✅ OpenClaw установлен"
fi

# 2. Создание папки конфига
echo ""
echo "2. Создаём папку ~/.openclaw/..."
mkdir -p ~/.openclaw/knowledge
echo "   ✅ Папка создана"

# 3. Копируем конфиг
echo ""
echo "3. Копируем openclaw.json..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/openclaw.json" ~/.openclaw/openclaw.json
cp "$SCRIPT_DIR/knowledge/user.md" ~/.openclaw/knowledge/user.md
echo "   ✅ Конфиг и база знаний скопированы"

# 4. Переменные окружения
echo ""
echo "4. Добавляем переменные окружения в ~/.zshrc..."

if grep -q "ROUTERAI_API_KEY" ~/.zshrc 2>/dev/null; then
    echo "   ROUTERAI_API_KEY уже в ~/.zshrc — пропускаем"
else
    echo "" >> ~/.zshrc
    echo "# OpenClaw — RouterAI API" >> ~/.zshrc
    echo "export ROUTERAI_API_KEY=\"\"  # ← вставить ключ из telegram-assistant/config.py" >> ~/.zshrc
    echo "export OPENCLAW_TG_TOKEN=\"\" # ← вставить токен нового бота от @BotFather" >> ~/.zshrc
    echo "   ✅ Строки добавлены в ~/.zshrc (заполни значения!)"
fi

# 5. Выключить mac-indexer (если установлен)
echo ""
echo "5. Отключаем mac-indexer LaunchAgent (если был)..."
PLIST="$HOME/Library/LaunchAgents/com.parser.mac-indexer.plist"
if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" 2>/dev/null && echo "   ✅ mac-indexer выгружен" || echo "   ⚠️ Не удалось выгрузить (возможно уже не запущен)"
else
    echo "   mac-indexer не найден — пропускаем"
fi

# Итог
echo ""
echo "=== Что нужно сделать вручную ==="
echo ""
echo "  1. Открой ~/.zshrc и вставь значения переменных:"
echo "     ROUTERAI_API_KEY  — скопировать из telegram-assistant/config.py"
echo "     OPENCLAW_TG_TOKEN — создать нового бота через @BotFather в Telegram"
echo ""
echo "  2. source ~/.zshrc   (применить переменные в текущей сессии)"
echo ""
echo "  3. Скачать и установить macOS Companion App:"
echo "     https://openclaw.ai  → Download → macOS (15+, Universal Binary)"
echo ""
echo "  4. openclaw start    (запустить агента)"
echo ""
echo "  5. Проверить: написать новому Telegram-боту 'найди файл README'"
echo "     → должен найти файл на Mac"
echo ""
echo "✅ Setup готов!"
