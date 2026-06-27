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
    TELETHON_STRING_SESSION,
)
from . import db
from .tg_html import to_telegram_html


def _sanitize(text):
    return to_telegram_html(text or "")

logger = logging.getLogger(__name__)

MEDIA_DIR = DATA_DIR / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


class TGParser:
    def __init__(self, phone: str = ""):
        self.phone = phone
        if TELETHON_STRING_SESSION:
            from telethon.sessions import StringSession
            self.client = TelegramClient(
                StringSession(TELETHON_STRING_SESSION),
                TELEGRAM_API_ID,
                TELEGRAM_API_HASH,
            )
        else:
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
        Альбомы (несколько фото с одним grouped_id) объединяются в один пост.
        limit — сколько последних ПОСТОВ (не сообщений) вернуть на канал.
        Возвращаем список словарей с photo_paths (список путей) и photo_path (первый, для совместимости).
        """
        channels = channels or PARSE_CHANNELS
        all_posts: List[Dict] = []

        for ch in channels:
            try:
                entity = await self.client.get_entity(ch)
                channel_name = getattr(entity, "title", ch)
                channel_username = getattr(entity, "username", None) or ch
                logger.info(f"📸 Читаем канал: {ch}")

                # Читаем больше сообщений, чем нужно постов (альбомы съедают несколько сообщений)
                raw_limit = max(limit * 4, 40)
                # Группируем по grouped_id
                groups: Dict = {}
                order: List = []

                async for msg in self.client.iter_messages(entity, limit=raw_limit):
                    if not isinstance(msg, Message):
                        continue
                    if not (msg.text or msg.media):
                        continue

                    gid = msg.grouped_id or msg.id  # одиночные посты — по своему id
                    if gid not in groups:
                        # достаточно групп — останавливаемся на новой группе
                        if len(order) >= limit:
                            break
                        groups[gid] = {
                            "messages": [],
                            "text": "",
                            "msg_id": msg.id,
                            "date": msg.date,
                        }
                        order.append(gid)
                    g = groups[gid]
                    g["messages"].append(msg)
                    # Текст альбома обычно в одном из сообщений — берём непустой
                    if msg.text and not g["text"]:
                        g["text"] = msg.text
                    # msg_id/date — минимальные (первое сообщение группы)
                    if msg.id < g["msg_id"]:
                        g["msg_id"] = msg.id
                        g["date"] = msg.date

                # Берём только нужное число постов (свежие — первые в order)
                for gid in order[:limit]:
                    g = groups[gid]
                    if skip_processed and db.is_processed(channel_username, g["msg_id"]):
                        continue

                    photo_paths = []
                    for m in g["messages"]:
                        p = await self._download_photo(m)
                        if p:
                            photo_paths.append(p)

                    all_posts.append({
                        "channel": channel_name,
                        "channel_username": channel_username,
                        "msg_id": g["msg_id"],
                        "text": _sanitize(g["text"]),
                        "photo_paths": photo_paths,
                        "photo_path": photo_paths[0] if photo_paths else None,
                        "date": g["date"].isoformat() if g["date"] else "",
                    })

                    if skip_processed:
                        db.mark_seen(channel_username, g["msg_id"])
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
