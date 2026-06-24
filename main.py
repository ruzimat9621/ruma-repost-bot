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

processed_albums = set()


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
        log("ERROR: SOURCE_CHATS empty.")
        return

    client = TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH
    )

    async def send_caption_separately(caption):
        if caption:
            await client.send_message(TARGET_CHAT, caption)
            log("CAPTION SENT SEPARATELY.")

    async def send_media_message(message, caption):
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                file_path = await client.download_media(message, file=tmpdir)

                log(f"DOWNLOADED MEDIA: {file_path}")

                if not file_path:
                    await send_caption_separately(caption)
                    return

                is_sticker = bool(getattr(message, "sticker", None))
                is_voice = bool(getattr(message, "voice", None))
                is_video_note = bool(getattr(message, "video_note", None))

                if is_sticker:
                    await client.send_file(TARGET_CHAT, file_path)
                    await send_caption_separately(caption)
                    log("STICKER SENT.")
                    return

                if is_voice:
                    await client.send_file(TARGET_CHAT, file_path, voice_note=True)
                    await send_caption_separately(caption)
                    log("VOICE SENT.")
                    return

                if is_video_note:
                    await client.send_file(TARGET_CHAT, file_path, video_note=True)
                    await send_caption_separately(caption)
                    log("ROUND VIDEO SENT.")
                    return

                if len(caption) <= 1024:
                    await client.send_file(
                        TARGET_CHAT,
                        file_path,
                        caption=caption,
                        force_document=False,
                        supports_streaming=True
                    )
                    log("MEDIA/FILE SENT WITH CAPTION.")
                else:
                    await client.send_file(
                        TARGET_CHAT,
                        file_path,
                        force_document=False,
                        supports_streaming=True
                    )
                    await send_caption_separately(caption)
                    log("MEDIA/FILE SENT, CAPTION SEPARATE.")

        except Exception as e:
            log(f"MEDIA SEND ERROR: {repr(e)}")

            try:
                await client.forward_messages(TARGET_CHAT, message)
                await send_caption_separately(caption)
                log("FALLBACK FORWARD SENT.")
            except Exception as e2:
                log(f"FALLBACK ERROR: {repr(e2)}")
                await client.send_message(
                    TARGET_CHAT,
                    f"{caption}\n\n⚠️ Media/fayl repost bo‘lmadi. Xato: {str(e2)}"
                )

    async def send_single_message(message):
        original_text = message.message or ""
        caption = build_caption(original_text)

        log(
            f"SINGLE DETECTED. message_id={message.id}, "
            f"has_media={bool(message.media)}, text_len={len(original_text)}"
        )

        if message.media:
            await send_media_message(message, caption)
        else:
            await client.send_message(TARGET_CHAT, caption)
            log("TEXT SENT.")

    async def send_album(event):
        messages = event.messages or []

        if not messages:
            log("EMPTY ALBUM SKIPPED.")
            return

        grouped_id = messages[0].grouped_id

        if grouped_id in processed_albums:
            log(f"DUPLICATE ALBUM SKIPPED: {grouped_id}")
            return

        processed_albums.add(grouped_id)

        first_text = ""
        for msg in messages:
            if msg.message:
                first_text = msg.message
                break

        caption = build_caption(first_text)

        log(f"ALBUM DETECTED. grouped_id={grouped_id}, count={len(messages)}")

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                files = []
                special_messages = []

                for msg in messages:
                    if not msg.media:
                        continue

                    is_sticker = bool(getattr(msg, "sticker", None))
                    is_voice = bool(getattr(msg, "voice", None))
                    is_video_note = bool(getattr(msg, "video_note", None))

                    if is_sticker or is_voice or is_video_note:
                        special_messages.append(msg)
                        continue

                    try:
                        file_path = await client.download_media(msg, file=tmpdir)
                        if file_path:
                            files.append(file_path)
                            log(f"ALBUM FILE DOWNLOADED: {file_path}")
                    except Exception as e:
                        log(f"ALBUM DOWNLOAD ERROR: {repr(e)}")
                        special_messages.append(msg)

                caption_sent = False

                if files:
                    try:
                        if len(caption) <= 1024:
                            await client.send_file(
                                TARGET_CHAT,
                                files,
                                caption=caption,
                                force_document=False,
                                supports_streaming=True
                            )
                            caption_sent = True
                        else:
                            await client.send_file(
                                TARGET_CHAT,
                                files,
                                force_document=False,
                                supports_streaming=True
                            )

                        log("ALBUM FILES SENT.")

                    except Exception as e:
                        log(f"ALBUM SEND ERROR: {repr(e)}")

                        for file_path in files:
                            await client.send_file(
                                TARGET_CHAT,
                                file_path,
                                force_document=False,
                                supports_streaming=True
                            )

                        log("ALBUM SENT ONE BY ONE.")

                for msg in special_messages:
                    await send_media_message(msg, "")

                if not caption_sent:
                    await send_caption_separately(caption)

        except Exception as e:
            log(f"ALBUM GENERAL ERROR: {repr(e)}")
            await client.send_message(
                TARGET_CHAT,
                f"{caption}\n\n⚠️ Album repost bo‘lmadi. Xato: {str(e)}"
            )

    @client.on(events.Album(chats=SOURCE_CHATS))
    async def album_handler(event):
        try:
            messages = event.messages or []

            if not messages:
                log("ALBUM EMPTY.")
                return

            if all(getattr(msg, "out", False) for msg in messages):
                log("OUTGOING ALBUM SKIPPED.")
                return

            log(f"SOURCE ALBUM EVENT. chat_id={event.chat_id}")
            await send_album(event)

        except Exception as e:
            log(f"ALBUM HANDLER ERROR: {repr(e)}")

    @client.on(events.NewMessage(chats=SOURCE_CHATS))
    async def message_handler(event):
        try:
            message = event.message

            if event.out:
                log(f"OUTGOING MESSAGE SKIPPED. message_id={message.id}")
                return

            if message.grouped_id:
                log(f"GROUPED MESSAGE SKIPPED FOR ALBUM. grouped_id={message.grouped_id}")
                return

            log(f"SOURCE MESSAGE EVENT. chat_id={event.chat_id}, message_id={message.id}")
            await send_single_message(message)

        except Exception as e:
            log(f"MESSAGE HANDLER ERROR: {repr(e)}")

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
