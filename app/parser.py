"""
Парсер Telegram-каналов через Telethon.
Читает последние сообщения из указанных каналов, скачивает фото.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

from telethon import TelegramClient
from telethon.tl.types import Message, MessageMediaPhoto, MessageMediaDocument

from .config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    SESSION_FILE,
    PARSE_CHANNELS,
    PARSE_DAYS,
    DATA_DIR,
)
from . import db

logger = logging.getLogger(__name__)

MEDIA_DIR = DATA_DIR / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


class TGParser:
    def __init__(self, phone: str = ""):
        self.phone = phone
        self.client = TelegramClient(
            str(SESSION_FILE),
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH,
        )

    async def start(self):
        """Подключаемся к Telegram. Не запускает интерактивный логин в Docker."""
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise RuntimeError(
                "Telethon-сессия не авторизована. "
                "Выполните авторизацию (см. docs / _auth.py) и положите tg_session.session в data/."
            )
        # HTML parse mode → msg.text возвращает текст с HTML-разметкой (сохраняем форматирование)
        self.client.parse_mode = "html"
        logger.info("✅ Подключено к Telegram")

    async def close(self):
        if self.client.is_connected():
            await self.client.disconnect()

    async def fetch_with_photos(
        self,
        channels: Optional[List[str]] = None,
        since_days: Optional[int] = None,
        limit: int = 20,
        skip_processed: bool = False,
    ) -> List[Dict]:
        """
        Собираем посты из каналов, скачиваем фото в data/media.
        limit — сколько последних сообщений просмотреть в каждом канале.
        Возвращаем список словарей с ключом photo_path (путь к локальному файлу или None).
        """
        channels = channels or PARSE_CHANNELS
        all_posts: List[Dict] = []

        for ch in channels:
            try:
                entity = await self.client.get_entity(ch)
                channel_name = getattr(entity, "title", ch)
                channel_username = getattr(entity, "username", None) or ch
                logger.info(f"📸 Читаем канал: {ch}")

                async for msg in self.client.iter_messages(entity, limit=limit):
                    if not isinstance(msg, Message):
                        continue

                    if not (msg.text or msg.media):
                        continue

                    if skip_processed and db.is_processed(channel_username, msg.id):
                        continue

                    photo_path = await self._download_photo(msg)

                    all_posts.append({
                        "channel": channel_name,
                        "channel_username": channel_username,
                        "msg_id": msg.id,
                        "text": msg.text or "",
                        "photo_path": photo_path,
                        "date": msg_date.isoformat() if msg_date else "",
                    })

                    if skip_processed:
                        db.mark_seen(channel_username, msg.id)
            except Exception as e:
                logger.error(f"❌ Ошибка при чтении {ch}: {e}")

        all_posts.sort(key=lambda m: m["date"])
        logger.info(f"📊 Найдено {len(all_posts)} постов")
        return all_posts

    async def _download_photo(self, msg: Message) -> Optional[str]:
        """Скачиваем фото сообщения в data/media. Возвращаем путь или None."""
        if not msg.media:
            return None
        if not isinstance(msg.media, (MessageMediaPhoto, MessageMediaDocument)):
            return None
        try:
            target = MEDIA_DIR / f"{msg.chat_id}_{msg.id}"
            path = await msg.download_media(file=str(target))
            return str(path) if path else None
        except Exception as e:
            logger.error(f"❌ Не удалось скачать медиа msg {msg.id}: {e}")
            return None
