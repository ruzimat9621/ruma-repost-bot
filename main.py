import os
import asyncio
import tempfile
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")

SOURCE_CHATS_RAW = os.getenv("SOURCE_CHATS", "")
TARGET_CHAT = os.getenv("TARGET_CHAT", "@ruma_collection")

HEADER_TEXT = os.getenv("HEADER_TEXT", "Ruma Premium🩵")
FOOTER_TEXT = os.getenv("FOOTER_TEXT", "Zakaz berish uchun: @ruma_admin")

SOURCE_CHATS = [
    item.strip()
    for item in SOURCE_CHATS_RAW.split(",")
    if item.strip()
]


def build_caption(original_text: str | None) -> str:
    original_text = (original_text or "").strip()

    if original_text:
        return f"{HEADER_TEXT}\n\n{original_text}\n\n{FOOTER_TEXT}"

    return f"{HEADER_TEXT}\n\n{FOOTER_TEXT}"


client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH
)


@client.on(events.NewMessage(chats=SOURCE_CHATS))
async def repost_handler(event):
    try:
        message = event.message
        caption = build_caption(message.message)

        if message.media:
            with tempfile.TemporaryDirectory() as tmpdir:
                file_path = await message.download_media(file=tmpdir)

                if file_path:
                    await client.send_file(
                        TARGET_CHAT,
                        file_path,
                        caption=caption
                    )
                else:
                    await client.send_message(
                        TARGET_CHAT,
                        caption
                    )
        else:
            await client.send_message(
                TARGET_CHAT,
                caption
            )

        print(f"Reposted message ID: {message.id}")

    except Exception as e:
        print(f"Error while reposting: {e}")


async def main():
    print("Ruma repost bot started.")
    print("Source chats:", SOURCE_CHATS)
    print("Target chat:", TARGET_CHAT)
    await client.run_until_disconnected()


if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
