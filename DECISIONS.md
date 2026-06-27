# OnePostBot — Decisions

## D001: Replace file-based queue with SQLite
- **Date:** 2026-06-27
- **Choice:** Использовать SQLite (db.py) вместо JSON файлов в data/queue/ для хранения очереди и dedup
- **Rationale:** JSON файлы — ненадёжно при одновременном доступе, нет транзакций, сложно искать. SQLite даёт ACID, индексы, JOIN.
- **Revisable:** Yes

## D002: Mode of operation — manual confirmation
- **Date:** 2026-06-27
- **Choice:** Ручное подтверждение оператором перед публикацией
- **Rationale:** Оператор хочет контролировать контент. Полная автономность будет в M003.
- **Revisable:** Yes

## D003: Target channel TBD
- **Date:** 2026-06-27
- **Choice:** TARGET_CHANNEL пока пустой, выбрать позже
- **Rationale:** Нужно обсудить какой именно канал использовать для OneProvider.
- **Revisable:** Yes

## D004: Telethon auth required
- **Date:** 2026-06-27
- **Choice:** Парсинг каналов требует предварительно авторизованной Telethon-сессии
- **Rationale:** Интерактивная авторизация не работает в Docker (нет stdin). Сессия должна быть создана до деплоя.
- **Revisable:** No — fundamental constraint of Docker environment.

## D005: Bot API for publishing, Telethon for parsing
- **Date:** 2026-06-27
- **Choice:** Публикация идёт через Bot API (BOT_TOKEN), парсинг — через Telethon user session
- **Rationale:** Bot API надёжнее для постинга (не блокируется за бан чата). Telethon нужен только для чтения.
- **Revisable:** Yes

## D006: aiogram 3.x positional → named arguments
- **Date:** 2026-06-27
- **Choice:** Все KeyboardButton и InlineKeyboardButton используют именованные аргументы (text=..., callback_data=...)
- **Rationale:** aiogram 3.x ломается на позиционных аргументах.
- **Revisable:** No — enforced by library.
