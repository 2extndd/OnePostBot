"""
Регенерация изображения через GPT Image (OpenAI-compatible, cc-vibe).
"""

import base64
import logging
import os
from pathlib import Path

from openai import OpenAI

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
        )
    return _client

GENERATED_DIR = DATA_DIR / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)


def _decode_image_response(data_item) -> bytes:
    """Извлекаем байты картинки из ответа OpenAI (b64 или url)."""
    b64 = getattr(data_item, "b64_json", None)
    if b64:
        return base64.b64decode(b64)

    url = getattr(data_item, "url", None)
    if url:
        import urllib.request
        with urllib.request.urlopen(url) as resp:
            return resp.read()

    raise ValueError("Ответ image API не содержит b64_json или url")


def regenerate_photo(image_path: str, prompt: str) -> str:
    """
    Перегенерируем фото через image-edit API.
    Возвращаем путь к новому файлу.
    """
    if not image_path or not os.path.exists(image_path):
        raise FileNotFoundError(f"Файл изображения не найден: {image_path}")

    with open(image_path, "rb") as f:
        response = _get_client().images.edit(
            model=IMAGE_MODEL,
            image=f,
            prompt=prompt,
            n=1,
            size="1024x1024",
        )

    image_bytes = _decode_image_response(response.data[0])

    output_path = GENERATED_DIR / f"regenerated_{os.path.basename(image_path)}"
    if output_path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        output_path = output_path.with_suffix(".png")

    with open(output_path, "wb") as f:
        f.write(image_bytes)

    logger.info(f"🖼 Фото переработано: {output_path}")
    return str(output_path)


def generate_image(prompt: str, filename: str = "generated") -> str:
    """
    Генерируем новое изображение с нуля по промпту.
    Возвращаем путь к файлу.
    """
    response = _get_client().images.generate(
        model=IMAGE_MODEL,
        prompt=prompt,
        n=1,
        size="1024x1024",
    )

    image_bytes = _decode_image_response(response.data[0])
    output_path = GENERATED_DIR / f"{filename}.png"

    with open(output_path, "wb") as f:
        f.write(image_bytes)

    logger.info(f"🖼 Изображение сгенерировано: {output_path}")
    return str(output_path)
