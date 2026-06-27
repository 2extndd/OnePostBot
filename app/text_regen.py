"""
Регенерация текста через OneProvider (Anthropic-compatible).
"""

import logging
from anthropic import Anthropic

from .config import ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

client = Anthropic(
    base_url=ANTHROPIC_BASE_URL,
    api_key=ANTHROPIC_API_KEY,
)


def regenerate_text(original_text: str, context: str = "") -> str:
    """
    Переписываем текст поста.
    Сохраняем смысл, но делаем уникальный контент.
    """
    prompt = f"""Перепиши этот текст поста. Сохрани основной смысл и факты, но:
- Используй другой стиль изложения
- Добавь вводную часть
- Если есть фото — упомяни его
- Сделай текст более интересным и читабельным
- Длина — примерно как оригинал

Контекст: {context}

Оригинал:
{original_text}

Только результат, без объяснений:"""

    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    regenerated = response.content[0].text.strip()
    logger.info(f"✨ Текст переписан ({len(regenerated)} символов)")
    return regenerated


def generate_caption_for_photo(photo_description: str, channel_context: str) -> str:
    """Генерируем подпись к переработанному фото."""
    prompt = f"""Напиши короткий привлекательный пост-подпись для фото.

Контекст канала: {channel_context}
Описание фото: {photo_description}

Только пост, без объяснений. 1-2 абзаца."""

    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text.strip()
