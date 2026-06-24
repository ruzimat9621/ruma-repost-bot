import os
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

load_dotenv()

api_id = int(input("API_ID ni kiriting: ").strip())
api_hash = input("API_HASH ni kiriting: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\nQuyidagi SESSION_STRING ni to‘liq nusxa oling va xavfsiz joyda saqlang:\n")
    print(client.session.save())
