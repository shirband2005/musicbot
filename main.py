"""نقطه‌ی ورود ربات: راه‌اندازی کلاینت‌ها، ثبت هندلر پایان استریم و اجرای حلقه."""
import asyncio
import logging

from pyrogram import idle
from pytgcalls.types import StreamEnded

from bot import app, assistant, call
from bot import player

LOGGER = logging.getLogger("musicbot.main")


@call.on_update()
async def _on_stream_end(_, update):
    """وقتی استریم یک آهنگ تمام شد، به‌طور خودکار آهنگ بعدی صف را پخش کن."""
    if isinstance(update, StreamEnded):
        chat_id = update.chat_id
        LOGGER.info("پایان استریم در %s — پخش بعدی", chat_id)
        try:
            await player.skip(chat_id)
        except Exception as e:  # noqa: BLE001
            LOGGER.warning("auto-skip error: %s", e)


async def main():
    LOGGER.info("در حال راه‌اندازی...")
    await app.start()
    await assistant.start()
    await call.start()

    me = await app.get_me()
    LOGGER.info("✅ ربات آنلاین شد: @%s", me.username)

    try:
        assistant_me = await assistant.get_me()
        LOGGER.info("✅ یوزربات کمکی: %s", assistant_me.first_name)
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("اطلاعات یوزربات کمکی خوانده نشد: %s", e)

    await idle()

    LOGGER.info("در حال خاموش شدن...")
    await app.stop()
    await assistant.stop()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
