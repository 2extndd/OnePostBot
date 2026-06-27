"""
Очередь публикаций.
Тонкая обёртка над слоем хранения db.py.

Жизненный цикл поста:
  pending   — спарсен, ждёт обработки/решения оператора
  approved  — оператор одобрил, ждёт автопубликации по расписанию
  published — опубликован в целевой канал
  failed    — ошибка публикации
"""

import logging
from typing import List, Dict, Optional

from . import db

logger = logging.getLogger(__name__)


def enqueue_post(text: str, photo_path: Optional[str] = None,
                 source_channel: str = "", msg_id: int = 0,
                 status: str = "pending") -> int:
    """Добавить пост в очередь. Возвращает id поста."""
    return db.enqueue(text, photo_path, source_channel, msg_id, status=status)


def get_pending_posts() -> List[Dict]:
    """Посты, ожидающие решения оператора."""
    return db.get_queue(status="pending")


def get_approved_posts() -> List[Dict]:
    """Посты, одобренные к автопубликации."""
    return db.get_queue(status="approved")


def get_post(post_id: int) -> Optional[Dict]:
    return db.get_post(post_id)


def approve_post(post_id: int):
    db.set_status(post_id, "approved")


def mark_published(post_id: int):
    db.set_status(post_id, "published")


def mark_failed(post_id: int, error: str):
    db.set_status(post_id, "failed", error=error)


def update_post(post_id: int, text: str, photo_path: Optional[str] = None):
    db.update_text(post_id, text, photo_path)


# Совместимость со старым API (filepath-based) — больше не используется,
# оставлено, чтобы не падали внешние вызовы.
def mark_processed(identifier=None):
    logger.debug("mark_processed() вызван (legacy no-op)")
