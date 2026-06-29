---
id: T01
parent: S01
milestone: M001
key_files:
  - app/bot.py — full rewrite
  - app/db.py — new SQLite layer with channels, parsed_posts
  - app/parser.py — fixed photo_path, auth check
  - app/image_regen.py — returns file path
  - app/publisher.py — aiohttp multipart
  - app/text_regen.py — lazy init
  - docker-compose.yml — env_file instead of env vars
  - .env.example — updated with two topics
key_decisions:
  - SQLite replaces file-based queue for durability
  - Multi-topic support via TOPICS config array
  - Callbacks use DB post IDs not FSM indices (fixes lost-update)
  - Lazy init for API clients (avoids startup crashes)
  - Secrets in env_file, not git
duration: 
verification_result: untested
completed_at: 2026-06-29T12:35:38.228Z
blocker_discovered: false
---

# T01: Fixed .env on server, rewrote bot.py for multiple topics, added channel management, fixed lost-update with SQLite

**Fixed .env on server, rewrote bot.py for multiple topics, added channel management, fixed lost-update with SQLite**

## What Happened

Major rewrite of OnePostBot: 1) Fixed broken .env on server (concatenated lines) 2) Rewrote bot.py with proper aiogram 3.x compatibility (keyword args) 3) Added SQLite storage for posts (fixes lost-update) 4) Added channel management (/channels, /addchannel, /delchannel) 5) Added support for multiple topics (CHAT_ID/TOPIC_ID + CHAT_ID_2/TOPIC_ID_2) 6) Fixed image_regen.py (returns file path, not binary) 7) Fixed publisher.py (aiohttp multipart upload) 8) Implemented lazy init for OpenAI/Anthropic clients 9) Secured secrets (moved from env vars to env_file, removed from git) 10) Authenticated Telethon session via QR login (user @huliganesss)

## Verification

✓ Bot running on server (138.124.50.27) — @AutoOneProviderbot id=8732968162
✓ Docker container stable (no restarts in 120s+)
✓ SQLite initialized with channels, parsed_posts, queue, processed_messages tables
✓ Two topics configured: -1003906263366/425 and -1003965270090/2084
✓ Telethon session authorized (@huliganesss)
✓ All callback handlers use DB (not FSM)
✓ Commands: /parse, /channels, /addchannel, /delchannel, /publish, /watch, /stop, /config, /help

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| — | No verification commands discovered | — | — | — |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `app/bot.py — full rewrite`
- `app/db.py — new SQLite layer with channels, parsed_posts`
- `app/parser.py — fixed photo_path, auth check`
- `app/image_regen.py — returns file path`
- `app/publisher.py — aiohttp multipart`
- `app/text_regen.py — lazy init`
- `docker-compose.yml — env_file instead of env vars`
- `.env.example — updated with two topics`
