import os, asyncio
from telethon import TelegramClient

# Загружаем .env
for line in open('.env'):
    line=line.strip()
    if '=' in line and not line.startswith('#'):
        k,v=line.split('=',1)
        os.environ[k]=v

api_id = int(os.environ['TELEGRAM_API_ID'])
api_hash = os.environ['TELEGRAM_API_HASH']
phone = os.environ['TELEPHONE']

async def main():
    client = TelegramClient('/app/data/tg_session', api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        result = await client.send_code_request(phone)
        print('CODE_SENT phone_code_hash=' + result.phone_code_hash)
    else:
        me = await client.get_me()
        print('ALREADY_AUTH:', me.username or me.first_name)
    await client.disconnect()

asyncio.run(main())
