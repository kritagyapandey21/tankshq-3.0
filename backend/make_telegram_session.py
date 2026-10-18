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

import re
import sys


def ask_api_id() -> int:
    raw = input("API ID (the short number from my.telegram.org, NOT your phone number): ").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= 2**31 - 1) or len(raw) > 9:
        sys.exit("That is not an API ID. API IDs are 5-9 digits (for example 39100979). "
                 "A phone number goes in later, when it asks for your phone.")
    return int(raw)


def ask_api_hash() -> str:
    raw = input("API hash (32 letters and numbers): ").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{32}", raw):
        sys.exit("That is not an API hash. It is exactly 32 characters (0-9 and a-f), shown on my.telegram.org/apps.")
    return raw


api_id = ask_api_id()
api_hash = ask_api_hash()
print("\nNext it asks for your PHONE (with the country code, e.g. +91...), then the code Telegram sends you,\n"
      "then your two-step password if you have one (nothing shows on screen while you type it).\n"
      "If the password is wrong 3 times Telegram blocks logins for an hour or more, so check it first.\n")

with TelegramClient(StringSession(), api_id, api_hash) as client:   # asks for phone, code and 2FA password
    me = client.get_me()
    print(f"\nLogged in as: {me.first_name} (@{me.username or 'no username'})")
    print("\nPut these three lines in backend/.env:\n")
    print(f"TELEGRAM_API_ID={api_id}")
    print(f"TELEGRAM_API_HASH={api_hash}")
    print(f"TELEGRAM_SESSION_STRING={client.session.save()}")
    print("\nKeep them secret. Do not commit .env.")
