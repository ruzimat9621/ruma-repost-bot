import os
import asyncio
import tempfile
from aiohttp import web
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

PORT = int(os.getenv("PORT", "8080"))


def log(text):
    print(text, flush=True)


def parse_chat(value: str):
    value = value.strip()
    if value.startswith("-100") or value.lstrip("-").isdigit():
        return int(value)
    return value


SOURCE_CHATS = [
    parse_chat(item)
    for item in SOURCE_CHATS_RAW.split(",")
    if item.strip()
]


def build_caption(original_text):
    original_text = (original_text or "").strip()

    if original_text:
        return f"{HEADER_TEXT}\n\n{original_text}\n\n{FOOTER_TEXT}"

    return f"{HEADER_TEXT}\n\n{FOOTER_TEXT}"


async def health(request):
    return web.Response(text="Ruma repost bot is running")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    log(f"Web server started on port {PORT}")
    return runner


async def main():
    if not API_ID or not API_HASH or not SESSION_STRING:
        log("ERROR: API_ID, API_HASH yoki SESSION_STRING kiritilmagan.")
        return

    if not SOURCE_CHATS:
        log("ERROR: SOURCE_CHATS empty. Source kanal CHAT_ID ni Environment Variables ga qo‘shing.")
        return

    client = TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH
    )

    async def send_repost(message):
        caption = build_caption(message.message)

        if message.media:
            with tempfile.TemporaryDirectory() as tmpdir:
                file_path = await message.download_media(file=tmpdir)

                if file_path:
                    if len(caption) <= 1000:
                        await client.send_file(
                            TARGET_CHAT,
                            file_path,
                            caption=caption
                        )
                    else:
                        await client.send_file(
                            TARGET_CHAT,
                            file_path
                        )
                        await client.send_message(
                            TARGET_CHAT,
                            caption
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

    @client.on(events.NewMessage())
    async def repost_handler(event):
        try:
            chat_id = event.chat_id
            message = event.message

            log(f"NEW MESSAGE DETECTED. chat_id={chat_id}, message_id={message.id}")

            if chat_id not in SOURCE_CHATS:
                log(f"SKIPPED. This chat_id is not in SOURCE_CHATS: {chat_id}")
                return

            log(f"MATCHED SOURCE CHAT. Reposting message_id={message.id}")

            await send_repost(message)

            log(f"REPOSTED SUCCESSFULLY. message_id={message.id}")

        except Exception as e:
            log(f"ERROR while reposting: {e}")

    await start_web_server()

    await client.start()

    me = await client.get_me()
    log(f"Telegram session logged in as: {me.first_name} / id={me.id}")
    log(f"Ruma repost bot started.")
    log(f"Source chats: {SOURCE_CHATS}")
    log(f"Target chat: {TARGET_CHAT}")

    try:
        await client.send_message(
            TARGET_CHAT,
            "✅ Ruma repost bot ishga tushdi. Test xabar."
        )
        log("TEST MESSAGE SENT TO TARGET CHANNEL.")
    except Exception as e:
        log(f"ERROR sending test message to target: {e}")

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
