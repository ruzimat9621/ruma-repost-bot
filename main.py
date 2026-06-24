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

    async def send_single_message(message):
        original_text = message.message or ""
        caption = build_caption(original_text)

        log(f"SENDING SINGLE. has_media={bool(message.media)}, text_len={len(original_text)}")

        if message.media:
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    file_path = await client.download_media(message, file=tmpdir)

                    log(f"DOWNLOADED MEDIA PATH: {file_path}")

                    if not file_path:
                        await client.send_message(TARGET_CHAT, caption)
                        log("MEDIA DOWNLOAD EMPTY. SENT CAPTION ONLY.")
                        return

                    if len(caption) <= 1024:
                        await client.send_file(
                            TARGET_CHAT,
                            file_path,
                            caption=caption,
                            force_document=False
                        )
                    else:
                        await client.send_file(
                            TARGET_CHAT,
                            file_path,
                            force_document=False
                        )
                        await client.send_message(TARGET_CHAT, caption)

                    log("MEDIA SENT SUCCESSFULLY.")

            except Exception as e:
                log(f"MEDIA ERROR: {repr(e)}")
                await client.send_message(
                    TARGET_CHAT,
                    f"{caption}\n\n⚠️ Media repost bo‘lmadi. Sabab: {str(e)}"
                )
        else:
            await client.send_message(TARGET_CHAT, caption)
            log("TEXT SENT SUCCESSFULLY.")

    async def send_album(event):
        messages = event.messages
        first_text = ""

        for msg in messages:
            if msg.message:
                first_text = msg.message
                break

        caption = build_caption(first_text)

        log(f"ALBUM DETECTED. count={len(messages)}, caption_len={len(caption)}")

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                files = []

                for msg in messages:
                    if msg.media:
                        file_path = await client.download_media(msg, file=tmpdir)
                        if file_path:
                            files.append(file_path)
                            log(f"ALBUM FILE DOWNLOADED: {file_path}")

                if files:
                    if len(caption) <= 1024:
                        await client.send_file(
                            TARGET_CHAT,
                            files,
                            caption=caption,
                            force_document=False
                        )
                    else:
                        await client.send_file(
                            TARGET_CHAT,
                            files,
                            force_document=False
                        )
                        await client.send_message(TARGET_CHAT, caption)

                    log("ALBUM SENT SUCCESSFULLY.")
                else:
                    await client.send_message(TARGET_CHAT, caption)
                    log("ALBUM FILES EMPTY. SENT CAPTION ONLY.")

        except Exception as e:
            log(f"ALBUM ERROR: {repr(e)}")
            await client.send_message(
                TARGET_CHAT,
                f"{caption}\n\n⚠️ Album repost bo‘lmadi. Sabab: {str(e)}"
            )

    @client.on(events.Album(chats=SOURCE_CHATS))
    async def album_handler(event):
        try:
            if event.out:
                log("SKIPPED OUTGOING ALBUM.")
                return

            log(f"SOURCE ALBUM DETECTED. chat_id={event.chat_id}")
            await send_album(event)

        except Exception as e:
            log(f"ERROR while album reposting: {repr(e)}")

    @client.on(events.NewMessage(chats=SOURCE_CHATS))
    async def repost_handler(event):
        try:
            message = event.message

            if event.out:
                log(f"SKIPPED OUTGOING MESSAGE. chat_id={event.chat_id}, message_id={message.id}")
                return

            if message.grouped_id:
                log(f"SKIPPED GROUPED MESSAGE. grouped_id={message.grouped_id}")
                return

            log(f"SOURCE MESSAGE DETECTED. chat_id={event.chat_id}, message_id={message.id}")

            await send_single_message(message)

            log(f"REPOSTED SUCCESSFULLY. message_id={message.id}")

        except Exception as e:
            log(f"ERROR while reposting: {repr(e)}")

    await start_web_server()
    await client.start()

    me = await client.get_me()
    log(f"Telegram session logged in as: {me.first_name} / id={me.id}")
    log("Ruma repost bot started.")
    log(f"Source chats: {SOURCE_CHATS}")
    log(f"Target chat: {TARGET_CHAT}")

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
