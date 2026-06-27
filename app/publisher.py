"""
Публикация постов в целевой канал.
Поддержка двух режимов:
1. Через бота (BOT_TOKEN)
2. Через пользователя (Telethon)
"""

import asyncio
import random
import logging
import os
from datetime import datetime, timedelta

from telethon import TelegramClient

from .config import (
    BOT_TOKEN,
    TARGET_CHANNEL,
    POST_DELAY_MIN,
    POST_DELAY_MAX,
)

logger = logging.getLogger(__name__)


async def post_via_bot(text: str, photo_path: str = None, chat_id: str = None):
    """Публикация через бота (Telegram Bot API)."""
    import aiohttp

    chat = chat_id or TARGET_CHANNEL
    url = f"https://api.telegram.org/bot{BOT_TOKEN}"

    if photo_path:
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": chat, "caption": text}
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{url}/sendPhoto", data=data, files=files) as resp:
                    result = await resp.json()
                    logger.info(f"📤 Пост отправлен через бота: {result}")
                    return result
    else:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{url}/sendMessage", json={"chat_id": chat, "text": text}) as resp:
                result = await resp.json()
                logger.info(f"📤 Пост отправлен через бота: {result}")
                return result


async def post_via_telethon(text: str, photo_path: str = None):
    """Публикация через Telethon (пользовательский аккаунт)."""
    from .config import TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSION_FILE

    client = TelegramClient(str(SESSION_FILE), TELEGRAM_API_ID, TELEGRAM_API_HASH)
    await client.start()

    entity = await client.get_entity(TARGET_CHANNEL)

    if photo_path:
        await client.send_message(entity, text, file=photo_path)
    else:
        await client.send_message(entity, text)

    await client.disconnect()
    logger.info(f"📤 Пост опубликован через Telethon")


async def publish_post(text: str, photo_path: str = None, mode: str = "auto"):
    """
    Публикуем пост.
    mode: 'bot' | 'telethon' | 'auto'
    """
    if mode == "auto":
        mode = "bot" if BOT_TOKEN else "telethon"

    delay = random.randint(POST_DELAY_MIN, POST_DELAY_MAX)
    logger.info(f"⏳ Публикация через {delay} мин...")
    await asyncio.sleep(delay * 60)

    try:
        if mode == "bot":
            return await post_via_bot(text, photo_path)
        else:
            return await post_via_telethon(text, photo_path)
    except Exception as e:
        logger.error(f"❌ Ошибка публикации: {e}")
        raise
