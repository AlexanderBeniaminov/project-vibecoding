"""
vk_max_bot.py — Бот для VK MAX (max.ru)
Запуск: python vk_max_bot.py alex
        python vk_max_bot.py oleg

Команды:
  /status  — состояние VPN, место на диске, uptime
  /report  — последний отчёт из Google Sheets
  /ping    — проверка связи
  /help    — список команд
"""

import sys
import subprocess
import shutil
import time
import requests
from datetime import datetime

sys.path.insert(0, "/home/parser")
from parsers.account_manager import AccountManager, get_account_from_args, VKMAX_API


class VKMaxBot:
    def __init__(self, am: AccountManager):
        self.am      = am
        self.cfg     = am.cfg
        self.log     = am.log
        self.token   = self.cfg.VK_MAX_TOKEN
        self.user_id = self.cfg.VK_MAX_USER_ID
        self.marker  = None

    def _headers(self):
        return {"Authorization": self.token, "Content-Type": "application/json"}

    def send(self, text: str, user_id: int = None):
        uid = user_id or self.user_id
        try:
            resp = requests.post(
                f"{VKMAX_API}/messages",
                params={"user_id": uid},
                headers=self._headers(),
                json={"text": text},
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            self.log.error(f"[{self.am.account}] VK MAX send error: {e}")

    def get_updates(self):
        params = {"timeout": 20}
        if self.marker:
            params["marker"] = self.marker
        try:
            resp = requests.get(
                f"{VKMAX_API}/updates",
                params=params,
                headers=self._headers(),
                timeout=30,
            )
            data = resp.json()
            self.marker = data.get("marker", self.marker)
            return data.get("updates", [])
        except Exception as e:
            self.log.error(f"[{self.am.account}] VK MAX poll error: {e}")
            return []

    def get_server_status(self) -> str:
        lines = [f"Статус сервера [{self.cfg.ACCOUNT_NAME}]"]
        lines.append(f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

        try:
            r = subprocess.run(["uptime", "-p"], capture_output=True, text=True)
            lines.append(f"Uptime: {r.stdout.strip()}")
        except Exception:
            pass

        try:
            r = subprocess.run(["systemctl", "is-active", "wg-quick@wg0"],
                               capture_output=True, text=True)
            wg = "✅ активен" if r.stdout.strip() == "active" else "❌ УПАЛ"
            lines.append(f"WireGuard: {wg}")
        except Exception:
            pass

        try:
            total, used, free = shutil.disk_usage("/")
            pct = used / total * 100
            lines.append(f"Диск: {used // (1024**3)}GB / {total // (1024**3)}GB ({pct:.0f}%)")
        except Exception:
            pass

        try:
            r = subprocess.run(["free", "-m"], capture_output=True, text=True)
            row = r.stdout.split("\n")[1].split()
            lines.append(f"RAM: {row[2]}MB / {row[1]}MB")
        except Exception:
            pass

        return "\n".join(lines)

    def get_last_report(self) -> str:
        try:
            sheet = self.am.get_sheet("reports", worksheet_index=0)
            records = sheet.get_all_values()
            if not records:
                return "Таблица пуста"
            last_rows = records[-5:] if len(records) > 1 else records
            lines = [f"Последний отчёт [{self.cfg.ACCOUNT_NAME}]"]
            for row in last_rows:
                lines.append("  ".join(str(c)[:20] for c in row[:5]))
            return "\n".join(lines)
        except Exception as e:
            return f"Ошибка получения отчёта: {e}"

    def handle(self, sender_id: int, text: str):
        cmd = text.strip().lower()
        self.log.info(f"[{self.am.account}] VK MAX команда от {sender_id}: {cmd!r}")

        if cmd in ("/ping", "ping"):
            self.send(f"✅ Бот [{self.cfg.ACCOUNT_NAME}] отвечает! {datetime.now().strftime('%H:%M:%S')}", sender_id)
        elif cmd in ("/status", "статус"):
            self.send(self.get_server_status(), sender_id)
        elif cmd in ("/report", "отчёт", "отчет"):
            self.send(self.get_last_report(), sender_id)
        elif cmd in ("/help", "помощь"):
            self.send(
                "Команды бота:\n"
                "/status — состояние сервера и VPN\n"
                "/report — последние данные из таблицы\n"
                "/ping   — проверка связи",
                sender_id,
            )
        else:
            self.send(f"Неизвестная команда: {text}\nНапиши /help для списка команд", sender_id)

    def run(self):
        self.log.info(f"[{self.am.account}] VK MAX бот запущен")
        print(f"[{self.am.account}] VK MAX бот запущен. Нажми Ctrl+C для остановки")

        while True:
            try:
                updates = self.get_updates()
                for upd in updates:
                    if upd.get("update_type") != "message_created":
                        continue
                    msg = upd.get("message", {})
                    sender = msg.get("sender", {})
                    if sender.get("is_bot"):
                        continue
                    sender_id = sender.get("user_id")
                    text = msg.get("body", {}).get("text", "")
                    if sender_id and text:
                        self.handle(sender_id, text)
            except KeyboardInterrupt:
                self.log.info(f"[{self.am.account}] VK MAX бот остановлен")
                break
            except Exception as e:
                self.log.error(f"[{self.am.account}] Ошибка: {e}")
                time.sleep(5)


if __name__ == "__main__":
    account = get_account_from_args()
    am = AccountManager(account)
    bot = VKMaxBot(am)
    bot.run()
