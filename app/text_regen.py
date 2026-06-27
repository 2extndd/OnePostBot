"""
Регенерация текста через OneProvider (Anthropic-compatible).

Архитектура промптов (3 уровня):
  1. project_context — общий контекст проекта (system prompt, кэшируется)
  2. rewrite_prompt  — инструкция для рерайта основного текста
  3. ad_prompt       — инструкция для добавления рекламной интеграции

Контекст проекта передаётся в system prompt с пометкой cache_control,
чтобы Anthropic кэшировал его и не тратил токены на повторных запросах.
"""

import logging
from anthropic import Anthropic

from .config import ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY, LLM_MODEL, LLM_THINKING_BUDGET
from . import db

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Ленивая инициализация Anthropic клиента."""
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY не задан — нельзя использовать text_regen")
        _client = Anthropic(
            base_url=ANTHROPIC_BASE_URL,
            api_key=ANTHROPIC_API_KEY,
        )
    return _client


def _extract_text(response) -> str:
    """Извлекает текстовый блок из ответа (пропуская thinking-блоки)."""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return block.text.strip()
    # fallback
    return response.content[-1].text.strip() if response.content else ""


def _build_system_blocks(extra: str = "") -> list:
    """
    System prompt с project_context. Помечаем cache_control для кэширования.
    """
    project_context = db.get_setting("project_context")
    system_text = (
        "Ты — редактор контента для Telegram-канала.\n\n"
        f"ОБЩИЙ КОНТЕКСТ ПРОЕКТА:\n{project_context}"
    )
    if extra:
        system_text += f"\n\n{extra}"

    return [
        {
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _call_llm(system_blocks: list, user_text: str, max_tokens: int = 1500) -> str:
    """Единая точка вызова LLM с обработкой ответа и extended thinking."""
    kwargs = {
        "model": LLM_MODEL,
        "system": system_blocks,
        "messages": [{"role": "user", "content": user_text}],
    }

    if LLM_THINKING_BUDGET > 0:
        # max_tokens должен превышать budget_tokens
        kwargs["max_tokens"] = max_tokens + LLM_THINKING_BUDGET
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": LLM_THINKING_BUDGET}
    else:
        kwargs["max_tokens"] = max_tokens

    response = _get_client().messages.create(**kwargs)
    result = _extract_text(response)
    usage = getattr(response, "usage", None)
    if usage:
        logger.info(
            f"✨ LLM: in={getattr(usage,'input_tokens','?')} "
            f"out={getattr(usage,'output_tokens','?')} "
            f"cache_read={getattr(usage,'cache_read_input_tokens','?')}"
        )
    return result


def rewrite_news(news_text: str, custom_prompt: str = None) -> str:
    """
    Рерайт основного текста новости.
    Использует rewrite_prompt из настроек (или custom_prompt, если задан).
    """
    instruction = custom_prompt or db.get_setting("rewrite_prompt")
    user_text = f"{instruction}\n\nИСХОДНАЯ НОВОСТЬ:\n{news_text}"
    result = _call_llm(_build_system_blocks(), user_text)
    logger.info(f"📝 Новость переписана ({len(result)} символов)")
    return result


def add_ad(text: str) -> str:
    """
    Добавляет рекламную интеграцию к тексту.
    Использует ad_prompt из настроек. НЕ переписывает основной текст.
    """
    instruction = db.get_setting("ad_prompt")
    user_text = f"{instruction}\n\nТЕКСТ ПОСТА:\n{text}"
    result = _call_llm(_build_system_blocks(), user_text)
    logger.info(f"🎯 Реклама добавлена ({len(result)} символов)")
    return result


def translate_text(news_text: str) -> str:
    """Перевод на английский с сохранением смысла."""
    user_text = (
        "Переведи этот текст на английский язык. Сохрани смысл и стиль. "
        f"Только результат:\n\n{news_text}"
    )
    result = _call_llm(_build_system_blocks(), user_text)
    logger.info(f"🌐 Текст переведён ({len(result)} символов)")
    return result


# ---------- Обратная совместимость ----------

def regenerate_text(original_text: str, context: str = "") -> str:
    """
    Legacy-обёртка. Если context выглядит как кастомный промпт — используем его,
    иначе берём дефолтный rewrite_prompt.
    """
    if context and context.strip():
        return rewrite_news(original_text, custom_prompt=context)
    return rewrite_news(original_text)


def generate_caption_for_photo(photo_description: str, channel_context: str = "") -> str:
    """Генерируем подпись к переработанному фото."""
    user_text = (
        f"Напиши короткий привлекательный пост-подпись для фото.\n"
        f"Описание фото: {photo_description}\n\n"
        f"Только пост, 1-2 абзаца, без объяснений."
    )
    return _call_llm(_build_system_blocks(), user_text, max_tokens=512)
