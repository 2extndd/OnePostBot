"""
Регенерация текста через OneProvider (Anthropic-compatible).

Архитектура промптов (3 уровня):
  1. project_context — общий контекст проекта (system prompt, кэшируется)
  2. rewrite_prompt  — инструкция для рерайта основного текста
  3. ad_prompt       — инструкция для добавления рекламной интеграции

Контекст проекта передаётся в system prompt с пометкой cache_control,
чтобы Anthropic кэшировал его и не тратил токены на повторных запросах.
"""

import asyncio
import logging
import random
from anthropic import Anthropic, APIStatusError, APITimeoutError, APIConnectionError

from .config import ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY, LLM_MODEL, LLM_THINKING_BUDGET
from . import db

logger = logging.getLogger(__name__)

_client = None
_lock = None  # для потокобезопасной ленивой инициализации


def _get_client():
    """Ленивая инициализация Anthropic клиента."""
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY не задан — нельзя использовать text_regen")
        _client = Anthropic(
            base_url=ANTHROPIC_BASE_URL,
            api_key=ANTHROPIC_API_KEY,
            max_retries=4,
            timeout=120.0,
        )
    return _client


def _is_retryable(e) -> bool:
    """Проверяет, стоит ли повторить запрос."""
    if isinstance(e, (APITimeoutError, APIConnectionError)):
        return True
    if isinstance(e, APIStatusError):
        return e.status_code in (429, 500, 502, 503, 529)
    return False


async def _call_llm(system_blocks: list, user_text: str, max_tokens: int = 1500) -> str:
    """Единая точка вызова LLM с retry и offload в поток (C1, C3)."""
    import concurrent.futures
    retries = 0
    while True:
        try:
            # offload синхронный вызов в поток (C1)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(lambda: _get_client().messages.create(
                    model=LLM_MODEL,
                    system=system_blocks,
                    messages=[{"role": "user", "content": user_text}],
                    **({"max_tokens": max_tokens + LLM_THINKING_BUDGET, "thinking": {"type": "enabled", "budget_tokens": LLM_THINKING_BUDGET}}
                       if LLM_THINKING_BUDGET > 0 else {"max_tokens": max_tokens}),
                ))
                response = future.result(timeout=180)

            result = _extract_text(response)
            usage = getattr(response, "usage", None)
            if usage:
                logger.info(
                    f"✨ LLM: in={getattr(usage,'input_tokens','?')} "
                    f"out={getattr(usage,'output_tokens','?')} "
                    f"cache_read={getattr(usage,'cache_read_input_tokens','?')}"
                )
            from .tg_html import to_telegram_html
            return to_telegram_html(result)

        except (APIStatusError, APITimeoutError, APIConnectionError, concurrent.futures.TimeoutError) as e:
            if not _is_retryable(e) or retries >= 4:
                raise
            retries += 1
            wait = min(2 ** retries, 6)  # короткий backoff: 2,4,6 сек
            logger.warning(f"🔄 LLM retry #{retries} after {e.__class__.__name__}: {e}")
            await asyncio.sleep(wait)
        except Exception as e:
            # 400/401/413 и другие — не повторяем
            raise


def _extract_text(response) -> str:
    """Извлекает текстовый блок из ответа (пропуская thinking-блоки)."""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return block.text.strip()
    return response.content[-1].text.strip() if response.content else ""


def _build_system_blocks(extra: str = "") -> list:
    project_context = db.get_setting("project_context")
    system_text = project_context
    if extra:
        system_text += f"\n\n{extra}"
    return [
        {"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}},
    ]


def rewrite_news(news_text: str, custom_prompt: str = None) -> str:
    instruction = custom_prompt or db.get_setting("rewrite_prompt")
    user_text = f"{instruction}\n\n<source_post>\n{news_text}\n</source_post>"
    result = _call_llm(_build_system_blocks(), user_text)
    logger.info(f"📝 Новость переписана ({len(result)} символов)")
    return result


def add_ad(text: str) -> str:
    instruction = db.get_setting("ad_prompt")
    user_text = f"{instruction}\n\n<post_to_keep>\n{text}\n</post_to_keep>"
    result = _call_llm(_build_system_blocks(), user_text)
    logger.info(f"🎯 Реклама добавлена ({len(result)} символов)")
    return result


def translate_text(news_text: str) -> str:
    from .prompts import TRANSLATE_PROMPT
    system_blocks = [{"type": "text", "text": "Ты — профессиональный переводчик. Переводишь точно, без отсебятины."}]
    user_text = f"{TRANSLATE_PROMPT}\n\n<source_post>\n{news_text}\n</source_post>"
    result = _call_llm(system_blocks, user_text)
    logger.info(f"🌐 Текст переведён ({len(result)} символов)")
    return result


# ---------- Обратная совместимость ----------

def regenerate_text(original_text: str, context: str = "") -> str:
    if context and context.strip():
        return rewrite_news(original_text, custom_prompt=context)
    return rewrite_news(original_text)


def generate_caption_for_photo(photo_description: str, channel_context: str = "") -> str:
    user_text = f"Напиши короткий привлекательный пост-подпись для фото.\nОписание фото: {photo_description}\n\nТолько пост, 1-2 абзаца, без объяснений."
    return _call_llm(_build_system_blocks(), user_text, max_tokens=512)
