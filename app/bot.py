"""
Telegram Bot — основной интерфейс управления.
Команды: /parse N, /publish, /watch, /stop, /help
"""

import logging
import asyncio
import random
import traceback
from typing import Dict, List

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    Message,
    CallbackQuery,
    FSInputFile,
)


def _photo(path: str):
    """Оборачивает локальный путь в FSInputFile, URL оставляет как есть."""
    if path and (path.startswith("http://") or path.startswith("https://")):
        return path
    return FSInputFile(path)


def _cap(text: str, limit: int = 1024) -> str:
    """Безопасная обрезка caption с закрытием HTML-тегов."""
    from .tg_html import safe_truncate
    return safe_truncate(text, limit)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from .config import (
    BOT_TOKEN, TOPIC_ID, CHAT_ID, TOPICS,
    PARSE_CHANNELS, PARSE_DAYS,
    POST_DELAY_MIN, POST_DELAY_MAX,
    TELEPHONE,
)
from .parser import TGParser
from .text_regen import regenerate_text, generate_caption_for_photo, rewrite_news, add_ad, translate_text
from .image_regen import regenerate_photo
from .publisher import post_via_bot
from .scheduler import enqueue_post, get_pending_posts, approve_post, mark_published, mark_failed, get_post, update_post
from . import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Глобальное состояние
active_watches: Dict[str, bool] = {}


class RewriteState(StatesGroup):
    waiting_prompt = State()


class ParseState(StatesGroup):
    waiting_count = State()


class ChannelState(StatesGroup):
    waiting_add = State()


class SettingsState(StatesGroup):
    waiting_value = State()


# ---------- keyboards ----------

def main_menu_kb():
    """Главное меню (inline)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Парсить посты", callback_data="menu_parse")],
        [
            InlineKeyboardButton(text="📚 Управление каналами", callback_data="menu_channels"),
            InlineKeyboardButton(text="📤 Опубликовать", callback_data="menu_publish"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings"),
            InlineKeyboardButton(text="❓ Помощь", callback_data="menu_help"),
        ],
    ])


def channels_menu_kb():
    """Меню управления каналами (inline)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список каналов", callback_data="channels_list")],
        [
            InlineKeyboardButton(text="➕ Добавить канал", callback_data="channels_add"),
            InlineKeyboardButton(text="➖ Удалить канал", callback_data="channels_del"),
        ],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="menu_main")],
    ])


