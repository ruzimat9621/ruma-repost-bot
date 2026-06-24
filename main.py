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
processed_messages = set()


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


def short_caption_or_none(caption):
    if caption and len(caption) <= 1024:
        return caption
    return None


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

    await start_web_server()
    await client.start()

    me = await client.get_me()
    target_entity = await client.get_entity(TARGET_CHAT)
    target_chat_id = int(f"-100{target_entity.id}") if not str(target_entity.id).startswith("-100") else target_entity.id

    log(f"Telegram session logged in as: {me.first_name} / id={me.id}")
    log("Ruma repost bot started.")
    log(f"Source chats: {SOURCE_CHATS}")
    log(f"Target chat: {TARGET_CHAT}")
    log(f"Target chat id: {target_chat_id}")

    async def send_text_after_if_needed(caption, was_caption_sent):
        if caption and not was_caption_sent:
            await client.send_message(TARGET_CHAT, caption)
            log("TEXT SENT SEPARATELY.")

    async def send_downloadable_media(message, caption):
        """
        Rasm, video, fayl/document, sticker, voice, audio, yumaloq video va boshqa download bo‘ladigan media.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = await client.download_media(message, file=tmpdir)

            log(f"DOWNLOADED MEDIA PATH: {file_path}")

            if not file_path:
                await client.send_message(TARGET_CHAT, caption)
                log("MEDIA DOWNLOAD EMPTY. SENT TEXT ONLY.")
                return

            # Sticker, voice, yumaloq video odatda caption qabul qilmaydi.
            is_sticker = bool(getattr(message, "sticker", None))
            is_voice = bool(getattr(message, "voice", None))
            is_video_note = bool(getattr(message, "video_note", None))

            if is_sticker:
                await client.send_file(
                    TARGET_CHAT,
                    file_path,
                    force_document=False
                )
                await send_text_after_if_needed(caption, False)
                log("STICKER SENT.")
                return

            if is_voice:
                await client.send_file(
                    TARGET_CHAT,
                    file_path,
                    voice_note=True
                )
                await send_text_after_if_needed(caption, False)
                log("VOICE SENT.")
                return

            if is_video_note:
                await client.send_file(
                    TARGET_CHAT,
                    file_path,
                    video_note=True
                )
                await send_text_after_if_needed(caption, False)
                log("ROUND VIDEO SENT.")
                return

            # Oddiy rasm/video/document/audio
            cap = short_caption_or_none(caption)

            await client.send_file(
                TARGET_CHAT,
                file_path,
                caption=cap,
                force_document=False
            )

            await send_text_after_if_needed(caption, cap is not None)

            log("MEDIA/FILE SENT SUCCESSFULLY.")

    async def send_single_message(message):
        original_text = message.message or ""
        caption = build_caption(original_text)

        has_media = bool(message.media)
        log(
            f"SENDING SINGLE. message_id={message.id}, "
            f"has_media={has_media}, text_len={len(original_text)}"
        )

        if has_media:
            try:
                await send_downloadable_media(message, caption)
            except Exception as e:
                log(f"MEDIA SEND ERROR: {repr(e)}")

                # Agar download/send_file ishlamasa, oxirgi variant: originalni forward qilib, tekstni alohida tashlaymiz.
                try:
                    await client.forward_messages(
                        TARGET_CHAT,
                        message
                    )
                    await client.send_message(TARGET_CHAT, caption)
                    log("FALLBACK FORWARD + TEXT SENT.")
                except Exception as e2:
                    log(f"FALLBACK ERROR: {repr(e2)}")
                    await client.send_message(
                        TARGET_CHAT,
                        f"{caption}\n\n⚠️ Media/fayl repost bo‘lmadi. Sabab: {str(e2)}"
                    )
        else:
            await client.send_message(TARGET_CHAT, caption)
            log("TEXT SENT SUCCESSFULLY.")

    async def send_album(event):
        messages = event.messages or []

        if not messages:
            log("EMPTY ALBUM SKIPPED.")
            return

        grouped_id = messages[0].grouped_id
        if grouped_id in processed_albums:
            log(f"ALBUM DUPLICATE SKIPPED. grouped_id={grouped_id}")
            return

        processed_albums.add(grouped_id)

        first_text = ""
        for msg in messages:
            if msg.message:
                first_text = msg.message
                break

        caption = build_caption(first_text)

        log(
            f"ALBUM DETECTED. grouped_id={grouped_id}, "
            f"count={len(messages)}, caption_len={len(caption)}"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            files = []
            separate_messages = []

            for msg in messages:
                if not msg.media:
                    continue

                # Sticker / voice / round video album ichida bo‘lsa alohida yuboramiz.
                is_sticker = bool(getattr(msg, "sticker", None))
                is_voice = bool(getattr(msg, "voice", None))
                is_video_note = bool(getattr(msg, "video_note", None))

                if is_sticker or is_voice or is_video_note:
                    separate_messages.append(msg)
                    continue

                try:
                    file_path = await client.download_media(msg, file=tmpdir)
                    if file_path:
                        files.append(file_path)
                        log(f"ALBUM FILE DOWNLOADED: {file_path}")
                except Exception as e:
                    log(f"ALBUM FILE DOWNLOAD ERROR: {repr(e)}")
                    separate_messages.append(msg)

            caption_sent = False

            if files:
                cap = short_caption_or_none(caption)

                try:
                    await client.send_file(
                        TARGET_CHAT,
                        files,
                        caption=cap,
                        force_document=False
                    )
                    caption_sent = cap is not None
                    log("ALBUM FILES SENT SUCCESSFULLY.")
                except Exception as e:
                    log(f"ALBUM SEND_FILE ERROR: {repr(e)}")

                    # Agar album bo‘lib yuborilmasa, bittalab yuboramiz.
                    for f in files:
                        await client.send_file(
                            TARGET_CHAT,
                            f,
                            force_document=False
                        )
                    log("ALBUM SENT ONE BY ONE.")

            for msg in separate_messages:
                try:
                    await send_downloadable_media(msg, "")
                except Exception as e:
                    log(f"SEPARATE ALBUM ITEM ERROR: {repr(e)}")
                    try:
                        await client.forward_messages(TARGET_CHAT, msg)
                    except Exception as e2:
                        log(f"SEPARATE FALLBACK ERROR: {repr(e2)}")

            await send_text_after_if_needed(caption, caption_sent)

    @client.on(events.Album(chats=SOURCE_CHATS))
    async def album_handler(event):
        try:
            # Agar adashib target kanal SOURCE_CHATS ichiga tushib qolsa, o‘zini o‘zi repost qilmasin.
            if event.chat_id == target_chat_id:
                log(f"TARGET ALBUM SKIPPED. chat_id={event.chat_id}")
                return

            messages = event.messages or []

            if not messages:
                log("SKIPPED EMPTY ALBUM.")
                return

            if all(getattr(msg, "out", False) for msg in messages):
                log("SKIPPED OUTGOING ALBUM.")
                return

            log(f"SOURCE ALBUM DETECTED. chat_id={event.chat_id}, count={len(messages)}")
            await send_album(event)

        except Exception as e:
            log(f"ERROR while album reposting: {repr(e)}")

    @client.on(events.NewMessage(chats=SOURCE_CHATS))
    async def repost_handler(event):
        try:
            message = event.message

            # O‘z kanalimdan chiqayotgan xabarlarni ushlamasin.
            if event.chat_id == target_chat_id:
                log(f"TARGET MESSAGE SKIPPED. chat_id={event.chat_id}, message_id={message.id}")
                return

            if event.out:
                log(f"OUTGOING MESSAGE SKIPPED. chat_id={event.chat_id}, message_id={message.id}")
                return

            message_key = f"{event.chat_id}:{message.id}"
            if message_key in processed_messages:
                log(f"DUPLICATE MESSAGE SKIPPED. {message_key}")
                return

            processed_messages.add(message_key)

            # Albumdagi rasm/videolarni NewMessage emas, Album handler yuboradi.
            if message.grouped_id:
                log(f"GROUPED MESSAGE SKIPPED FOR ALBUM HANDLER. grouped_id={message.grouped_id}")
                return

            log(f"SOURCE MESSAGE DETECTED. chat_id={event.chat_id}, message_id={message.id}")

            await send_single_message(message)

            log(f"REPOSTED SUCCESSFULLY. message_id={message.id}")

        except Exception as e:
            log(f"ERROR while reposting: {repr(e)}")

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
