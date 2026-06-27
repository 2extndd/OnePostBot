"""
Парсер Telegram-каналов через Telethon.
Читает последние сообщения из указанных каналов.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict

from telethon import TelegramClient
from telethon.tl.types import (
    Message,
    MessageMediaPhoto,
    MessageMediaDocument,
)

from .config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    SESSION_FILE,
    PARSE_CHANNELS,
    PARSE_DAYS,
    PROCESSED_DB,
)

logger = logging.getLogger(__name__)


class TGParser:
    def __init__(self, phone: str = ""):
        self.phone = phone
        self.client = TelegramClient(
            str(SESSION_FILE),
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH,
        )

    async def start(self):
        """Подключаемся к Telegram."""
        await self.client.start(phone=self.phone or None)
        logger.info("✅ Подключено к Telegram")

    async def close(self):
        await self.client.disconnect()

    async def fetch_messages(
        self,
        channels: List[str] = None,
        since_days: int = None,
    ) -> List[Dict]:
        """
        Собираем сообщения из каналов.
        Возвращаем список словарей:
        {
            "channel": "@channel",
            "msg_id": 123,
            "text": "...",
            "photo_url": "..." | None,
            "date": ...,
        }
        """
        channels = channels or PARSE_CHANNELS
        since = datetime.now() - timedelta(days=since_days or PARSE_DAYS)
        all_messages = []

        async with self.client:
            for ch in channels:
                try:
                    entity = await self.client.get_entity(ch)
                    logger.info(f"📡 Читаем канал: {ch}")

                    async for msg in self.client.iter_messages(
                        entity,
                        limit=100,
                        date_gte=since,
                    ):
                        if not isinstance(msg, Message):
                            continue
                        if msg.date < since:
                            continue
                        if msg.media:
                            continue  # текстовые посты

                        all_messages.append({
                            "channel": getattr(entity, "title", ch),
                            "channel_username": getattr(entity, "username", ch),
                            "msg_id": msg.id,
                            "text": msg.text or "",
                            "photo_url": None,
                            "date": msg.date.isoformat(),
                        })
                except Exception as e:
                    logger.error(f"❌ Ошибка при чтении {ch}: {e}")

        # Сортируем по дате
        all_messages.sort(key=lambda m: m["date"])
        logger.info(f"📊 Найдено {len(all_messages)} сообщений")
        return all_messages

    async def fetch_with_photos(
        self,
        channels: List[str] = None,
        since_days: int = None,
    ) -> List[Dict]:
        """
        Альтернативная версия: берём посты с фото.
        Скачиваем фото во временный файл и возвращаем путь.
        """
        channels = channels or PARSE_CHANNELS
        since = datetime.now() - timedelta(days=since_days or PARSE_DAYS)
        all_posts = []

        async with self.client:
            for ch in channels:
                try:
                    entity = await self.client.get_entity(ch)
                    logger.info(f"📸 Читаем канал с медиа: {ch}")

                    async for msg in self.client.iter_messages(
                        entity,
                        limit=100,
                        date_gte=since,
                    ):
                        if not isinstance(msg, Message):
                            continue
                        if msg.date < since:
                            continue

                        photo_url = None
                        if msg.media and isinstance(msg.media, MessageMediaPhoto):
                            photo = await msg.download_media()
                            photo_url = str(photo)
                        elif msg.media and isinstance(msg.media, MessageMediaDocument):
                            # Фото в документе
                            ext = ".jpg"
                            photo = await msg.download_media(file=photo_url or f"/tmp/photo_{msg.id}{ext}")
                            photo_url = str(photo)

                        all_posts.append({
                            "channel": getattr(entity, "title", ch),
                            "channel_username": getattr(entity, "username", ch),
                            "msg_id": msg.id,
                            "text": msg.text or "",
                            "photo_url": photo_url,
                            "date": msg.date.isoformat(),
                        })
                except Exception as e:
                    logger.error(f"❌ Ошибка при чтении {ch}: {e}")

        all_posts.sort(key=lambda m: m["date"])
        logger.info(f"📊 Найдено {len(all_posts)} постов с медиа")
        return all_posts
