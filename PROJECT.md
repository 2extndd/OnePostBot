# OnePostBot — Project Overview

## Milestone Sequence

- [x] M001: Fix bot deployment — fix .env, Telethon auth, code bugs, multi-topic support
- [ ] M002: Full OneProvider integration — connect to OneProvider API, auto-publish blog/news content
- [ ] M003: Automation features — cron scheduling, approval workflow, analytics

## What it is

OnePostBot (внутреннее имя «TG Publisher») — система автоматического ведения Telegram-каналов. Парсит контент из исходных каналов, перерабатывает его через AI (рерайт, перевод, улучшение изображений) и публикует в целевой канал с ручным подтверждением оператора.

Предназначен для ведения контент-канала, связанного с проектом **OneProvider.dev** (платформа продажи LLM API-ключей).

## Core surfaces

- **Telegram Bot** (`@AutoOneProviderbot`) — основной интерфейс управления через команды и inline-кнопки
- **Telethon parser** — пользовательский аккаунт читает исходные каналы (требует авторизации сессии)
- **AI layer** — Anthropic (Claude) для текста, OpenAI-совместимый (cc-vibe, GPT Image) для изображений

## Tech stack

- **Язык:** Python 3.13
- **Bot framework:** aiogram 3.x (Bot API)
- **Парсинг:** Telethon 1.44+ (MTProto / user session)
- **AI:** anthropic SDK (через OneProvider proxy), openai SDK (через cc-vibe)
- **Хранилище:** SQLite (`data/processed.db`) — dedup + очередь публикаций
- **Деплой:** Docker Compose через Dokploy на VPS

## Deployment

- **Сервер:** `138.124.50.27` (root)
- **Путь:** `/etc/dokploy/compose/onepostbot-stack-7gdtph/code/`
- **Контейнер:** `onepostbot-stack-7gdtph-tg-publisher-1`
- **Запуск:** `python -m app.main bot`
- **Ресурсы:** 512MB RAM, 1 CPU (лимит)

## Module map

| Модуль | Ответственность |
|--------|-----------------|
| `app/bot.py` | Команды бота, callback-хендлеры, watch-loop |
| `app/parser.py` | Парсинг каналов через Telethon, скачивание медиа |
| `app/text_regen.py` | Рерайт/перевод текста (Claude) |
| `app/image_regen.py` | Улучшение/генерация изображений (GPT Image) |
| `app/publisher.py` | Публикация в целевой канал (Bot API / Telethon) |
| `app/scheduler.py` | Очередь публикаций (обёртка над db.py) |
| `app/db.py` | SQLite: dedup + очередь |
| `app/config.py` | Конфигурация из .env |
| `app/notifier.py` | Уведомления в тему топика |

## Post lifecycle

```
parsed → pending → approved → published
                 ↘ failed
```

## Current state (2026-06-27)

**Исправлено в этой сессии:**
- Сломанный `.env` на сервере (склеенные строки `DOCKER_CONFIG`/`TELEGRAM_API_ID`)
- `EOFError` при `/parse` — Telethon пытался интерактивно вводить код в Docker без stdin
- aiogram 3.x несовместимость — позиционные аргументы в `InlineKeyboardButton`/`KeyboardButton`
- Перехват `rewrite_custom_` хендлером `rewrite_`
- Несоответствие `photo_url` vs `photo_path` между parser и bot
- Файловая очередь заменена на SQLite с корректным жизненным циклом
- `post_via_bot` использовал requests-синтаксис в aiohttp (падал на отправке фото)
- `regenerate_photo` возвращал невалидные данные вместо пути к файлу

**Открытые вопросы:**
- Telethon-сессия не авторизована (блокирует парсинг) — требуется код подтверждения
- `TARGET_CHANNEL` пустой — целевой канал ещё не выбран
- Режим работы: ручное подтверждение перед публикацией (выбрано оператором)
