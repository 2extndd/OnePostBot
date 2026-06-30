# GSD context snapshot (2026-06-30T01:36:47.211Z)

## Top project memories
- [MEM005] (gotcha) Telethon session auth in Docker: interactive login (code input) won't work without stdin. Session must be authorized beforehand (via _auth.py or interactive script), then the .session file placed in data/.
- [MEM006] (gotcha) aiogram 3.x InlineKeyboardButton/KeyboardButton require keyword args (text=..., callback_data=...). Positional args like InlineKeyboardButton("text", callback_data=...) throw TypeError.
- [MEM007] (gotcha) Dokploy .env files can have concatenated lines without newline separators (e.g., "DOCKER_CONFIG=/root/.dockerTELEGRAM_API_ID=..."). Always verify .env with cat -A.
- [MEM010] (gotcha) OnePostBot: Telethon session must be authorized while the bot container is STOPPED. If the QR-auth web server and the bot run simultaneously, they both open the same SQLite session file (data/tg_session.session) and conflict — the bot recreates it empty, losing authorization. Correct flow: docker stop bot → run QR auth → verify is_user_authorized=True → docker compose up bot.
- [MEM011] (gotcha) aiogram 3.x: sending a parsed/local photo must use FSInputFile(path), not the raw path string — otherwise Telegram API returns 'Bad Request: invalid file HTTP URL specified: URL host is empty' because aiogram treats bare strings as URLs/file_ids.
- [MEM001] (architecture) Заменить файловую очередь постов на SQLite Chose: SQLite вместо JSON файлов. Rationale: JSON файлы ненадёжны при конкурентном доступе, нет транзакций и сложных запросов. SQLite обеспечивает ACID, индексы, встроенность..
