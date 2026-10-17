"""Create a Telegram session string for TELEGRAM_SESSION_STRING in backend/.env.

Run it on your OWN computer (not on the server):

    cd backend
    venv\\Scripts\\python.exe make_telegram_session.py        (Windows)
    venv/bin/python make_telegram_session.py                 (Mac / Linux)

It asks for your API ID and API hash (from https://my.telegram.org/apps), then logs in as the Telegram
account that is allowed to message AffiliatePocketBot (phone number, the code Telegram sends you, and your
two-step password if you have one). It prints a long string: paste that into .env and keep it secret.
A session string gives full access to that Telegram account, so never commit it or share it.
"""

from telethon.sessions import StringSession
from telethon.sync import TelegramClient

api_id = int(input("API ID (numbers only): ").strip())
api_hash = input("API hash: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:   # asks for phone, code and 2FA password
    me = client.get_me()
    print(f"\nLogged in as: {me.first_name} (@{me.username or 'no username'})")
    print("\nPut these three lines in backend/.env:\n")
    print(f"TELEGRAM_API_ID={api_id}")
    print(f"TELEGRAM_API_HASH={api_hash}")
    print(f"TELEGRAM_SESSION_STRING={client.session.save()}")
    print("\nKeep them secret. Do not commit .env.")
