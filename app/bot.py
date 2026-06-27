"""
Telegram Bot — основной интерфейс управления.
Команды: /parse N, /publish, /watch, /stop, /help
"""

import logging
import asyncio
import random
import traceback
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramForbiddenError

from .config import (
    BOT_TOKEN, TOPIC_ID, CHAT_ID,
    PARSE_CHANNELS, PARSE_DAYS,
    POST_DELAY_MIN, POST_DELAY_MAX,
    TELEPHONE,
)
from .parser import TGParser
from .text_regen import regenerate_text, generate_caption_for_photo
from .image_regen import regenerate_photo
from .publisher import post_via_bot
from .scheduler import enqueue_post, get_pending_posts, mark_processed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Глобальное состояние
active_watches = {}  # chat_id -> True


class RewriteState(StatesGroup):
    waiting_prompt = State()


async def send_with_topic(chat_id: str, text: str, reply_markup=None):
    """Отправить сообщение в топик."""
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


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("/parse 10"), KeyboardButton("/parse 20")],
            [KeyboardButton("/publish"), KeyboardButton("/watch")],
            [KeyboardButton("/help")],
        ],
        resize_keyboard=True,
    )
    await send_with_topic(
        message.chat.id,
        "🤖 TG Publisher бот активен!\n\n"
        "📋 Команды:\n"
        "/parse N — показать последние N постов\n"
        "/parse @channel N — парсить конкретный канал\n"
        "/publish — опубликовать выбранный пост\n"
        "/watch — включить мониторинг\n"
        "/stop — остановить мониторинг\n"
        "/help — справка",
        reply_markup=kb,
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await send_with_topic(
        message.chat.id,
        "📋 Команды бота:\n\n"
        "/parse N — показать последние N постов\n"
        "/parse @channel N — парсить конкретный канал\n\n"
        "При показе постов доступны кнопки:\n"
        "• Рерайт — переписать текст (на английском)\n"
        "• Рерайт промт — переписать с твоим промптом\n"
        "• Перевести — перевести на английский\n"
        "• Перегенерировать фото — улучшить изображение\n"
        "• Опубликовать — отправить в целевой канал\n\n"
        "/publish — опубликовать выбранный пост\n"
        "/watch — включить мониторинг новых постов\n"
        "/stop — остановить мониторинг\n"
        "/config — текущие настройки",
    )


@dp.message(Command("parse"))
async def cmd_parse(message: types.Message, state: FSMContext):
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
        channels = [channel] if channel else PARSE_CHANNELS
        if not channels:
            await send_with_topic(message.chat.id, "❌ Нет каналов для парсинга. Укажите канал или добавьте в config.")
            return

        posts = await parser.fetch_with_photos(channels=channels, since_days=PARSE_DAYS)

        if not posts:
            await send_with_topic(message.chat.id, "📭 Нет новых постов за последние дни.")
            return

        # Показываем посты по одному
        await show_post(parser, posts, message, state, index=0)

    except Exception as e:
        logger.error(f"Parse error: {e}\n{traceback.format_exc()}")
        await send_with_topic(message.chat.id, f"❌ Ошибка парсинга: {e}")
    finally:
        await parser.close()


async def show_post(parser, posts, message, state, index=0):
    """Показать один пост с кнопками."""
    if index >= len(posts):
        await send_with_topic(message.chat.id, "✅ Все посты просмотрены.")
        return

    post = posts[index]
    text_preview = post["text"][:200] + ("..." if len(post["text"]) > 200 else "")
    channel_name = post.get("channel", post.get("channel_username", "unknown"))

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton("⬅️ Назад", callback_data=f"post_prev_{index}"),
                InlineKeyboardButton(f"{index+1}/{len(posts)}", callback_data="noop"),
                InlineKeyboardButton("➡️ Далее", callback_data=f"post_next_{index}"),
            ],
            [InlineKeyboardButton("📝 Рерайт", callback_data=f"rewrite_{index}")],
            [InlineKeyboardButton("✍️ Рерайт промт", callback_data=f"rewrite_custom_{index}")],
            [InlineKeyboardButton("🌐 Перевести", callback_data=f"translate_{index}")],
            [InlineKeyboardButton("🖼 Перегенерировать фото", callback_data=f"regen_photo_{index}")],
            [InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_{index}")],
        ],
    )

    caption = f"📰 [{channel_name}]\n\n{text_preview}\n\n🆔 ID: {post['msg_id']}\n📅 {post['date']}"
    if post.get("photo_url"):
        await message.answer_photo(photo=post["photo_url"], caption=caption, reply_markup=kb)
    else:
        await send_with_topic(message.chat.id, caption, reply_markup=kb)

    # Сохраняем состояние
    await state.update_data(posts=posts, channel_parser=parser)


