# OnePostBot — Telegram Auto-Publisher

Система автоматической публикации контента для Telegram-каналов. Автоматически парсит посты из исходных каналов, позволяет рерайтить/переводить/улучшать контент через AI, и публиковать в целевой канал с ручным подтверждением.

## Архитектура

```
┌──────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Source TG     │    │  OnePostBot     │    │  Target TG      │
│ Channels      │───▶│  (Telegram Bot) │───▶│  Channel        │
│ (@claudedev)  │    │                 │    │  (TBD)          │
└──────────────┘    │                 │    └─────────────────┘
                    │  ┌───────────┐  │
                    │  │ AI Layer  │  │
                    │  │ Anthropic │  │
                    │  │ OpenAI    │  │
                    │  └───────────┘  │
                    └─────────────────┘
```

## Модули

- **`bot.py`** — Telegram Bot API (aiogram 3.x): команды `/parse`, `/publish`, `/watch`, `/stop`, `/config`, `/help` + inline-кнопки для каждого поста
- **`parser.py`** — парсинг Telegram-каналов через Telethon: скачивает посты с медиа, сохраняет фото в `data/media/`
- **`text_regen.py`** — рерайт/перевод текста через Anthropic (Claude)
- **`image_regen.py`** — улучшение/генерация изображений через OpenAI (GPT Image)
- **`publisher.py`** — публикация в целевой канал через Bot API
- **`scheduler.py`** — очередь постов (SQLite: pending → approved → published)
- **`db.py`** — SQLite-слой: dedup обработанных сообщений + очередь публикаций
- **`config.py`** — конфигурация из `.env`
- **`notifier.py`** — отправка уведомлений в тему (aiohttp)

## Команды бота

| Команда | Описание |
|---------|----------|
| `/parse N` | Показать последние N постов |
| `/parse @channel N` | Парсить конкретный канал |
| `/publish` | Опубликовать одобренные посты |
| `/watch` | Включить мониторинг новых постов |
| `/stop` | Остановить мониторинг |
| `/config` | Текущие настройки |
| `/help` | Справка |

## Жизненный цикл поста

```
спарсен → pending → approved → published
         ↓          ↓
      failed    published
```

Каждый пост хранится в SQLite с метаданными: текст, фото, источник, статус, время.

## Деплой

**Сервер:** `138.124.50.27` (root)
**Путь проекта:** `/etc/dokploy/compose/onepostbot-stack-7gdtph/code/`
**Имя контейнера:** `onepostbot-stack-7gdtph-tg-publisher-1`

### Установка

```bash
cd /etc/dokploy/compose/onepostbot-stack-7gdtph/code
# .env уже настроен (проверить после авторизации)
docker compose up -d --build
```

### Логи

```bash
docker logs -f onepostbot-stack-7gdtph-tg-publisher-1
```

## Конфигурация (.env)

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен бота от @BotFather |
| `TELEGRAM_API_ID` | API ID для Telethon (парсинг) |
| `TELEGRAM_API_HASH` | API Hash для Telethon |
| `TELEPHONE` | Номер телефона для авторизации Telethon |
| `PARSE_CHANNELS` | Каналы для парсинга (через запятую) |
| `TARGET_CHANNEL` | Целевой канал для публикации |
| `ANTHROPIC_API_KEY` | Ключ для рерайта текста |
| `OPENAI_API_KEY` | Ключ для генерации фото |

## Данные

- `data/queue/` — очередь постов (JSON файлы, legacy)
- `data/media/` — скачанные медиа
- `data/tg_session.session` — Telethon-сессия
- `data/processed.db` — SQLite (dedup + очередь)

## Известные ограничения

1. **Telethon авторизация** — сессия должна быть авторизована заранее (через `_auth.py` или скрипт авторизации). Без этого `/parse` выдаёт ошибку.
2. **TARGET_CHANNEL** — сейчас пустой, нужно указать перед публикацией.
3. **Watch mode** — уведомления приходят в тот же чат, откуда отправлена команда `/watch`. Просмотр постов в watch-loop не поддерживается.
4. **Один поток парсинга** — парсинг синхронный, блокирующий другие операции.
5. **Нет rate-limit** между публикациями — зависит от настроек `POST_DELAY_MIN/MAX`.

## Будущее развитие

- Интеграция с OneProvider.dev (контент из блога/новостей)
- Автопубликация без ручного подтверждения (через approve-кнопку)
- Мультиязычность (EN/RU)
- Статистика просмотров/кликов
- Планировщик публикаций (cron-style)
