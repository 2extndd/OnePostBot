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


def _safe_caption(text: str, max_len: int = 1024) -> str:
    """Обрезает текст до max_len, закрывая открытые HTML-теги."""
    if len(text) <= max_len:
        return text
    text = text[:max_len]
    # Закрываем открытые теги
    for tag in ("<b>", "<strong>", "<i>", "<em>", "<a", "<a>", "<blockquote>", "<pre>", "<code>"):
        if text.count(tag) % 2 != 0:
            text += f"</{tag.lstrip('<>')}>"
    return text


async def post_via_bot(text: str, photo_path: str = None, chat_id: str = None, topic_id: int = None):
    """Публикация через бота (Telegram Bot API)."""
    import aiohttp

    chat = chat_id or TARGET_CHANNEL
    if not chat:
        raise ValueError("TARGET_CHANNEL или chat_id не задан — некуда публиковать")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}"

    # Подготовим общие параметры
    base_params = {"chat_id": str(chat), "text": text, "parse_mode": "HTML"}
    if topic_id:
        base_params["message_thread_id"] = topic_id

    if photo_path and os.path.exists(photo_path):
        async with aiohttp.ClientSession() as session:
            with open(photo_path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("chat_id", str(chat))
                form.add_field("caption", _safe_caption(text))
                form.add_field("parse_mode", "HTML")
                if topic_id:
                    form.add_field("message_thread_id", str(topic_id))
                form.add_field("photo", f, filename=os.path.basename(photo_path))
                async with session.post(f"{url}/sendPhoto", data=form) as resp:
                    result = await resp.json()
    else:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{url}/sendMessage", json=base_params) as resp:
                result = await resp.json()

    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result.get('description', result)}")
    logger.info(f"📤 Пост отправлен через бота: chat={chat}, topic={topic_id}, msg_id={result['result'].get('message_id')}")
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
    Публикуем пост (НЕ добавляет задержку — она в publish_worker).
    """
    if mode == "auto":
        mode = "bot" if BOT_TOKEN else "telethon"

    try:
        if mode == "bot":
            return await post_via_bot(text, photo_path)
        else:
            return await post_via_telethon(text, photo_path)
    except Exception as e:
        logger.error(f"❌ Ошибка публикации: {e}")
        raise
