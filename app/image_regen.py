"""
Редактирование изображений через gpt-image-2 (VectorEngine, OpenAI-compatible).
Принимает оригинальное фото и добавляет фирменную рамку ONEPROVIDER.
"""

import asyncio
import base64
import logging
import os
import random
from pathlib import Path

from openai import OpenAI, APIStatusError, APITimeoutError, APIConnectionError

from .config import OPENAI_BASE_URL, OPENAI_API_KEY, IMAGE_MODEL, DATA_DIR

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Ленивая инициализация OpenAI клиента."""
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY не задан — нельзя использовать image_regen")
        _client = OpenAI(
            base_url=OPENAI_BASE_URL,
            api_key=OPENAI_API_KEY,
            max_retries=4,
            timeout=120.0,
        )
    return _client


def _is_retryable(e) -> bool:
    if isinstance(e, (APITimeoutError, APIConnectionError)):
        return True
    if isinstance(e, APIStatusError):
        return e.status_code in (429, 500, 502, 503, 529)
    return False


async def regenerate_photo(original_image_path: str) -> str:
    """
    Редактирует оригинальное фото: добавляет фирменную рамку ONEPROVIDER.
    Возвращает путь к результату.
    """
    if not original_image_path or not os.path.exists(original_image_path):
        raise FileNotFoundError(f"Оригинальное фото не найдено: {original_image_path}")

    frame_prompt = (
        "Add a clean minimal white border around the image with black L-shaped corner marks "
        "and vertical ONEPROVIDER text on the right side. "
        "Keep the original photo content exactly unchanged."
    )

    import concurrent.futures
    retries = 0
    while True:
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    lambda: _get_client().images.edit(
                        model=IMAGE_MODEL,
                        image=open(original_image_path, "rb"),
                        prompt=frame_prompt,
                        n=1,
                        size="1024x1024",
                    ),
                )
                response = future.result(timeout=120)

            image_bytes = _decode_image_response(response.data[0])
            output_path = GENERATED_DIR / f"regen_{os.getpid()}_{retries}.png"
            with open(output_path, "wb") as f:
                f.write(image_bytes)
            logger.info(f"🖼 Изображение отредактировано: {output_path} ({len(image_bytes)} bytes)")
            return str(output_path)

        except (APIStatusError, APITimeoutError, APIConnectionError, concurrent.futures.TimeoutError) as e:
            if not _is_retryable(e) or retries >= 4:
                raise
            retries += 1
            wait = min(2 ** retries + random.random(), 30)
            logger.warning(f"🔄 Image regen retry #{retries}: {e}")
            await asyncio.sleep(wait)
        except Exception as e:
            raise


def _decode_image_response(data_item) -> bytes:
    b64 = getattr(data_item, "b64_json", None)
    if b64:
        return base64.b64decode(b64)
    url = getattr(data_item, "url", None)
    if url:
        import urllib.request
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read()
    raise ValueError("Ответ image API не содержит b64_json или url")


GENERATED_DIR = DATA_DIR / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
