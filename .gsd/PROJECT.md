# TG Publisher — Summary

## Что сделано

### Баги исправлены (8+)
1. `.env` на сервере — склеенные строки `DOCKER_CONFIG`/`TELEGRAM_API_ID` → разделены
2. `EOFError` при `/parse` — Telethon пытался интерактивно вводить код в Docker
3. aiogram 3.x — все `InlineKeyboardButton`/`KeyboardButton` переделаны на именованные аргументы
4. `rewrite_` перехватывал `rewrite_custom_` → добавлен фильтр `not startswith("rewrite_custom_")`
5. `photo_url` vs `photo_path` между parser и bot → унифицировано на `photo_path`
6. `post_via_bot` — использовал `files=` из requests → переделан на `aiohttp.FormData()`
7. `regenerate_photo` — возвращал невалидные данные → теперь возвращает путь к файлу
8. Файловая очередь → SQLite с транзакциями и индексами
9. Telegram-токен устарел → заменён на новый

### Новые возможности
- **Управление каналами:** `/channels`, `/addchannel @канал`, `/delchannel @канал`
- **Многотопиковость:** поддержка двух топиков (CHAT_ID/TOPIC_ID + CHAT_ID_2/TOPIC_ID_2)
- **Посты в БД:** все посты хранятся в `parsed_posts` таблице (фиксит lost-update)
- **Ленивая инициализация API-клиентов** — не падает при отсутствии ключей
- **Альбомы фото:** multi-photo posts через `send_media_group`

### Архитектурные изменения
- Новый модуль `db.py` — SQLite слой (channels, parsed_posts, queue, processed_messages, settings)
- `docker-compose.yml` использует `env_file` — секреты не в git
- `.env` добавлен в `.gitignore`
- Callback-хендлеры теперь берут посты из БД по id

### Деплой
- Сервер: 138.124.50.27
- Путь: /etc/dokploy/compose/onepostbot-stack-7gdtph/code/
- Контейнер: onepostbot-stack-7gdtph-tg-publisher-1
- Бот: @AutoOneProviderbot (id=8732968162)
- Токен: 8732968162:AAHedj6mb2jUMlogz5HLtKpN2aDqCEZdDEM

### Команды бота
- `/parse N` — парсинг последних N постов
- `/parse @channel N` — парсинг конкретного канала
- `/channels` — список каналов
- `/addchannel @канал` — добавить канал
- `/delchannel @канал` — удалить канал
- `/publish` — опубликовать одобренные посты
- `/watch` — мониторинг новых постов
- `/stop` — остановить мониторинг
- `/config` — текущие настройки
- `/help` — справка

### Кнопки под каждым постом
- ⬅️ Назад / ➡️ Далее (навигация)
- 📝 Рерайт (рерайт + перевод на английский)
- ✍️ Рерайт промт (своим промптом)
- 🌐 Перевести
- 🖼 Перегенерировать фото
- ✅ Опубликовать

## Открытые вопросы
- API ключи для LLM (ANTHROPIC_API_KEY, OPENAI_API_KEY) — placeholder'ы
- TARGET_CHANNEL установлен на @onecodebase (-1003944526531)
- Dokploy может перезаписывать .env при деплое — нужно настроить через UI или env_file mount