# M001: Fix bot deployment

**Vision:** Привести OnePostBot к стабильному рабочему состоянию на сервере: исправить сломанный .env, Telethon-авторизацию, баги aiogram 3.x, заменить файловую очередь на SQLite, исправить все сломанные callback-хендлеры.

## Slices

- [x] **S01: S01** `risk:low` `depends:[]`
  > After this: Контейнер запускается без ошибок

- [ ] **S02: Rewrite bot.py callbacks** `risk:medium` `depends:[]`
  > After this: Все callback-кнопки работают

- [ ] **S03: Replace file queue with SQLite** `risk:medium` `depends:[]`
  > After this: enqueue/get_pending/mark_processed работают

- [ ] **S04: Fix image_regen and publisher** `risk:medium` `depends:[]`
  > After this: regenerate_photo и post_via_bot работают

- [ ] **S05: Fix parser.py** `risk:low` `depends:[]`
  > After this: fetch_with_photos работает, скачивает медиа

- [ ] **S06: Authorize Telethon session** `risk:high` `depends:[S05]`
  > After this: Парсинг каналов работает (/parse)

## Boundary Map

Not provided.
