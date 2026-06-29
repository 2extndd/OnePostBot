# TG Publisher (OnePostBot) — Документация

## Архитектура

```
Source TG Channels  →  Telegram Parser (Telethon)  →  AI Layer  →  Publish Queue  →  Target Channels
(@claudedev)              (downloads photos)            (Claude + GPT)  (SQLite)            (2 topics)
```

## Модули

| Модуль | Назначение |
|--------|-----------|
| `app/bot.py` | Telegram Bot API (aiogram 3.x): команды + callback-хендлеры |
| `app/parser.py` | Парсинг каналов через Telethon, скачивание медиа |
| `app/text_regen.py` | Рерайт/перевод текста (Anthropic/Claude) |
| `app/image_regen.py` | Улучшение/генерация изображений (OpenAI/GPT Image) |
| `app/publisher.py` | Публикация в целевой канал (Bot API) |
| `app/scheduler.py` | Очередь публикаций (обёртка над db.py) |
| `app/db.py` | SQLite: dedup + очередь + каналы + посты + настройки |
| `app/config.py` | Конфигурация из .env |

## Команды бота

| Команда | Описание |
|---------|----------|
| `/parse N` | Последние N постов |
| `/parse @channel N` | Конкретный канал |
| `/channels` | Список каналов |
| `/addchannel @канал` | Добавить канал |
| `/delchannel @канал` | Удалить канал |
| `/publish` | Опубликовать одобренные посты |
| `/watch` | Мониторинг новых постов |
| `/stop` | Остановить мониторинг |
| `/config` | Настройки |
| `/help` | Справка |

## Кнопки под каждым постом

- **📝 Рерайт** — рерайт + перевод на английский (LLM)
- **✍️ Рерайт промт** — рерайт с вашим промптом
- **🌐 Перевести** — перевод на английский
- **🖼 Перегенерировать фото** — улучшение изображения (GPT Image)
- **✅ Опубликовать** — в очередь публикаций

## Жизненный цикл поста

```
спарсен → pending → approved → published
         ↓          ↓
      failed    опубликован
```

## Деплой

- **Сервер:** 138.124.50.27 (root)
- **Путь:** `/etc/dokploy/compose/onepostbot-stack-7gdtph/code/`
- **Контейнер:** `onepostbot-stack-7gdtph-tg-publisher-1`
- **Бот:** @AutoOneProviderbot (id=8732968162)
- **Запуск:** `python -m app.main bot`
- **Логи:** `docker logs onepostbot-stack-7gdtph-tg-publisher-1`

### Топики (2)

1. **Топик 1:** `CHAT_ID=-1003906263366`, `TOPIC_ID=425`
2. **Топик 2:** `CHAT_ID=-1003965270090`, `TOPIC_ID=2084`

Публикация идёт во **все** топики одновременно.

## Конфигурация

Все ключи встроены в **Dockerfile ENV** — Dokploy не перезапишет их при деплое.

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен бота от @BotFather |
| `TELEGRAM_API_ID` | API ID для Telethon |
| `TELEGRAM_API_HASH` | API Hash для Telethon |
| `TELEPHONE` | Номер для авторизации Telethon |
| `ANTHROPIC_API_KEY` | Ключ для рерайта (Claude) |
| `ANTHROPIC_BASE_URL` | Прокси OneProvider |
| `LLM_MODEL` | Модель Claude |
| `OPENAI_API_KEY` | Ключ для фото (GPT Image) |
| `OPENAI_BASE_URL` | Прокси cc-vibe |
| `IMAGE_MODEL` | Модель генерации фото |
| `TARGET_CHANNEL` | Целевой канал для публикации |
| `DATA_DIR` | Папка данных |

## SQLite структура

- `channels` — список каналов (@username)
- `parsed_posts` — все спарсенные посты (текст, фото, edited_text, showing_original)
- `queue` — очередь публикаций (pending/approved/published/failed)
- `processed_messages` — dedup (чтобы не парсить дважды)
- `settings` — настройки (image_prompt и т.д.)

## Безопасность

- `.env` в `.gitignore` — не попадает в git
- Секреты в `Dockerfile ENV` — Dokploy не перезапишет при деплое
- `.dockerignore` — исключает `.env` из образа
