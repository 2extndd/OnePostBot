"""
Основной скрипт — запускает Telegram бота.
"""

import sys
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

from .bot import main as bot_main


async def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python main.py bot        # Запустить Telegram бота")
        print("  python main.py parse      # Только распарсить")
        print("  python main.py publish    # Опубликовать очередь")
        print("  python main.py run        # Полный цикл")
        return

    cmd = sys.argv[1]

    from . import db
    db.init_db()

    if cmd == "bot":
        await bot_main()
    elif cmd == "parse":
        from .parser import TGParser
        from .config import TELEPHONE
        parser = TGParser(phone=TELEPHONE)
        await parser.start()
        try:
            posts = await parser.fetch_with_photos()
            print(f"📊 Найдено {len(posts)} постов")
            for i, post in enumerate(posts[:5]):
                print(f"  {i+1}. [{post['channel']}] {post['text'][:80]}...")
        finally:
            await parser.close()
    elif cmd == "publish":
        from .scheduler import get_pending_posts, mark_published, mark_failed
        from .publisher import publish_post
        pending = get_pending_posts()
        print(f"📤 Публикую {len(pending)} постов...")
        for post in pending:
            try:
                await publish_post(post["text"], post.get("photo_path"))
                mark_published(post["id"])
            except Exception as e:
                mark_failed(post["id"], str(e))
                print(f"❌ Ошибка поста #{post['id']}: {e}")
    elif cmd == "run":
        from .parser import TGParser
        from .config import TELEPHONE
        parser = TGParser(phone=TELEPHONE)
        await parser.start()
        try:
            posts = await parser.fetch_with_photos()
            print(f"📊 Найдено {len(posts)} постов")
        finally:
            await parser.close()
    else:
        print(f"❌ Неизвестная команда: {cmd}")


if __name__ == "__main__":
    asyncio.run(main())
