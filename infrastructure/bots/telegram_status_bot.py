"""
telegram_status_bot.py — Telegram бот для мониторинга и команд
Запуск: python telegram_status_bot.py alex
        python telegram_status_bot.py oleg

Команды:
  /status  — состояние VPN, парсеров, диска, uptime
  /report  — последний отчёт из Google Sheets
  /ping    — проверка связи
  /wg      — подробный статус WireGuard
  /logs    — последние строки логов
"""

import sys
import subprocess
import shutil
import glob
import os
import asyncio
from datetime import datetime
import telegram
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters
)

sys.path.insert(0, "/home/parser")
from parsers.account_manager import AccountManager, get_account_from_args


class TelegramStatusBot:
    def __init__(self, am: AccountManager):
        self.am  = am
        self.cfg = am.cfg
        self.log = am.log

    def _server_status(self) -> str:
        lines = [f"📊 <b>Статус сервера [{self.cfg.ACCOUNT_NAME}]</b>"]
        lines.append(f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

        # Uptime
        try:
            r = subprocess.run(["uptime", "-p"], capture_output=True, text=True)
            lines.append(f"⏱ Uptime: {r.stdout.strip()}")
        except Exception:
            pass

        # WireGuard
        try:
            r = subprocess.run(["systemctl", "is-active", "wg-quick@wg0"],
                               capture_output=True, text=True)
            wg = "✅ активен" if r.stdout.strip() == "active" else "❌ УПАЛ"
            lines.append(f"🔒 WireGuard: {wg}")
        except Exception:
            pass

        # Клиенты WireGuard
        try:
            r = subprocess.run(["wg", "show", "wg0"], capture_output=True, text=True)
            peers = r.stdout.count("peer:")
            lines.append(f"👥 Клиентов VPN: {peers}")
        except Exception:
            pass

        # Диск
        try:
            total, used, free = shutil.disk_usage("/")
            pct = used / total * 100
            bar = "█" * int(pct // 10) + "░" * (10 - int(pct // 10))
            lines.append(f"💾 Диск: {bar} {pct:.0f}% ({free // (1024**3):.1f}GB свободно)")
        except Exception:
            pass

        # Память
        try:
            r = subprocess.run(["free", "-m"], capture_output=True, text=True)
            row = r.stdout.split("\n")[1].split()
            total_mb, used_mb = int(row[1]), int(row[2])
            lines.append(f"🧠 RAM: {used_mb}MB / {total_mb}MB ({used_mb/total_mb*100:.0f}%)")
        except Exception:
            pass

        # Последние логи
        log_dir = "/home/parser/logs"
        try:
            logs = sorted(glob.glob(f"{log_dir}/*{self.am.account}*.log"), reverse=True)[:3]
            if logs:
                lines.append("\n📄 <b>Последние запуски:</b>")
                for lg in logs:
                    name = os.path.basename(lg).replace(".log", "")
                    mtime = datetime.fromtimestamp(os.path.getmtime(lg)).strftime("%d.%m %H:%M")
                    size = os.path.getsize(lg)
                    ok = "✅" if size > 100 else "⚠️"
                    lines.append(f"  {ok} {name} ({mtime})")
        except Exception:
            pass

        return "\n".join(lines)

    def _wg_status(self) -> str:
        try:
            r = subprocess.run(["wg", "show"], capture_output=True, text=True)
            return f"<pre>{r.stdout[:3000]}</pre>" if r.stdout else "WireGuard не запущен"
        except Exception as e:
            return f"Ошибка: {e}"

    def _last_report(self) -> str:
        try:
            sheet = self.am.get_sheet("reports", worksheet_index=0)
            records = sheet.get_all_values()
            if not records:
                return "Таблица пуста"
            headers = records[0]
            last_rows = records[-5:] if len(records) > 1 else []
            lines = [f"📋 <b>Последний отчёт [{self.cfg.ACCOUNT_NAME}]</b>"]
            for row in last_rows:
                lines.append("  ".join(str(c)[:20] for c in row[:6]))
            return "\n".join(lines)
        except Exception as e:
            return f"Ошибка: {e}"

    def _last_logs(self) -> str:
        log_dir = "/home/parser/logs"
        try:
            logs = sorted(glob.glob(f"{log_dir}/*{self.am.account}*.log"), reverse=True)
            if not logs:
                return "Логов нет"
            last_log = logs[0]
            with open(last_log, "r") as f:
                lines = f.readlines()
            last_20 = "".join(lines[-20:])
            name = os.path.basename(last_log)
            return f"<b>Лог:</b> {name}\n<pre>{last_20[-2000:]}</pre>"
        except Exception as e:
            return f"Ошибка: {e}"

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"👋 Привет! Я бот аккаунта <b>{self.cfg.ACCOUNT_NAME}</b>\n\n"
            "Команды:\n"
            "/status — состояние сервера\n"
            "/report — последний отчёт\n"
            "/wg     — статус VPN\n"
            "/logs   — последние логи\n"
            "/ping   — проверка связи",
            parse_mode="HTML"
        )

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(self._server_status(), parse_mode="HTML")

    async def cmd_report(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(self._last_report(), parse_mode="HTML")

    async def cmd_wg(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(self._wg_status(), parse_mode="HTML")

    async def cmd_logs(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(self._last_logs(), parse_mode="HTML")

    async def cmd_ping(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"✅ Pong! [{self.cfg.ACCOUNT_NAME}] {datetime.now().strftime('%H:%M:%S')}"
        )

    async def unknown(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Неизвестная команда. Напиши /ping для проверки.")

    def run(self):
        self.log.info(f"[{self.am.account}] Telegram бот запущен")
        app = Application.builder().token(self.cfg.TELEGRAM_BOT_TOKEN).build()
        app.add_handler(CommandHandler("start",  self.cmd_start))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("report", self.cmd_report))
        app.add_handler(CommandHandler("wg",     self.cmd_wg))
        app.add_handler(CommandHandler("logs",   self.cmd_logs))
        app.add_handler(CommandHandler("ping",   self.cmd_ping))
        app.add_handler(MessageHandler(filters.COMMAND, self.unknown))
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    account = get_account_from_args()
    am = AccountManager(account)
    bot = TelegramStatusBot(am)
    bot.run()
