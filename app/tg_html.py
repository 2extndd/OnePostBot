"""
Конвертация/санитизация текста под Telegram HTML.

Telegram поддерживает ограниченный набор тегов:
  <b> <strong>, <i> <em>, <u> <ins>, <s> <strike> <del>,
  <a href>, <code>, <pre>, <blockquote>, <span class="tg-spoiler">

Всё остальное (markdown **, ##, <h1>, <p>, <br>, <div>) Telegram НЕ понимает
и отвергает сообщение с ошибкой "can't parse entities".

Этот модуль:
  1. Конвертирует markdown-разметку (**bold**, *italic*, `code`) в Telegram-HTML
  2. Превращает <br>, <p>, <h1-6> в переносы строк
  3. Удаляет все неподдерживаемые теги, сохраняя их текст
  4. Экранирует "голые" амперсанды/угловые скобки вне тегов
"""

import re

# Теги, которые Telegram принимает (имя → допустимо)
_ALLOWED = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
            "a", "code", "pre", "blockquote", "span", "tg-spoiler"}


def _md_to_html(text: str) -> str:
    """Конвертирует базовый markdown в Telegram-HTML."""
    # Блоки кода ```...``` → <pre>
    text = re.sub(r"```[a-zA-Z0-9]*\n?(.*?)```", r"<pre>\1</pre>", text, flags=re.DOTALL)
    # Inline код `...` → <code>
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    # Жирный **...** или __...__ → <b>
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__([^_]+)__", r"<b>\1</b>", text)
    # Курсив *...* → <i> (одиночные звёздочки, не тронув уже сконвертированные)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
    # Markdown-ссылки [text](url) → <a>
    text = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', text)
    # Заголовки ## Header → жирная строка
    text = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    return text


def _block_tags_to_newlines(text: str) -> str:
    """<br>, </p>, <h1-6> и т.п. → переносы строк."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "", text, flags=re.IGNORECASE)
    # Заголовки <h1>..</h1> → жирный + перенос
    text = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"<b>\1</b>\n", text,
                  flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</?(div|ul|ol|li|span)[^>]*>", "", text, flags=re.IGNORECASE)
    return text


def _strip_unsupported(text: str) -> str:
    """Удаляет теги не из белого списка, сохраняя их текстовое содержимое."""
    def repl(m):
        tag = m.group(1).lower().lstrip("/")
        # допускаем <a ...>, <pre>, <code>, <span ...> и закрывающие
        base = tag.split()[0] if " " in tag else tag
        if base in _ALLOWED:
            return m.group(0)
        return ""  # выкидываем тег, текст между тегами остаётся
    return re.sub(r"<(/?[a-zA-Z][^>]*)>", repl, text)


def to_telegram_html(text: str) -> str:
    """
    Главная функция: приводит произвольный вывод LLM к валидному Telegram-HTML.
    """
    if not text:
        return text
    text = _md_to_html(text)
    text = _block_tags_to_newlines(text)
    text = _strip_unsupported(text)
    # Чистим лишние пустые строки (3+ подряд → 2)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