def settings_menu_kb():
    """Меню настроек промптов (inline)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Контекст проекта", callback_data="settings_project_context")],
        [
            InlineKeyboardButton(text="📝 Промпт рерайта", callback_data="settings_rewrite_prompt"),
            InlineKeyboardButton(text="🎯 Промпт рекламы", callback_data="settings_ad_prompt"),
        ],
        [InlineKeyboardButton(text="🖼 Промпт изображений", callback_data="settings_image_prompt")],
        [InlineKeyboardButton(text="👁 Показать все", callback_data="settings_show_all")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="menu_main")],
    ])


# ---------- helpers ----------

import contextvars

_UNSET = object()
_current_thread = contextvars.ContextVar("current_thread", default=None)


@dp.update.outer_middleware()
async def thread_context_middleware(handler, event, data):
    """Запоминает тред входящего апдейта, чтобы ответы шли в тот же топик."""
    thread = None
    msg = getattr(event, "message", None)
    cb = getattr(event, "callback_query", None)
    if msg is not None:
        thread = getattr(msg, "message_thread_id", None)
    elif cb is not None and getattr(cb, "message", None) is not None:
        thread = getattr(cb.message, "message_thread_id", None)
    token = _current_thread.set(thread)
    try:
        return await handler(event, data)
    finally:
        _current_thread.reset(token)


async def send_with_topic(chat_id: int, text: str, reply_markup=None, thread_id=_UNSET, parse_mode=None):
    """
    Отправить сообщение.
    thread_id:
      - не передан (_UNSET) → берём тред текущего апдейта (из middleware)
      - None → без треда (личка / обычный чат)
      - число → конкретный тред
    """
    async def _send(tid):
        kwargs = {"chat_id": chat_id, "text": text}
        if tid:
            kwargs["message_thread_id"] = tid
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        logger.info(f"➡️ send chat={chat_id} thread={tid} has_kb={reply_markup is not None}")
        await bot.send_message(**kwargs)

    target_thread = _current_thread.get() if thread_id is _UNSET else thread_id

    try:
        await _send(target_thread)
    except TelegramForbiddenError as e:
        logger.error(f"TelegramForbiddenError: {e}")
        try:
            await bot.send_message(chat_id=chat_id, text="❌ Ошибка доступа: проверьте права бота в канале")
        except Exception:
            pass
    except TelegramBadRequest as e:
        if "thread" in str(e).lower():
            try:
                await _send(None)
            except Exception as e2:
                logger.error(f"send_with_topic retry failed: {e2}")
        else:
            logger.error(f"send_with_topic BadRequest: {e}")


def thread_of(message: Message):
    """Извлекает message_thread_id из входящего сообщения (или None)."""
    return getattr(message, "message_thread_id", None)


async def send_error(chat_id: int, text: str, thread_id=_UNSET):
    """Отправить ошибку."""
    await send_with_topic(chat_id, f"❌ {text}", thread_id=thread_id)


async def cb_send(callback, text, reply_markup=None):
    """Ответ на callback в тот же чат/тред (через middleware-контекст)."""
    await send_with_topic(callback.message.chat.id, text, reply_markup=reply_markup)


# ---------- commands ----------

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await send_with_topic(
        message.chat.id,
        "🤖 TG Publisher бот активен!\n\nВыберите действие из меню ниже:",
        reply_markup=main_menu_kb(),
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await send_with_topic(
        message.chat.id,
        "📋 Команды бота:\n\n"
        "/parse N — показать последние N постов\n"
        "/parse @channel N — парсить конкретный канал\n\n"
        "📚 Управление каналами:\n"
        "/channels — список каналов\n"
        "/addchannel @канал — добавить канал\n"
        "/delchannel @канал — удалить канал\n\n"
        "При показе постов доступны кнопки:\n"
        "• Рерайт — переписать текст (на английском)\n"
        "• Рерайт промт — переписать с твоим промптом\n"
        "• Перевести — перевести на английский\n"
        "• Перегенерировать фото — улучшить изображение\n"
        "• Опубликовать — добавить в очередь\n\n"
        "/publish — опубликовать одобренные посты\n"
        "/watch — включить мониторинг новых постов\n"
        "/stop — остановить мониторинг\n"
        "/config — текущие настройки",
    )


async def do_parse(message: Message, state: FSMContext, count: int = 10, channel: str = None):
    """Общая логика парсинга — вызывается из команды и из меню."""
    parser = TGParser(phone=TELEPHONE)
    await parser.start()

    try:
        if channel:
            channels = [channel]
        else:
            db_channels = db.get_channels()
            channels = db_channels if db_channels else PARSE_CHANNELS
        if not channels:
            await send_error(message.chat.id, "Нет каналов для парсинга. Добавьте через меню «Управление каналами».")
            return

        posts = await parser.fetch_with_photos(channels=channels, limit=count)

        if not posts:
            await send_error(message.chat.id, "Нет постов в каналах.")
            return

        # Сохраняем посты в БД (фиксит lost-update)
        post_ids = []
        for p in posts:
            photo_paths = p.get("photo_paths") or ([p.get("photo_path")] if p.get("photo_path") else None)
            pid = db.save_parsed_post(
                text=p["text"],
                photo_path=p.get("photo_path"),
                photo_paths=photo_paths,
                source_channel=p.get("channel", ""),
                msg_id=p["msg_id"],
                date=p.get("date", ""),
                channel_title=p.get("channel", ""),
                channel_username=p.get("channel_username", ""),
            )
            post_ids.append(pid)

        # Сохраняем id в состоянии, показываем ОДНУ карточку с навигацией
        await state.update_data(post_ids=post_ids, current_index=0, card_message_id=None, card_is_photo=False)
        await send_with_topic(message.chat.id, f"📥 Найдено {len(posts)} постов из {len(channels)} каналов.")
        await show_card(message, state, index=0, edit=False)

    except Exception as e:
        logger.error(f"Parse error: {e}\n{traceback.format_exc()}")
        await send_error(message.chat.id, f"{e}")
    finally:
        await parser.close()


@dp.message(Command("parse"))
async def cmd_parse(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    count = 10
    channel = None

    if len(args) >= 2:
        arg = args[1]
        if arg.startswith("@"):
            channel = arg
        else:
            try:
                count = int(arg)
            except ValueError:
                pass

    if len(args) >= 3:
        try:
            count = int(args[2])
        except ValueError:
            pass

    await do_parse(message, state, count=count, channel=channel)


@dp.message(Command("config"))
async def cmd_config(message: Message):
    from .config import TELEGRAM_API_ID, PARSE_CHANNELS, TOPIC_ID, CHAT_ID
    await send_with_topic(
        message.chat.id,
        f"⚙️ Настройки:\n"
        f"API ID: {TELEGRAM_API_ID}\n"
        f"Парсим: {PARSE_CHANNELS}\n"
        f"Ответ в топик: {TOPIC_ID}\n"
        f"Chat ID: {CHAT_ID}\n"
        f"Дней назад: {PARSE_DAYS}\n"
        f"Задержка постинга: {POST_DELAY_MIN}-{POST_DELAY_MAX} мин",
    )


# ---------- channel management ----------

@dp.message(Command("channels"))
async def cmd_channels(message: Message):
    """Показать список каналов."""
    channels = db.get_channels()
    if not channels:
        await send_with_topic(message.chat.id, "📭 Список каналов пуст. Добавьте через /addchannel @канал")
        return
    text = "📚 Каналы для парсинга:\n" + "\n".join(f"• @{ch}" for ch in channels)
    await send_with_topic(message.chat.id, text)


@dp.message(Command("addchannel"))
async def cmd_addchannel(message: Message):
    """Добавить канал в список."""
    args = message.text.split()
    if len(args) < 2:
        await send_error(message.chat.id, "Укажите канал: /addchannel @канал")
        return
    username = args[1].strip().lstrip("@")
    db.add_channel(username)
    await send_with_topic(message.chat.id, f"✅ Канал @{username} добавлен")


@dp.message(Command("delchannel"))
async def cmd_delchannel(message: Message):
    """Удалить канал из списка."""
    args = message.text.split()
    if len(args) < 2:
        await send_error(message.chat.id, "Укажите канал: /delchannel @канал")
        return
    username = args[1].strip().lstrip("@")
    db.remove_channel(username)
    await send_with_topic(message.chat.id, f"✅ Канал @{username} удалён")


# ---------- post display ----------

def _post_kb(index: int, total: int = 1) -> InlineKeyboardMarkup:
    """Клавиатура карточки: навигация + действия."""
    nav_prev = InlineKeyboardButton(
        text="⬅️ Назад" if index > 0 else "⬅️",
        callback_data="nav_prev" if index > 0 else "noop",
    )
    nav_center = InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="noop")
    nav_next = InlineKeyboardButton(
        text="➡️ Далее" if index < total - 1 else "➡️",
        callback_data="nav_next" if index < total - 1 else "noop",
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [nav_prev, nav_center, nav_next],
            [
                InlineKeyboardButton(text="📝 Рерайт", callback_data="act_rewrite"),
                InlineKeyboardButton(text="✍️ Рерайт промт", callback_data="act_rewrite_custom"),
            ],
            [
                InlineKeyboardButton(text="🎯 Реклама", callback_data="act_ad"),
                InlineKeyboardButton(text="🌐 Перевести", callback_data="act_translate"),
            ],
            [
                InlineKeyboardButton(text="🖼 Фото", callback_data="act_photo"),
                InlineKeyboardButton(text="📄 Оригинал", callback_data="act_orig"),
            ],
            [
                InlineKeyboardButton(text="✅ Опубликовать", callback_data="act_publish"),
            ],
        ],
    )


async def _total(state) -> int:
    data = await state.get_data()
    return len(data.get("post_ids", []))


async def show_card(message: Message, state: FSMContext, index: int = 0, edit: bool = False):
    """
    Показать карточку поста (single-message card view).
    edit=False → отправить новую карточку, сохранить card_message_id/card_is_photo
    edit=True  → отредактировать текущую карточку (или пересоздать при смене типа)
    """
    data = await state.get_data()
    post_ids = data.get("post_ids", [])
    total = len(post_ids)
    if total == 0:
        await send_with_topic(message.chat.id, "📭 Нет постов.")
        return

    index = max(0, min(index, total - 1))
    post = db.get_parsed_post(post_ids[index])
    if not post:
        await send_with_topic(message.chat.id, "❌ Пост не найден.")
        return

    # Текущая версия для показа (оригинал/отредактированный)
    if post.get("showing_original"):
        body = post["text"]
    else:
        body = post.get("edited_text") or post["text"]
    channel_name = post.get("channel_title") or post.get("channel_username") or "unknown"
    kb = _post_kb(index, total)

    photo_paths = post.get("photo_paths") or ([post["photo_path"]] if post.get("photo_path") else [])
    is_photo = bool(photo_paths)
    caption = _cap(body, 1024) if body else channel_name

    card_id = data.get("card_message_id")
    card_is_photo = data.get("card_is_photo", False)
    chat_id = message.chat.id

    if edit and card_id is not None:
        # Если тип совпадает — редактируем на месте
        if is_photo and card_is_photo:
            try:
                from aiogram.types import InputMediaPhoto
                await bot.edit_message_media(
                    chat_id=chat_id, message_id=card_id,
                    media=InputMediaPhoto(media=_photo(photo_paths[0]), caption=caption, parse_mode="HTML"),
                    reply_markup=kb,
                )
                return
            except Exception as e:
                logger.warning(f"edit_media failed: {e}")
                # пробуем хотя бы caption
                try:
                    await bot.edit_message_caption(chat_id=chat_id, message_id=card_id, caption=caption, parse_mode="HTML", reply_markup=kb)
                    return
                except Exception:
                    pass
        elif not is_photo and not card_is_photo:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=card_id,
                    text=_cap(body, 4096) if body else channel_name,
                    parse_mode="HTML", reply_markup=kb,
                )
                return
            except Exception as e:
                logger.warning(f"edit_text failed: {e}")
        # Тип изменился (текст↔фото) — удаляем старую, шлём новую
        try:
            await bot.delete_message(chat_id=chat_id, message_id=card_id)
        except Exception:
            pass

    # Отправляем новую карточку
    if is_photo:
        sent = await bot.send_photo(
            chat_id=chat_id, photo=_photo(photo_paths[0]), caption=caption,
            reply_markup=kb, parse_mode="HTML", message_thread_id=_current_thread.get(),
        )
    else:
        sent = await bot.send_message(
            chat_id=chat_id, text=_cap(body, 4096) if body else channel_name,
            reply_markup=kb, parse_mode="HTML", message_thread_id=_current_thread.get(),
        )
    await state.update_data(card_message_id=sent.message_id, card_is_photo=is_photo, current_index=index)


async def _refresh_card(callback, state, index, new_body=None):
    """Перерисовать карточку после действия (рерайт/реклама и т.п.)."""
    await show_card(callback.message, state, index=index, edit=True)


# Защита от двойных кликов: блокировки по (chat_id, message_id)
_post_locks: Dict[str, asyncio.Lock] = {}


def _get_lock(callback) -> asyncio.Lock:
    key = f"{callback.message.chat.id}:{callback.message.message_id}"
    if key not in _post_locks:
        _post_locks[key] = asyncio.Lock()
    return _post_locks[key]


async def _set_status(callback, status_text: str):
    """Заменяет клавиатуру на статус-плашку «идёт обработка» (удаляемый статус)."""
    busy_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=status_text, callback_data="noop"),
    ]])
    try:
        await callback.message.edit_reply_markup(reply_markup=busy_kb)
    except Exception:
        pass


# ---------- callbacks ----------

async def _get_post_from_db(state, index: int):
    """Получить пост из БД по индексу в списке post_ids."""
    data = await state.get_data()
    post_ids = data.get("post_ids", [])
    if index < 0 or index >= len(post_ids):
        return None
    pid = post_ids[index]
    return db.get_parsed_post(pid)

@dp.callback_query(lambda c: c.data == "noop")
async def handle_noop(callback: types.CallbackQuery):
    await callback.answer()


async def _current_post(state):
    """Текущий пост (по current_index из state)."""
    data = await state.get_data()
    idx = data.get("current_index", 0)
    post = await _get_post_from_db(state, idx)
    return idx, post


# ---------- Навигация ⬅️ ➡️ ----------

@dp.callback_query(lambda c: c.data in ("nav_prev", "nav_next"))
async def handle_nav(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    total = len(data.get("post_ids", []))
    idx = data.get("current_index", 0)
    idx = idx + 1 if callback.data == "nav_next" else idx - 1
    idx = max(0, min(idx, total - 1))
    await state.update_data(current_index=idx)
    await show_card(callback.message, state, index=idx, edit=True)
    await callback.answer()


# ---------- Действия (работают с текущим постом) ----------

@dp.callback_query(lambda c: c.data == "act_rewrite")
async def handle_rewrite(callback: types.CallbackQuery, state: FSMContext):
    idx, post = await _current_post(state)
    if not post:
        await callback.answer("❌ Пост не найден")
        return
    lock = _get_lock(callback)
    if lock.locked():
        await callback.answer("⏳ Уже обрабатывается...")
        return
    async with lock:
        await callback.answer("📝 Рерайчу...")
        await _set_status(callback, "📝 Рерайчу... LLM думает")
        try:
            new_text = await rewrite_news(post["text"])
            db.update_parsed_post(post["id"], new_text, photo_path=post.get("photo_path"))
            await show_card(callback.message, state, index=idx, edit=True)
        except Exception as e:
            logger.error(f"Rewrite error: {e}")
            await show_card(callback.message, state, index=idx, edit=True)
            await callback.answer("❌ Ошибка рерайта", show_alert=True)


@dp.callback_query(lambda c: c.data == "act_rewrite_custom")
async def handle_rewrite_custom(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = data.get("current_index", 0)
    await state.set_state(RewriteState.waiting_prompt)
    await state.update_data(rewrite_index=idx)
    await send_with_topic(callback.message.chat.id, "✍️ Введи свой промпт для рерайта:")
    await callback.answer()


@dp.message(RewriteState.waiting_prompt)
async def handle_rewrite_input(message: Message, state: FSMContext):
    prompt = message.text
    data = await state.get_data()
    idx = data.get("rewrite_index", 0)
    post = await _get_post_from_db(state, idx)
    await state.set_state(None)
    if not post:
        await send_error(message.chat.id, "Пост не найден")
        return
    await send_with_topic(message.chat.id, "📝 Рерайчу по запросу...")
    try:
        new_text = await rewrite_news(post["text"], custom_prompt=prompt)
        db.update_parsed_post(post["id"], new_text, photo_path=post.get("photo_path"))
        # Перерисуем карточку
        await show_card(message, state, index=idx, edit=True)
    except Exception as e:
        logger.error(f"Rewrite custom error: {e}")
        await send_error(message.chat.id, f"{e}")


@dp.callback_query(lambda c: c.data == "act_translate")
async def handle_translate(callback: types.CallbackQuery, state: FSMContext):
    idx, post = await _current_post(state)
    if not post:
        await callback.answer("❌ Пост не найден")
        return
    lock = _get_lock(callback)
    if lock.locked():
        await callback.answer("⏳ Уже обрабатывается...")
        return
    async with lock:
        await callback.answer("🌐 Перевожу...")
        await _set_status(callback, "🌐 Перевожу... LLM думает")
        try:
            base_text = post["text"] if post.get("showing_original") else (post.get("edited_text") or post["text"])
            translated = await translate_text(base_text)
            db.update_parsed_post(post["id"], translated, photo_path=post.get("photo_path"))
            await show_card(callback.message, state, index=idx, edit=True)
        except Exception as e:
            logger.error(f"Translate error: {e}")
            await show_card(callback.message, state, index=idx, edit=True)
            await callback.answer("❌ Ошибка перевода", show_alert=True)


@dp.callback_query(lambda c: c.data == "act_ad")
async def handle_ad(callback: types.CallbackQuery, state: FSMContext):
    idx, post = await _current_post(state)
    if not post:
        await callback.answer("❌ Пост не найден")
        return
    lock = _get_lock(callback)
    if lock.locked():
        await callback.answer("⏳ Уже обрабатывается...")
        return
    async with lock:
        await callback.answer("🎯 Добавляю рекламу...")
        await _set_status(callback, "🎯 Интегрирую рекламу... LLM думает")
        try:
            base_text = post["text"] if post.get("showing_original") else (post.get("edited_text") or post["text"])
            new_text = await add_ad(base_text)
            db.update_parsed_post(post["id"], new_text, photo_path=post.get("photo_path"))
            await show_card(callback.message, state, index=idx, edit=True)
        except Exception as e:
            logger.error(f"Ad error: {e}")
            await show_card(callback.message, state, index=idx, edit=True)
            await callback.answer("❌ Ошибка рекламы", show_alert=True)


@dp.callback_query(lambda c: c.data == "act_orig")
async def handle_original(callback: types.CallbackQuery, state: FSMContext):
    """Свитч между оригиналом и отредактированной версией."""
    idx, post = await _current_post(state)
    if not post:
        await callback.answer("❌ Пост не найден")
        return
    edited = post.get("edited_text")
    if not edited:
        await callback.answer("Пост ещё не редактировался")
        return
    new_showing = not post.get("showing_original", False)
    # Сохраняем флаг
    with db._connect() as conn:
        conn.execute("UPDATE parsed_posts SET showing_original = ? WHERE id = ?",
                     (1 if new_showing else 0, post["id"]))
    await callback.answer("📄 Оригинал" if new_showing else "↩️ Отредактированная версия")
    await show_card(callback.message, state, index=idx, edit=True)


@dp.callback_query(lambda c: c.data == "act_photo")
async def handle_regenerate_photo(callback: types.CallbackQuery, state: FSMContext):
    idx, post = await _current_post(state)
    if not post:
        await callback.answer("❌ Пост не найден")
        return
    if not post.get("photo_path"):
        await callback.answer("❌ У поста нет фото")
        return
    lock = _get_lock(callback)
    if lock.locked():
        await callback.answer("⏳ Уже обрабатывается...")
        return
    async with lock:
        await callback.answer("🖼 Перегенерирую фото...")
        await _set_status(callback, "🖼 Генерирую изображение... (~30 сек)")
        try:
            image_prompt = db.get_setting("image_prompt")
            new_photo = await regenerate_photo(post["photo_path"], image_prompt)
            db.update_parsed_post(post["id"], post.get("edited_text") or post["text"], photo_path=new_photo)
            await show_card(callback.message, state, index=idx, edit=True)
        except Exception as e:
            logger.error(f"Regen photo error: {e}")
            await show_card(callback.message, state, index=idx, edit=True)
            await callback.answer("❌ Ошибка генерации фото", show_alert=True)


@dp.callback_query(lambda c: c.data == "act_publish")
async def handle_publish(callback: types.CallbackQuery, state: FSMContext):
    idx, post = await _current_post(state)
    if not post:
        await callback.answer("❌ Пост не найден")
        return
    await callback.answer("✅ Добавлено в очередь!")
    if post.get("showing_original"):
        final_text = post["text"]
    else:
        final_text = post.get("edited_text") or post["text"]
    post_id = enqueue_post(final_text, post.get("photo_path"), post.get("source_channel", ""), post["msg_id"])
    await send_with_topic(
        callback.message.chat.id,
        f"📝 Пост #{post_id} добавлен в очередь.\nНажмите «📤 Опубликовать» в меню для отправки во все топики.",
    )



async def do_publish(message: Message):
    """Общая логика публикации — вызывается из команды и из меню."""
    pending = get_pending_posts()
    if not pending:
        await send_error(message.chat.id, "📭 Очередь пуста. Используйте /parse для загрузки постов.")
        return

    published_count = 0
    for post in pending:
        try:
            await send_with_topic(message.chat.id, f"📤 Публикую #{post['id']}...")
            for topic in TOPICS:
                await post_via_bot(
                    post["text"],
                    post.get("photo_path"),
                    chat_id=str(topic["chat_id"]),
                    topic_id=topic["topic_id"]
                )
            mark_published(post["id"])
            await send_with_topic(message.chat.id, f"✅ Пост #{post['id']} опубликован!")
            published_count += 1
        except Exception as e:
            logger.error(f"Publish error: {e}")
            mark_failed(post["id"], str(e))
            await send_with_topic(message.chat.id, f"❌ Ошибка поста #{post['id']}: {e}")

    if published_count:
        await send_with_topic(message.chat.id, f"🎉 Опубликовано {published_count} постов.")
    else:
        await send_with_topic(message.chat.id, "⚠️ Публикации завершены с ошибками.")


@dp.message(Command("publish"))
async def cmd_publish(message: Message):
    await do_publish(message)



# ---------- watch ----------

@dp.message(Command("watch"))
async def cmd_watch(message: Message):
    chat_id = str(message.chat.id)
    if chat_id in active_watches:
        await send_with_topic(message.chat.id, "⏺ Мониторинг уже активен.")
        return

    active_watches[chat_id] = True
    await send_with_topic(message.chat.id, "👁 Включаю мониторинг новых постов...")
    asyncio.create_task(watch_loop(chat_id))


@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    chat_id = str(message.chat.id)
    if chat_id in active_watches:
        del active_watches[chat_id]
        await send_with_topic(message.chat.id, "🛑 Мониторинг остановлен.")
    else:
        await send_with_topic(message.chat.id, "📭 Мониторинг не был активен.")


# ---------- MENU CALLBACK HANDLERS (inline) ----------

@dp.callback_query(F.data == "menu_main")
async def cb_menu_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cb_send(callback, "🏠 Главное меню:", reply_markup=main_menu_kb())
    await callback.answer()


@dp.callback_query(F.data == "menu_parse")
async def cb_menu_parse(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ParseState.waiting_count)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="5", callback_data="parse_n_5"),
            InlineKeyboardButton(text="10", callback_data="parse_n_10"),
            InlineKeyboardButton(text="20", callback_data="parse_n_20"),
        ],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="menu_main")],
    ])
    await cb_send(callback, 
        "Сколько последних постов спарсить? Выберите или отправьте число:",
        reply_markup=kb,
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("parse_n_"))
async def cb_parse_n(callback: types.CallbackQuery, state: FSMContext):
    count = int(callback.data.split("_")[-1])
    await state.clear()
    await callback.answer(f"🔍 Парсю {count} постов...")
    await cb_send(callback, f"🔍 Парсю последние {count} постов...")
    await do_parse(callback.message, state, count=count)


@dp.message(ParseState.waiting_count)
async def menu_parse_count(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
    except (ValueError, AttributeError):
        await send_with_topic(message.chat.id, "Введите число, например 10.")
        return
    await state.clear()
    await send_with_topic(message.chat.id, f"🔍 Парсю последние {count} постов...")
    await do_parse(message, state, count=count)


@dp.callback_query(F.data == "menu_publish")
async def cb_menu_publish(callback: types.CallbackQuery):
    await callback.answer("📤 Публикую...")
    await do_publish(callback.message)


@dp.callback_query(F.data == "menu_help")
async def cb_menu_help(callback: types.CallbackQuery):
    await cb_send(callback, 
        "📋 Как пользоваться:\n\n"
        "1️⃣ «Управление каналами» → добавьте каналы для парсинга\n"
        "2️⃣ «Настройки» → настройте контекст проекта и промпты\n"
        "3️⃣ «Парсить посты» → выберите количество постов\n"
        "4️⃣ Под каждым постом кнопки:\n"
        "   • Рерайт — переписать по контексту проекта\n"
        "   • Рерайт промт — переписать по вашему запросу\n"
        "   • 🎯 Рекламный текст — добавить интеграцию проекта\n"
        "   • Перевести — перевести на английский\n"
        "   • Перегенерировать фото — улучшить изображение\n"
        "   • Опубликовать — добавить в очередь\n"
        "5️⃣ «Опубликовать» → публикация во все топики",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


# ---------- settings (inline) ----------

@dp.callback_query(F.data == "menu_settings")
async def cb_menu_settings(callback: types.CallbackQuery):
    channels = db.get_channels()
    ch_text = ", ".join(f"@{c}" for c in channels) if channels else "нет"
    topics_text = "\n".join(f"  • chat={t['chat_id']}, topic={t['topic_id']}" for t in TOPICS)
    await cb_send(callback, 
        f"⚙️ Настройки:\n\n"
        f"📚 Каналы: {ch_text}\n"
        f"📍 Топики публикации:\n{topics_text}\n"
        f"📅 Дней назад: {PARSE_DAYS}\n"
        f"⏱ Задержка постинга: {POST_DELAY_MIN}-{POST_DELAY_MAX} мин\n\n"
        f"Ниже — настройка AI-промптов:",
        reply_markup=settings_menu_kb(),
    )
    await callback.answer()


# Маппинг callback → ключ в БД + читаемое имя
_SETTING_KEYS = {
    "settings_project_context": ("project_context", "📄 Контекст проекта"),
    "settings_rewrite_prompt": ("rewrite_prompt", "📝 Промпт рерайта"),
    "settings_ad_prompt": ("ad_prompt", "🎯 Промпт рекламы"),
    "settings_image_prompt": ("image_prompt", "🖼 Промпт изображений"),
}


@dp.callback_query(F.data.in_(list(_SETTING_KEYS.keys())))
async def cb_edit_setting(callback: types.CallbackQuery, state: FSMContext):
    key, name = _SETTING_KEYS[callback.data]
    current = db.get_setting(key)
    await state.set_state(SettingsState.waiting_value)
    await state.update_data(setting_key=key)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Настройки", callback_data="menu_settings")],
    ])
    await cb_send(callback, 
        f"Текущее значение «{name}»:\n\n{current}\n\n"
        f"✍️ Отправьте новый текст, чтобы заменить:",
        reply_markup=kb,
    )
    await callback.answer()


@dp.message(SettingsState.waiting_value)
async def menu_save_setting(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("setting_key")
    db.set_setting(key, message.text)
    await state.clear()
    await send_with_topic(message.chat.id, "✅ Сохранено!", reply_markup=settings_menu_kb())


@dp.callback_query(F.data == "settings_show_all")
async def cb_show_settings(callback: types.CallbackQuery):
    s = db.get_all_settings()
    await cb_send(callback, 
        f"📄 КОНТЕКСТ ПРОЕКТА:\n{s['project_context']}\n\n"
        f"📝 ПРОМПТ РЕРАЙТА:\n{s['rewrite_prompt']}\n\n"
        f"🎯 ПРОМПТ РЕКЛАМЫ:\n{s['ad_prompt']}\n\n"
        f"🖼 ПРОМПТ ИЗОБРАЖЕНИЙ:\n{s['image_prompt']}",
        reply_markup=settings_menu_kb(),
    )
    await callback.answer()


# ---------- channels (inline) ----------

@dp.callback_query(F.data == "menu_channels")
async def cb_menu_channels(callback: types.CallbackQuery):
    await cb_send(callback, "📚 Управление каналами:", reply_markup=channels_menu_kb())
    await callback.answer()


@dp.callback_query(F.data == "channels_list")
async def cb_channels_list(callback: types.CallbackQuery):
    channels = db.get_channels()
    if not channels:
        await cb_send(callback, "📭 Список пуст. Нажмите «Добавить канал».", reply_markup=channels_menu_kb())
    else:
        text = "📚 Каналы для парсинга:\n" + "\n".join(f"• @{ch}" for ch in channels)
        await cb_send(callback, text, reply_markup=channels_menu_kb())
    await callback.answer()


@dp.callback_query(F.data == "channels_add")
async def cb_channels_add(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ChannelState.waiting_add)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Управление каналами", callback_data="menu_channels")],
    ])
    await cb_send(callback, 
        "Отправьте @username канала (можно несколько через пробел):",
        reply_markup=kb,
    )
    await callback.answer()


@dp.message(ChannelState.waiting_add)
async def menu_channels_add_input(message: Message, state: FSMContext):
    added = []
    for token in (message.text or "").split():
        username = token.strip().lstrip("@")
        if username:
            db.add_channel(username)
            added.append(username)
    await state.clear()
    txt = "✅ Добавлено: " + ", ".join(f"@{u}" for u in added) if added else "❌ Не распознал канал."
    await send_with_topic(message.chat.id, txt, reply_markup=channels_menu_kb())


@dp.callback_query(F.data == "channels_del")
async def cb_channels_del(callback: types.CallbackQuery, state: FSMContext):
    channels = db.get_channels()
    if not channels:
        await cb_send(callback, "📭 Список пуст.", reply_markup=channels_menu_kb())
        await callback.answer()
        return
    rows = [[InlineKeyboardButton(text=f"➖ @{ch}", callback_data=f"delch_{ch}")] for ch in channels]
    rows.append([InlineKeyboardButton(text="🔙 Управление каналами", callback_data="menu_channels")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await cb_send(callback, "Выберите канал для удаления:", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("delch_"))
async def cb_del_channel(callback: types.CallbackQuery):
    username = callback.data[len("delch_"):]
    db.remove_channel(username)
    await callback.answer(f"✅ @{username} удалён")
    await cb_send(callback, f"✅ Канал @{username} удалён", reply_markup=channels_menu_kb())


async def watch_loop(chat_id: str):
    """Постоянный мониторинг новых постов."""
    parser = TGParser(phone=TELEPHONE)
    await parser.start()
    last_ids: set = set()

    try:
        while active_watches.get(chat_id):
            try:
                posts = await parser.fetch_with_photos(since_days=1)
                new_posts = [p for p in posts if p.get("msg_id") not in last_ids]

                if new_posts:
                    last_ids.update(p.get("msg_id", 0) for p in new_posts)
                    await send_with_topic(int(chat_id), f"📬 Найдено {len(new_posts)} новых постов!")
                    # Сохраняем для просмотра
                    # Примечание: FSM-состояние для другого чата — это workaround,
                    # лучше бы использовать отдельное хранилище.
                    # Для watch_loop достаточно уведомления, а не показа.
            except Exception as e:
                logger.error(f"Watch error: {e}")

            await asyncio.sleep(300)
    finally:
        await parser.close()


async def main():
    """Запуск бота."""
    logger.info("🚀 Запускаю TG Publisher бота...")
    db.init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
