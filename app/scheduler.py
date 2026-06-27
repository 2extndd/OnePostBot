"""
Очередь постов.
Сохраняем в очередь, затем публикуем с задержкой.
"""

import json
import os
import glob
import logging
from datetime import datetime

from .config import QUEUE_DIR

logger = logging.getLogger(__name__)


def enqueue_post(text: str, photo_path: str = None, source_channel: str = "", msg_id: int = 0):
    """Добавляем пост в очередь."""
    post = {
        "text": text,
        "photo_path": photo_path,
        "source_channel": source_channel,
        "msg_id": msg_id,
        "queued_at": datetime.now().isoformat(),
        "status": "pending",
    }

    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{msg_id}.json"
    filepath = os.path.join(QUEUE_DIR, filename)

    with open(filepath, "w") as f:
        json.dump(post, f, indent=2, ensure_ascii=False)

    logger.info(f"📝 Пост добавлен в очередь: {filepath}")
    return filepath


def get_pending_posts() -> list:
    """Возвращаем список ожидающих постов."""
    posts = []
    for filepath in sorted(glob.glob(os.path.join(QUEUE_DIR, "*.json"))):
        with open(filepath) as f:
            post = json.load(f)
        if post.get("status") == "pending":
            post["_filepath"] = filepath
            posts.append(post)
    return posts


def mark_processed(filepath: str):
    """Помечаем пост как обработанный."""
    with open(filepath) as f:
        post = json.load(f)
    post["status"] = "published"
    post["published_at"] = datetime.now().isoformat()
    with open(filepath, "w") as f:
        json.dump(post, f, indent=2, ensure_ascii=False)

    # Удаляем из очереди
    os.remove(filepath)
    logger.info(f"✅ Пост удалён из очереди: {filepath}")
