# Decisions Register

<!-- Append-only. Never edit or remove existing rows.
     To reverse a decision, add a new row that supersedes it.
     Read this file at the start of any planning or research phase. -->

| # | When | Scope | Decision | Choice | Rationale | Revisable? | Made By |
|---|------|-------|----------|--------|-----------|------------|---------|
| D001 | M001/S03 | architecture | Заменить файловую очередь постов на SQLite | SQLite вместо JSON файлов | JSON файлы ненадёжны при конкурентном доступе, нет транзакций и сложных запросов. SQLite обеспечивает ACID, индексы, встроенность. | Yes | agent |
| D002 | M001 | feature | Режим работы — ручное подтверждение перед публикацией | Ручное подтверждение оператором | Оператор контролирует контент. Автопилот будет в M003. | Yes | agent |
| D003 | M001 | architecture | Telethon user session для парсинга, Bot API для публикации | Telegram user session для парсинга, Bot API для публикации | Bot API надёжнее для постинга (не банится за чат). Telethon нужен для чтения каналов. Авторизация Telethon — заранее, не в Docker. | Yes | agent |
| D004 | M001 | compatibility | aiogram 3.x — все KeyboardButton/InlineKeyboardButton с именованными аргументами | Именованные аргументы aiogram 3.x | aiogram 3.x падает на позиционных аргументах KeyboardButton(text, callback_data). | No | agent |
| D005 | M002 | architecture | Архитектура AI-промптов: 3 уровня (project_context, rewrite_prompt, ad_prompt) | Anthropic prompt caching через cache_control в system prompt | project_context передаётся в system prompt с cache_control ephemeral — Anthropic кэширует его, экономя ~90% токенов на повторных запросах к той же новости. Один вызов LLM вместо субагентов — проще и дешевле для текущего объёма. | Yes | agent |
| D006 | M002 | feature | Разделение кнопок "Рерайт" и "Рекламный текст" | Кнопка "Рекламный текст" не переписывает, а дополняет | Рерайт переосмысляет весь текст под контекст проекта. Рекламный текст работает поверх (берёт edited_text если есть) и только добавляет интеграцию с ссылкой, не трогая основной смысл. Это даёт оператору гибкость комбинировать. | Yes | agent |
| D007 | M001 | deployment | Секреты (API-ключи, токены) в Dockerfile ENV — Dokploy не перезапишет при деплое | Секреты в Dockerfile ENV | Dokploy при деплое перезаписывает .env из своей панели. ENV в Dockerfile — единственный способ защитить секреты от перезаписи. .dockerignore гарантирует, что .env не попадёт в git. | Yes | agent |
