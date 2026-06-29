"""
Слой хранения на SQLite.
Отвечает за:
  - dedup обработанных сообщений (чтобы не парсить/публиковать дважды)
  - очередь постов на публикацию (pending -> approved -> published)
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional

from .config import PROCESSED_DB

logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_messages (
    channel TEXT NOT NULL,
    msg_id INTEGER NOT NULL,
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (channel, msg_id)
);

CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    photo_path TEXT,
    source_channel TEXT,
    msg_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | published | failed
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);

CREATE TABLE IF NOT EXISTS channels (
    username TEXT PRIMARY KEY,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS parsed_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    photo_path TEXT,
    photo_paths TEXT,
    source_channel TEXT,
    msg_id INTEGER,
    date TEXT,
    channel_title TEXT,
    channel_username TEXT,
    edited_text TEXT,
    showing_original BOOLEAN DEFAULT 0,
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(PROCESSED_DB), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Создаём таблицы, если их нет."""
    with _connect() as conn:
        conn.executescript(SCHEMA)
    logger.info(f"🗄  БД инициализирована: {PROCESSED_DB}")


# ---------- dedup ----------

def is_processed(channel: str, msg_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM processed_messages WHERE channel = ? AND msg_id = ?",
            (channel, msg_id),
        ).fetchone()
        return row is not None


def mark_seen(channel: str, msg_id: int):
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_messages (channel, msg_id) VALUES (?, ?)",
            (channel, msg_id),
        )


# ---------- queue ----------

def enqueue(text: str, photo_path: Optional[str], source_channel: str, msg_id: int,
            status: str = "pending") -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO queue (text, photo_path, source_channel, msg_id, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (text, photo_path, source_channel, msg_id, status),
        )
        post_id = cur.lastrowid
    logger.info(f"📝 Пост #{post_id} в очереди (status={status})")
    return post_id


def get_queue(status: Optional[str] = None) -> List[Dict]:
    query = "SELECT * FROM queue"
    params: tuple = ()
    if status:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY queued_at ASC"
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_post(post_id: int) -> Optional[Dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM queue WHERE id = ?", (post_id,)).fetchone()
        return dict(row) if row else None


def set_status(post_id: int, status: str, error: Optional[str] = None):
    fields = "status = ?"
    params: list = [status]
    if status == "published":
        fields += ", published_at = ?"
        params.append(datetime.now().isoformat())
    if error is not None:
        fields += ", error = ?"
        params.append(error)
    params.append(post_id)
    with _connect() as conn:
        conn.execute(f"UPDATE queue SET {fields} WHERE id = ?", tuple(params))
    logger.info(f"📌 Пост #{post_id} -> {status}")


def update_text(post_id: int, text: str, photo_path: Optional[str] = None):
    with _connect() as conn:
        if photo_path is not None:
            conn.execute(
                "UPDATE queue SET text = ?, photo_path = ? WHERE id = ?",
                (text, photo_path, post_id),
            )
        else:
            conn.execute("UPDATE queue SET text = ? WHERE id = ?", (text, post_id))


# ---------- Channels ----------

def get_channels() -> List[str]:
    """Возвращает список всех каналов."""
    with _connect() as conn:
        rows = conn.execute("SELECT username FROM channels ORDER BY added_at").fetchall()
    return [r["username"] for r in rows]


def add_channel(username: str):
    """Добавляет канал в список."""
    username = username.strip().lstrip("@")
    with _connect() as conn:
        conn.execute("INSERT OR IGNORE INTO channels (username) VALUES (?)", (username,))
    logger.info(f"➕ Канал @{username} добавлен")


def remove_channel(username: str):
    """Удаляет канал из списка."""
    username = username.strip().lstrip("@")
    with _connect() as conn:
        conn.execute("DELETE FROM channels WHERE username = ?", (username,))
    logger.info(f"➖ Канал @{username} удалён")


# ---------- Settings (key-value) ----------

from . import prompts

DEFAULT_SETTINGS = {
    "project_context": prompts.PROJECT_CONTEXT,
    "rewrite_prompt": prompts.REWRITE_PROMPT,
    "ad_prompt": prompts.AD_PROMPT,
    "image_prompt": prompts.IMAGE_PROMPT,
}


def get_setting(key: str) -> str:
    """Получить настройку. Возвращает сохранённое значение или дефолт."""
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row:
        return row["value"]
    return DEFAULT_SETTINGS.get(key, "")


def set_setting(key: str, value: str):
    """Сохранить настройку."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    logger.info(f"⚙️ Настройка '{key}' обновлена ({len(value)} символов)")


def get_all_settings() -> Dict[str, str]:
    """Все настройки (с дефолтами)."""
    result = dict(DEFAULT_SETTINGS)
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    for r in rows:
        result[r["key"]] = r["value"]
    return result


# ---------- Parsed Posts (fixes lost-update from FSM) ----------

def save_parsed_post(text: str, photo_path: Optional[str], photo_paths=None,
                     source_channel: str = "", msg_id: int = 0, date: str = "",
                     channel_title: str = "", channel_username: str = "") -> int:
    """Сохраняет спаршенный пост. photo_paths сериализуется в JSON. Возвращает id."""
    paths_json = json.dumps(photo_paths) if photo_paths else None
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO parsed_posts 
               (text, photo_path, photo_paths, source_channel, msg_id, date, 
                channel_title, channel_username)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (text, photo_path, paths_json, source_channel, msg_id, date,
             channel_title, channel_username),
        )
        return cur.lastrowid


def _deserialize_post(row) -> Optional[Dict]:
    if not row:
        return None
    d = dict(row)
    if d.get("photo_paths"):
        try:
            d["photo_paths"] = json.loads(d["photo_paths"])
        except (ValueError, TypeError):
            d["photo_paths"] = None
    return d


def get_parsed_post(post_id: int) -> Optional[Dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM parsed_posts WHERE id = ?", (post_id,)).fetchone()
    return _deserialize_post(row)


def update_parsed_post(post_id: int, edited_text: str, photo_path: Optional[str] = None):
    """Обновляет пост после рерайта/рекламы/фото."""
    with _connect() as conn:
        if photo_path is not None:
            conn.execute(
                "UPDATE parsed_posts SET edited_text = ?, photo_path = ?, showing_original = 0 WHERE id = ?",
                (edited_text, photo_path, post_id),
            )
        else:
            conn.execute(
                "UPDATE parsed_posts SET edited_text = ?, showing_original = 0 WHERE id = ?",
                (edited_text, post_id),
            )
    logger.info(f"📝 Пост #{post_id} обновлён")


def get_parsed_posts(ids: List[int]) -> List[Dict]:
    """Получить список постов по id."""
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    with _connect() as conn:
        rows = conn.execute(f"SELECT * FROM parsed_posts WHERE id IN ({placeholders})", ids).fetchall()
    return [_deserialize_post(r) for r in rows]


def delete_parsed_posts(ids: List[int]):
    """Удалить посты после публикации."""
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    with _connect() as conn:
        conn.execute(f"DELETE FROM parsed_posts WHERE id IN ({placeholders})", ids)
    logger.info(f"🗑 Удалено {len(ids)} постов из очереди")
