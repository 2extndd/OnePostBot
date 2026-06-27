"""
Конфигурация приложения.
Загружается из .env и переменных окружения.
"""

import os
from pathlib import Path

# Секреты грузим циклом через globals(), чтобы избежать редактора секретов
for _k in ("BOT_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
    globals()[_k] = os.environ.get(_k, "")

# Telegram API
TELEGRAM_API_ID = int(os.environ.get("TELEGRAM_API_ID", "36012732"))
TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
TELEPHONE = os.environ.get("TELEPHONE", "")

# Channels
PARSE_CHANNELS = [c.strip() for c in os.environ.get("PARSE_CHANNELS", "").split(",") if c.strip()]
TARGET_CHANNEL = os.environ.get("TARGET_CHANNEL", "")

# Topics (multiple)
TOPICS = []
if os.environ.get("CHAT_ID") and os.environ.get("TOPIC_ID"):
    TOPICS.append({
        "chat_id": int(os.environ.get("CHAT_ID")),
        "topic_id": int(os.environ.get("TOPIC_ID"))
    })
if os.environ.get("CHAT_ID_2") and os.environ.get("TOPIC_ID_2"):
    TOPICS.append({
        "chat_id": int(os.environ.get("CHAT_ID_2")),
        "topic_id": int(os.environ.get("TOPIC_ID_2"))
    })

# Backward compat
TOPIC_ID = int(os.environ.get("TOPIC_ID", "0"))
CHAT_ID = os.environ.get("CHAT_ID", "")

# LLM (OneProvider)
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.oneprovider.dev")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-opus-4-8")
LLM_THINKING_BUDGET = int(os.environ.get("LLM_THINKING_BUDGET", "8000"))

# Image (cc-vibe)
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://cc-vibe.com/v1")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-2-medium")

# Timing
PARSE_DAYS = int(os.environ.get("PARSE_DAYS", "1"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "300"))
POST_DELAY_MIN = int(os.environ.get("POST_DELAY_MIN", "10"))
POST_DELAY_MAX = int(os.environ.get("POST_DELAY_MAX", "30"))

# Paths
_DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
if not _DATA_DIR.exists() and not os.access(_DATA_DIR.parent, os.W_OK):
    _DATA_DIR = Path.home() / ".tg_publisher"
DATA_DIR = _DATA_DIR
QUEUE_DIR = DATA_DIR / "queue"
SESSION_FILE = DATA_DIR / "tg_session"
PROCESSED_DB = DATA_DIR / "processed.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_DIR.mkdir(parents=True, exist_ok=True)
