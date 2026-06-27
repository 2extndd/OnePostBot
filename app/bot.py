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
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramForbiddenError

from .config import (
    BOT_TOKEN, TOPIC_ID, CHAT_ID, TOPICS,
    PARSE_CHANNELS, PARSE_DAYS,
    POST_DELAY_MIN, POST_DELAY_MAX,
    TELEPHONE,
)
from .parser import TGParser
from .text_regen import regenerate_text, generate_caption_for_photo
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


# ---------- helpers ----------

async def send_with_topic(chat_id: int, text: str, reply_markup=None):
    """Отправить сообщение в тему."""
    try:
        kwargs = {"chat_id": chat_id, "text": text}
        if TOPIC_ID:
            kwargs["message_thread_id"] = TOPIC_ID
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        await bot.send_message(**kwargs)
    except TelegramForbiddenError as e:
        logger.error(f"TelegramForbiddenError: {e}")
        await bot.send_message(chat_id=chat_id, text=f"❌ Ошибка доступа: проверьте права бота в канале")


async def send_error(chat_id: int, text: str):
    """Отправить ошибку и ответить на коллбек, если есть."""
    await send_with_topic(chat_id, f"❌ {text}")


# ---------- commands ----------

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/parse 10"), KeyboardButton(text="/parse 20")],
            [KeyboardButton(text="/publish"), KeyboardButton(text="/watch")],
            [KeyboardButton(text="/help")],
        ],
        resize_keyboard=True,
    )
    await send_with_topic(
        message.chat.id,
        "🤖 TG Publisher бот активен!\n\n"
        "📋 Команды:\n"
        "/parse N — показать последние N постов\n"
        "/parse @channel N — парсить конкретный канал\n\n"
        "При показе постов доступны кнопки:\n"
        "• Рерайт — переписать текст (на английском)\n"
        "• Рерайт промт — переписать с твоим промптом\n"
        "• Перевести — перевести на английский\n"
        "• Перегенерировать фото — улучшить изображение\n"
        "• Опубликовать — добавить в очередь\n\n"
        "/publish — опубликовать одобренные посты\n"
        "/watch — включить мониторинг новых постов\n"
        "/stop — остановить мониторинг\n"
        "/help — справка",
        reply_markup=kb,
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

    parser = TGParser(phone=TELEPHONE)
    await parser.start()

    try:
        if channel:
            channels = [channel]
        else:
            # Берём каналы из БД, fallback на конфиг
            db_channels = db.get_channels()
            channels = db_channels if db_channels else PARSE_CHANNELS
        if not channels:
            await send_error(message.chat.id, "Нет каналов для парсинга. Добавьте через /addchannel @канал")
            return

        posts = await parser.fetch_with_photos(channels=channels, since_days=PARSE_DAYS)

        if not posts:
            await send_error(message.chat.id, "Нет новых постов за последние дни.")
            return

        # Сохраняем посты в состояние
        await state.update_data(posts=posts, channel=channel)
        await show_post(parser, posts, message, state, index=0)

    except Exception as e:
        logger.error(f"Parse error: {e}\n{traceback.format_exc()}")
        await send_error(message.chat.id, f"{e}")
    finally:
        await parser.close()


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

async def show_post(parser: TGParser, posts: List[Dict], message: Message, state: FSMContext, index: int = 0):
    """Показать один пост с кнопками."""
    if index >= len(posts):
        await send_with_topic(message.chat.id, "✅ Все посты просмотрены.")
        return

    if index < 0:
        index = 0

    post = posts[index]
    text_preview = post["text"][:200] + ("..." if len(post["text"]) > 200 else "")
    channel_name = post.get("channel", post.get("channel_username", "unknown"))
    msg_id = post.get("msg_id", "?")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"prev_{index}"),
                InlineKeyboardButton(text=f"{index+1}/{len(posts)}", callback_data="noop"),
                InlineKeyboardButton(text="➡️ Далее", callback_data=f"next_{index}"),
            ],
            [InlineKeyboardButton(text="📝 Рерайт", callback_data=f"rewrite_{index}")],
            [InlineKeyboardButton(text="✍️ Рерайт промт", callback_data=f"rewrite_custom_{index}")],
            [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{index}")],
            [InlineKeyboardButton(text="🖼 Перегенерировать фото", callback_data=f"regen_photo_{index}")],
            [InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"publish_{index}")],
        ],
    )

    caption = f"📰 [{channel_name}]\n\n{text_preview}\n\n🆔 ID: {msg_id}\n📅 {post.get('date', '')}"
    if post.get("photo_path"):
        await message.answer_photo(photo=post["photo_path"], caption=caption, reply_markup=kb)
    else:
        await send_with_topic(message.chat.id, caption, reply_markup=kb)


# ---------- callbacks ----------

@dp.callback_query(lambda c: c.data in ("noop",))
async def handle_noop(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith(("prev_", "next_")))
async def handle_nav(callback: types.CallbackQuery, state: FSMContext):
    action, idx_str = callback.data.split("_", 1)
    try:
        index = int(idx_str)
    except ValueError:
        await callback.answer("❌ Ошибка")
        return

    state_data = await state.get_data()
    posts = state_data.get("posts", [])
    if not posts:
        await callback.answer("❌ Нет постов")
        return

    if action == "prev":
        index = max(0, index - 1)
    elif action == "next":
        index = min(len(posts) - 1, index + 1)

    await show_post(None, posts, callback.message, state, index)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("rewrite_") and not c.data.startswith("rewrite_custom_"))
