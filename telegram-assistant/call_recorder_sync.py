#!/usr/bin/env python3
"""
Наблюдатель за записями Cube ACR — отправляет новые файлы в Telegram-бот.
Запускается на Mac по cron каждые 2 минуты.

Устройство: Huawei Nova 11 по ADB WiFi (192.168.1.144:5555)
Папка записей: /storage/emulated/0/Documents/CubeCallRecorder/All/
"""

import subprocess
import os
import sys
import json
import requests
import time
from pathlib import Path
from datetime import datetime

PHONE_HOST = "192.168.1.144:5555"
ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
CUBE_FOLDER = "/storage/emulated/0/Documents/CubeCallRecorder/All"

BOT_TOKEN = "7778266500:AAFT-5f7eJOMIBIR5o8j3RHBkhzIGNxS0F8"
CHAT_ID = 994743403

# Локальные пути
SCRIPT_DIR = Path(__file__).parent
SEEN_FILE = SCRIPT_DIR / "data" / "cube_acr_seen.json"
TEMP_DIR = Path("/tmp/cube_acr_sync")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def adb(*args, timeout=30) -> tuple[int, str, str]:
    cmd = [ADB, "-s", PHONE_HOST] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def connect_phone() -> bool:
    code, out, err = adb("shell", "echo", "ok")
    if code == 0:
        return True
    # Попробуем переподключиться
    subprocess.run([ADB, "connect", PHONE_HOST], capture_output=True, timeout=10)
    time.sleep(2)
    code, out, _ = adb("shell", "echo", "ok")
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
    code, out, _ = adb("shell", "ls", "-1", CUBE_FOLDER)
    if code != 0 or not out:
        return []
    return [f.strip() for f in out.splitlines() if f.strip().endswith((".amr", ".m4a", ".mp4", ".wav", ".ogg"))]


def pull_and_send(filename: str) -> bool:
    local_path = TEMP_DIR / filename
    # Скачиваем файл
    remote_path = f"{CUBE_FOLDER}/{filename}"
    code, _, err = adb("pull", remote_path, str(local_path), timeout=60)
    if code != 0:
        log(f"Ошибка pull {filename}: {err}")
        return False
    if not local_path.exists() or local_path.stat().st_size == 0:
        log(f"Файл пустой: {filename}")
        return False

    # Извлекаем номер из имени файла: phone_YYYYMMDD-HHMMSS__PHONENUMBER.amr
    parts = filename.replace(".amr", "").replace(".m4a", "").split("__")
    phone_number = parts[1] if len(parts) > 1 else "неизвестный номер"
    caption = f"📞 Запись звонка\nНомер: {phone_number}\nФайл: {filename}"

    # Отправляем в Telegram
    with open(local_path, "rb") as f:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendAudio",
            data={"chat_id": CHAT_ID, "caption": caption},
            files={"audio": (filename, f, "audio/amr")},
            timeout=120,
        )

    if resp.status_code == 200:
        log(f"Отправлено: {filename}")
        local_path.unlink(missing_ok=True)
        return True
    else:
        log(f"Ошибка Telegram {resp.status_code}: {resp.text[:200]}")
        local_path.unlink(missing_ok=True)
        return False


def main():
    log("=== Запуск синхронизации записей звонков ===")

    if not connect_phone():
        log("Телефон недоступен по ADB WiFi — пропускаем")
        sys.exit(0)

    seen = load_seen()
    files = list_recordings()

    if not files:
        log("Новых записей нет или папка пуста")
        sys.exit(0)

    new_files = [f for f in files if f not in seen]
    if not new_files:
        log(f"Все {len(files)} файлов уже обработаны")
        sys.exit(0)

    log(f"Новых файлов: {len(new_files)}")
    for filename in new_files:
        if pull_and_send(filename):
            seen.add(filename)
            save_seen(seen)
        time.sleep(1)

    log("=== Синхронизация завершена ===")


if __name__ == "__main__":
    main()
