TELEGRAM_TOKEN    = "YOUR_TELEGRAM_BOT_TOKEN"          # Новый токен от @BotFather
ALLOWED_USER_IDS: set[int] = {994743403}                # Только Александр

CHANNEL_ID        = "@your_channel"                     # «ИИндустрия Развлечений» — боевой канал
TEST_CHANNEL_ID   = "@your_test_channel"                # Закрытый тестовый канал (только Александр)

ROUTERAI_BASE_URL = "https://routerai.ru/api/v1"
ROUTERAI_API_KEY  = "YOUR_ROUTERAI_API_KEY"
MODEL             = "deepseek/deepseek-v4-pro"

GROQ_API_KEY      = "YOUR_GROQ_API_KEY"

DB_PATH           = "/home/parser/bots/content-bot/data/content.db"
KNOWLEDGE_DIR     = "/home/parser/bots/content-bot/knowledge"

SERVICE_ACCOUNT_JSON  = "/home/parser/config/personal/service_account.json"
SPREADSHEET_ID        = "YOUR_GOOGLE_SPREADSHEET_ID"

IDEA_COOLDOWN_DAYS    = 30
LIFEHACK_START_DATE   = "2026-06-19"   # Опорная дата первого лайфхак-четверга
PUBLISH_DAYS          = [0, 3]          # 0=пн, 3=чт
PUBLISH_HOUR          = 10              # 10:00 МСК
SHEETS_SYNC_HOUR      = 3               # Синхронизация Sheets→Бот в 03:00 МСК
