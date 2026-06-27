"""
Ответы в тему топика (не в общий чат).
"""

import logging
import aiohttp
from .config import BOT_TOKEN, TOPIC_ID, CHAT_ID

logger = logging.getLogger(__name__)


async def reply_to_topic(text: str) -> dict:
    """Отправляем сообщение в тему топика через Bot API."""
    if not BOT_TOKEN or TOPIC_ID == 0:
        logger.warning("⚠️ Нет BOT_TOKEN или TOPIC_ID — ответ не отправлен")
        return {}

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "message_thread_id": TOPIC_ID,
        "text": text,
        "parse_mode": "Markdown",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            result = await resp.json()
            if result.get("ok"):
                logger.info(f"✅ Ответ отправлен в топик #{TOPIC_ID}")
            else:
                logger.error(f"❌ Ошибка: {result}")
            return result


async def send_progress(status: str) -> dict:
    """Отправляем статус в топик."""
    return await reply_to_topic(f"⚙️ {status}")


async def send_error(message: str) -> dict:
    """Отправляем ошибку в топик."""
    return await reply_to_topic(f"❌ {message}")
