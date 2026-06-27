"""
Регенерация изображения через GPT Image 2 (OpenAI-compatible, cc-vibe).
"""

import logging
import os
from openai import OpenAI

from .config import OPENAI_BASE_URL, OPENAI_API_KEY, IMAGE_MODEL

logger = logging.getLogger(__name__)

client = OpenAI(
    base_url=OPENAI_BASE_URL,
    api_key=OPENAI_API_KEY,
)


def regenerate_photo(image_path: str, prompt: str) -> str:
    """
    Перегенерируем фото через GPT Image 2 Edit.
    Возвращаем путь к новому файлу.
    """
    with open(image_path, "rb") as f:
        image_data = f.read()

    response = client.images.edit(
        model=IMAGE_MODEL,
        image=image_data,
        prompt=prompt,
        n=1,
        size="1024x1024",
    )

    # Сохраняем результат
    output_dir = os.environ.get("DATA_DIR", "/app/data") / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = os.path.join(output_dir, f"regenerated_{os.path.basename(image_path)}")

    with open(output_path, "wb") as f:
        f.write(response.data[0].b64_bytes.encode())

    logger.info(f"🖼 Фото переработано: {output_path}")
    return output_path
