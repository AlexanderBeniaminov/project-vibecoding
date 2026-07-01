#!/usr/bin/env python3
"""
Наблюдатель за записями Cube ACR.
Каждые 2 минуты (cron) проверяет новые записи на телефоне,
загружает их на сервер и запускает обработку.

Телефон: Huawei Nova 11, ADB WiFi 192.168.1.144:5555
Папка записей: /storage/emulated/0/Documents/CubeCallRecorder/All/
"""

import subprocess
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

PHONE_HOST = "192.168.1.16:5555"
ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
CUBE_FOLDER = "/storage/emulated/0/Documents/CubeCallRecorder/All"

SERVER_ALIAS = "server"
SERVER_INBOX = "/tmp/call_recordings"
SERVER_PROCESS_SCRIPT = "/home/parser/bots/assistant/process_call_audio.py"
SERVER_VENV_PYTHON = "/home/parser/venv/bin/python3"

SCRIPT_DIR = Path(__file__).parent
SEEN_FILE = SCRIPT_DIR / "data" / "cube_acr_seen.json"
TEMP_DIR = Path("/tmp/cube_acr_sync")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run(cmd: list, timeout=30) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def connect_phone() -> bool:
    code, out, _ = run([ADB, "-s", PHONE_HOST, "shell", "echo", "ok"])
    if code == 0:
        return True
    run([ADB, "connect", PHONE_HOST])
    time.sleep(2)
    code, _, _ = run([ADB, "-s", PHONE_HOST, "shell", "echo", "ok"])
    return code == 0


def load_seen() -> set:
    if SEEN_FILE.exists():
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def list_recordings() -> list[str]:
    code, out, _ = run([ADB, "-s", PHONE_HOST, "shell", "ls", "-1", CUBE_FOLDER])
    if code != 0 or not out:
        return []
    return [
        f.strip() for f in out.splitlines()
        if f.strip().endswith((".amr", ".m4a", ".mp4", ".wav", ".ogg"))
    ]


def ensure_server_inbox():
    run(["ssh", SERVER_ALIAS, f"mkdir -p {SERVER_INBOX}"])


def process_file(filename: str) -> bool:
    local_path = TEMP_DIR / filename

    # 1. Скачиваем с телефона
    code, _, err = run(
        [ADB, "-s", PHONE_HOST, "pull", f"{CUBE_FOLDER}/{filename}", str(local_path)],
        timeout=120
    )
    if code != 0 or not local_path.exists() or local_path.stat().st_size == 0:
        log(f"Ошибка pull {filename}: {err}")
        return False

    size_kb = local_path.stat().st_size // 1024
    log(f"Скачан: {filename} ({size_kb} КБ)")

    # 2. Копируем на сервер
    remote_path = f"{SERVER_INBOX}/{filename}"
    code, _, err = run(
        ["scp", str(local_path), f"{SERVER_ALIAS}:{remote_path}"],
        timeout=120
    )
    if code != 0:
        log(f"Ошибка scp {filename}: {err}")
        local_path.unlink(missing_ok=True)
        return False

    # 3. Запускаем обработку на сервере (в фоне)
    code, _, err = run(
        ["ssh", SERVER_ALIAS,
         f"nohup {SERVER_VENV_PYTHON} {SERVER_PROCESS_SCRIPT} {remote_path} "
         f"> /tmp/call_recordings/process_{filename}.log 2>&1 &"],
        timeout=15
    )

    local_path.unlink(missing_ok=True)
    if code != 0:
        log(f"Ошибка запуска обработки {filename}: {err}")
        return False

    log(f"Обработка запущена: {filename}")
    return True


def main():
    log("=== Синхронизация записей Cube ACR ===")

    if not connect_phone():
        log("Телефон недоступен по ADB WiFi — пропускаем")
        sys.exit(0)

    seen = load_seen()
    files = list_recordings()

    if not files:
        log("Записей нет или папка пуста")
        sys.exit(0)

    new_files = [f for f in files if f not in seen]
    if not new_files:
        log(f"Всё уже обработано ({len(files)} файлов)")
        sys.exit(0)

    log(f"Новых файлов: {len(new_files)}")
    ensure_server_inbox()

    for filename in new_files:
        # Пропускаем слишком маленькие файлы (обрыв соединения < 5KB)
        code, out, _ = run([ADB, "-s", PHONE_HOST, "shell", "stat", "-c%s",
                            f"{CUBE_FOLDER}/{filename}"])
        try:
            size = int(out)
        except ValueError:
            size = 0
        if size < 5000:
            log(f"Пропуск {filename} — слишком маленький ({size} байт)")
            seen.add(filename)
            save_seen(seen)
            continue

        if process_file(filename):
            seen.add(filename)
            save_seen(seen)
        time.sleep(2)

    log("=== Готово ===")


if __name__ == "__main__":
    main()
