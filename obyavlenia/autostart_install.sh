#!/bin/bash
# Устанавливает автозапуск парсера через macOS LaunchAgent.
# Запусти один раз: bash autostart_install.sh

PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/com.parser.obyavlenia.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.parser.obyavlenia.plist"

echo "Копирую plist в LaunchAgents..."
cp "$PLIST_SRC" "$PLIST_DST"

echo "Регистрирую агент (launchctl)..."
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load -w "$PLIST_DST"

echo ""
echo "✅ Готово! Парсер будет запускаться автоматически при входе в macOS."
echo "   Расписание: каждый день в 09:00 МСК (задаётся внутри APScheduler)."
echo ""
echo "Проверить статус:  launchctl list | grep parser"
echo "Остановить:        launchctl unload ~/Library/LaunchAgents/com.parser.obyavlenia.plist"
echo "Включить обратно:  launchctl load -w ~/Library/LaunchAgents/com.parser.obyavlenia.plist"