@dp.callback_query(lambda c: c.data.startswith(("post_prev_", "post_next_", "rewrite_", "rewrite_custom_", "translate_", "regen_photo_", "publish_")))
async def handle_callback(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    parts = data.rsplit("_", 1)
    action = parts[0]
    try:
        index = int(parts[1])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка")
        return

    state_data = await state.get_data()
    posts = state_data.get("posts", [])
    parser = state_data.get("channel_parser")

    if not posts:
        await callback.answer("❌ Нет постов")
        return

    if action == "post_prev":
        await show_post(parser, posts, callback.message, state, index=index)
    elif action == "post_next":
        await show_post(parser, posts, callback.message, state, index=index)

    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("rewrite_"))
async def handle_rewrite(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[-1])
    state_data = await state.get_data()
    posts = state_data.get("posts", [])
    if index >= len(posts):
        await callback.answer("❌ Пост не найден")
        return

    post = posts[index]
    text = post["text"]

    # Рерайт на английском
    new_text = regenerate_text(text, f"Переведи и перепиши на английский")
    caption = f"✅ Рерайт (EN):\n\n{new_text}"

    if post.get("photo_url"):
        await callback.message.answer_photo(photo=post["photo_url"], caption=caption)
    else:
        await send_with_topic(callback.message.chat.id, caption)

    # Предлагаем опубликовать
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_{index}"),
        InlineKeyboardButton("📋 К списку", callback_data=f"post_next_{index}"),
    ]])
    await send_with_topic(callback.message.chat.id, "Хочешь опубликовать этот вариант?", reply_markup=kb)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("rewrite_custom_"))
async def handle_rewrite_custom(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[-1])
    await state.set_state(RewriteState.waiting_prompt)
    await state.update_data(rewrite_index=index)
    await send_with_topic(callback.message.chat.id, "✍️ Введи свой промпт для рерайта:")
    await callback.answer()


@dp.message(RewriteState.waiting_prompt)
async def handle_rewrite_input(message: types.Message, state: FSMContext):
    prompt = message.text
    data = await state.get_data()
    index = data.get("rewrite_index")
    state_data = await state.get_data()
    posts = state_data.get("posts", [])

    if index >= len(posts):
        await state.clear()
        await message.reply("❌ Пост не найден")
        return

    post = posts[index]
    text = post["text"]
    new_text = regenerate_text(text, prompt)
    caption = f"✅ Рерайт:\n\n{prompt}\n\n{new_text}"

    if post.get("photo_url"):
        await message.answer_photo(photo=post["photo_url"], caption=caption)
    else:
        await send_with_topic(message.chat.id, caption)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_{index}"),
        InlineKeyboardButton("📋 К списку", callback_data=f"post_next_{index}"),
    ]])
    await send_with_topic(message.chat.id, "Хочешь опубликовать?", reply_markup=kb)
    await state.clear()


@dp.callback_query(lambda c: c.data.startswith("translate_"))
async def handle_translate(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[-1])
    state_data = await state.get_data()
    posts = state_data.get("posts", [])
    if index >= len(posts):
        await callback.answer("❌ Пост не найден")
        return

    post = posts[index]
    text = post["text"]
    translated = regenerate_text(text, "Переведи на английский язык. Сохрани смысл.")
    caption = f"✅ Перевод (EN):\n\n{translated}"

    if post.get("photo_url"):
        await callback.message.answer_photo(photo=post["photo_url"], caption=caption)
    else:
        await send_with_topic(callback.message.chat.id, caption)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_{index}"),
    ]])
    await send_with_topic(callback.message.chat.id, "Опубликовать?", reply_markup=kb)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("regen_photo_"))