async def handle_rewrite(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[-1])
    state_data = await state.get_data()
    posts = state_data.get("posts", [])
    if index >= len(posts):
        await callback.answer("❌ Пост не найден")
        return

    await callback.answer("🔄 Переписываю...")
    try:
        post = posts[index]
        new_text = regenerate_text(post["text"], "Переведи и перепиши на английский")
        caption = f"✅ Рерайт (EN):\n\n{new_text}"
        if post.get("photo_path"):
            await callback.message.answer_photo(photo=post["photo_path"], caption=caption)
        else:
            await send_with_topic(callback.message.chat.id, caption)
    except Exception as e:
        logger.error(f"Rewrite error: {e}")
        await callback.answer(f"❌ Ошибка: {e}")
        await send_error(callback.message.chat.id, f"{e}")


@dp.callback_query(lambda c: c.data.startswith("rewrite_custom_"))
async def handle_rewrite_custom(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[-1])
    await state.set_state(RewriteState.waiting_prompt)
    await state.update_data(rewrite_index=index)
    await send_with_topic(callback.message.chat.id, "✍️ Введи свой промпт для рерайта:")
    await callback.answer()


@dp.message(RewriteState.waiting_prompt)
async def handle_rewrite_input(message: Message, state: FSMContext):
    prompt = message.text
    data = await state.get_data()
    index = data.get("rewrite_index")
    state_data = await state.get_data()
    posts = state_data.get("posts", [])

    if index >= len(posts):
        await state.clear()
        await send_error(message.chat.id, "Пост не найден")
        return

    await send_with_topic(message.chat.id, "🔄 Переписываю...")
    try:
        post = posts[index]
        new_text = regenerate_text(post["text"], prompt)
        caption = f"✅ Рерайт:\n\n{prompt}\n\n{new_text}"
        if post.get("photo_path"):
            await message.answer_photo(photo=post["photo_path"], caption=caption)
        else:
            await send_with_topic(message.chat.id, caption)
    except Exception as e:
        logger.error(f"Rewrite custom error: {e}")
        await send_error(message.chat.id, f"{e}")

    await state.clear()


@dp.callback_query(lambda c: c.data.startswith("translate_"))
async def handle_translate(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[-1])
    state_data = await state.get_data()
    posts = state_data.get("posts", [])
    if index >= len(posts):
        await callback.answer("❌ Пост не найден")
        return

    await callback.answer("🔄 Перевожу...")
    try:
        post = posts[index]
        translated = regenerate_text(post["text"], "Переведи на английский язык. Сохрани смысл.")
        caption = f"✅ Перевод (EN):\n\n{translated}"
        if post.get("photo_path"):
            await callback.message.answer_photo(photo=post["photo_path"], caption=caption)
        else:
            await send_with_topic(callback.message.chat.id, caption)
    except Exception as e:
        logger.error(f"Translate error: {e}")
        await callback.answer(f"❌ Ошибка: {e}")
        await send_error(callback.message.chat.id, f"{e}")


@dp.callback_query(lambda c: c.data.startswith("regen_photo_"))
async def handle_regenerate_photo(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[-1])
    state_data = await state.get_data()
    posts = state_data.get("posts", [])
    if index >= len(posts):
        await callback.answer("❌ Пост не найден")
        return

    post = posts[index]
    if not post.get("photo_path"):
        await callback.answer("❌ У поста нет фото")
        return

    await callback.answer("🖼 Перегенерирую...")
    try:
        new_photo = regenerate_photo(post["photo_path"], "Улучши качество, сделай ярче и контрастнее")
        caption = f"✅ Фото переработано!\n\n{post['text'][:200]}"
        await callback.message.answer_photo(photo=new_photo, caption=caption)
    except Exception as e:
        logger.error(f"Regen photo error: {e}")
        await callback.answer(f"❌ Ошибка: {e}")
        await send_error(callback.message.chat.id, f"{e}")


@dp.callback_query(lambda c: c.data.startswith("publish_"))
async def handle_publish(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[-1])
    state_data = await state.get_data()
    posts = state_data.get("posts", [])
    if index >= len(posts):
        await callback.answer("❌ Пост не найден")
        return

    await callback.answer("✅ Добавлено в очередь!")
    post = posts[index]

    # Регенерируем текст
    new_text = regenerate_text(post["text"], "Переписываем пост для публикации")

    post_id = enqueue_post(new_text, post.get("photo_path"), post.get("channel", ""), post["msg_id"])

    await send_with_topic(
        callback.message.chat.id,
        f"📝 Пост #{post_id} добавлен в очередь.\n\n"
        f"Нажмите /publish чтобы опубликовать одобренные посты.",
    )


@dp.message(Command("publish"))
async def cmd_publish(message: Message):
    pending = get_pending_posts()
    if not pending:
        await send_error(message.chat.id, "Очередь пуста. Нет постов для публикации.")
        return

    approved_count = 0
    for post in pending:
        await send_with_topic(message.chat.id, f"📤 Публикую #{post['id']}: {post['text'][:100]}...")
        delay = random.randint(POST_DELAY_MIN, POST_DELAY_MAX)
        await asyncio.sleep(delay * 60)

        try:
            # Публикуем во все топики из TOPICS
            for topic in TOPICS:
                await post_via_bot(
                    post["text"],
                    post.get("photo_path"),
                    chat_id=str(topic["chat_id"]),
                    topic_id=topic["topic_id"]
                )
            mark_published(post["id"])
            await send_with_topic(message.chat.id, f"✅ Пост #{post['id']} опубликован во все топики!")
            approved_count += 1
        except Exception as e:
            logger.error(f"Publish error: {e}")
            mark_failed(post["id"], str(e))
            await send_with_topic(message.chat.id, f"❌ Ошибка поста #{post['id']}: {e}")

    if approved_count:
        await send_with_topic(message.chat.id, f"🎉 Опубликовано {approved_count} постов.")
    else:
        await send_with_topic(message.chat.id, "⚠️ Публикации завершены с ошибками.")


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
