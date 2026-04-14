"""
Центральный конфиг: читает .env и предоставляет константы всему проекту.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем .env из папки проекта
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# ─── Макс (ICQ New) Bot — уведомления ────────────────────────────────────────
# Бот создаётся через @metabot в приложении Макс
ICQ_BOT_TOKEN: str = os.getenv("ICQ_BOT_TOKEN", "")
ICQ_CHAT_ID: str = os.getenv("ICQ_CHAT_ID", "")
ICQ_API_BASE: str = "https://botapi.max.ru"

# ─── Telegram MTProto (парсинг ТГ-каналов через Telethon) — опционально ──────
# Нужно только если хочешь парсить Telegram-каналы как источник объявлений.
# Регистрация: https://my.telegram.org/apps
TELEGRAM_API_ID: str = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION_FILE: Path = BASE_DIR / "tg_session"  # файл сессии Telethon

# ─── Google Sheets ────────────────────────────────────────────────────────────
GOOGLE_CREDENTIALS_FILE: Path = BASE_DIR / os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_SPREADSHEET_ID: str = os.getenv("GOOGLE_SPREADSHEET_ID", "")
SHEET_ALL_LISTINGS = "Все объявления"
SHEET_HISTORY = "История изменений"

# ─── База данных ──────────────────────────────────────────────────────────────
DB_PATH: Path = BASE_DIR / "listings.db"

# ─── Задержки антибан (секунды) ───────────────────────────────────────────────
REQUEST_DELAY_MIN: float = 4.0
REQUEST_DELAY_MAX: float = 12.0
SITE_DELAY_MIN: float = 15.0
SITE_DELAY_MAX: float = 45.0
RETRY_PAUSE: int = 300       # пауза после 403/429 (5 минут)
MAX_RETRIES: int = 3

# ─── Планировщик ─────────────────────────────────────────────────────────────
RUN_HOUR: int = int(os.getenv("RUN_HOUR", "9"))
RUN_MINUTE: int = int(os.getenv("RUN_MINUTE", "0"))
RUN_TIMEZONE: str = "Europe/Moscow"

# ─── Пути к конфиг-файлам ────────────────────────────────────────────────────
KEYWORDS_CONFIG_FILE: Path = BASE_DIR / "keywords_config.json"
TELEGRAM_SOURCES_FILE: Path = BASE_DIR / "telegram_sources.json"
LOG_FILE: Path = BASE_DIR / "parser.log"

# ─── Проверка обязательных переменных ────────────────────────────────────────
def check_config() -> list[str]:
    """Возвращает список незаполненных обязательных переменных."""
    missing = []
    if not ICQ_BOT_TOKEN:
        missing.append("ICQ_BOT_TOKEN (токен бота Макс — получи у @metabot)")
    if not ICQ_CHAT_ID:
        missing.append("ICQ_CHAT_ID (твой номер телефона или ID чата в Макс)")
    if not GOOGLE_SPREADSHEET_ID:
        missing.append("GOOGLE_SPREADSHEET_ID")
    if not GOOGLE_CREDENTIALS_FILE.exists():
        missing.append(f"credentials.json (файл не найден: {GOOGLE_CREDENTIALS_FILE})")
    return missing