async def handle_regenerate_photo(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[-1])
    state_data = await state.get_data()
    posts = state_data.get("posts", [])
    if index >= len(posts):
        await callback.answer("❌ Пост не найден")
        return

    post = posts[index]
    if not post.get("photo_url"):
        await callback.answer("❌ У поста нет фото")
        return

    await callback.answer("🖼 Перегенерирую...")

    try:
        new_photo = regenerate_photo(post["photo_url"], "Улучши качество, сделай ярче и контрастнее")
        caption = f"✅ Фото переработано!\n\n{post['text'][:200]}"
        await callback.message.answer_photo(photo=new_photo, caption=caption)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}")
        logger.error(f"Regen photo error: {e}")

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_{index}"),
    ]])
    await send_with_topic(callback.message.chat.id, "Опубликовать?", reply_markup=kb)


@dp.callback_query(lambda c: c.data.startswith("publish_"))
async def handle_publish(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[-1])
    state_data = await state.get_data()
    posts = state_data.get("posts", [])
    if index >= len(posts):
        await callback.answer("❌ Пост не найден")
        return

    post = posts[index]
    await callback.answer("✅ Добавлено в очередь!")

    # Регенерируем текст
    new_text = regenerate_text(post["text"], "Переписываем пост для публикации")

    enqueue_post(new_text, post.get("photo_url"), post.get("channel", ""), post["msg_id"])

    # Публикуем
    delay = random.randint(POST_DELAY_MIN, POST_DELAY_MAX)
    await callback.message.answer(f"📤 Публикую через {delay} мин...")

    try:
        await post_via_bot(new_text, post.get("photo_url"))
        await callback.message.answer("✅ Опубликовано!")
        mark_processed("")  # Очистка очереди
    except Exception as e:
        logger.error(f"Publish error: {e}")
        await callback.message.answer(f"❌ Ошибка публикации: {e}")

    await callback.answer()


@dp.message(Command("publish"))
async def cmd_publish(message: types.Message):
    pending = get_pending_posts()
    if not pending:
        await send_with_topic(message.chat.id, "📭 Очередь пуста.")
        return

    for i, post in enumerate(pending):
        await send_with_topic(message.chat.id, f"📤 Публикую #{i+1}: {post['text'][:100]}...")
        delay = random.randint(POST_DELAY_MIN, POST_DELAY_MAX)
        await asyncio.sleep(delay * 60)
        try:
            await post_via_bot(post["text"], post.get("photo_path"))
            mark_processed(post["_filepath"])
            await send_with_topic(message.chat.id, "✅ Опубликовано!")
        except Exception as e:
            logger.error(f"Publish error: {e}")
            await send_with_topic(message.chat.id, f"❌ Ошибка: {e}")


@dp.message(Command("watch"))
async def cmd_watch(message: types.Message):
    chat_id = str(message.chat.id)
    if chat_id in active_watches:
        await send_with_topic(message.chat.id, "⏺ Мониторинг уже активен.")
        return

    active_watches[chat_id] = True
    await send_with_topic(message.chat.id, "👁 Включаю мониторинг новых постов...")
    asyncio.create_task(watch_loop(chat_id))


@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
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
    last_ids = set()

    try:
        while active_watches.get(chat_id):
            try:
                posts = await parser.fetch_with_photos(since_days=1)
                new_posts = [p for p in posts if p["msg_id"] not in last_ids]

                if new_posts:
                    last_ids.update(p["msg_id"] for p in new_posts)
                    await send_with_topic(chat_id, f"📬 Найдено {len(new_posts)} новых постов!")
                    # Сохраняем для просмотра
                    await state.update_data(posts=posts)
                    await show_post(parser, new_posts, None, state, index=0)
            except Exception as e:
                logger.error(f"Watch error: {e}")

            await asyncio.sleep(300)
    finally:
        await parser.close()


@dp.message(Command("config"))
async def cmd_config(message: types.Message):
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


async def main():
    """Запуск бота."""
    logger.info("🚀 Запускаю TG Publisher бота...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
