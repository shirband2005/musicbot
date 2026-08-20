"""نقطه‌ی ورود ربات: راه‌اندازی کلاینت‌ها، ثبت هندلر پایان استریم و اجرای حلقه."""
import asyncio
import logging

from pyrogram import idle
from pytgcalls.types import StreamEnded

from bot import app, assistant, call
import config
from bot import logs
from bot import player
from bot import youtube

LOGGER = logging.getLogger("musicbot.main")


@call.on_update()
async def _on_stream_end(_, update):
    """وقتی استریم یک آهنگ تمام شد، به‌طور خودکار آهنگ بعدی صف را پخش کن."""
    if isinstance(update, StreamEnded):
        chat_id = update.chat_id
        logs.info("پایان استریم | chat=%s — پخش بعدی", chat_id)
        try:
            await player.skip(chat_id)
        except Exception as e:  # noqa: BLE001
            logs.warn("auto-skip error | chat=%s: %s", chat_id, e)


async def main():
    logs.stage_start("BOOT")
    # نوشتن فایل کوکی از COOKIES_B64 (اگر تنظیم شده باشد) پیش از هر چیز
    if config.materialize_cookies():
        logs.info("YouTube: فایل کوکی آماده شد ✅ (%s)", config.COOKIES_FILE)
    try:
        with logs.stage("START_BOT"):
            await app.start()
        with logs.stage("START_ASSISTANT"):
            await assistant.start()
        with logs.stage("START_CALLS"):
            await call.start()
    except Exception as e:  # noqa: BLE001
        logs.stage_fail("BOOT", err=e)
        raise

    me = await app.get_me()
    logs.info("ربات: @%s (id=%s)", me.username, me.id)

    try:
        a = await assistant.get_me()
        logs.info("یوزربات کمکی: %s (id=%s)", a.first_name, a.id)
    except Exception as e:  # noqa: BLE001
        logs.warn("اطلاعات یوزربات کمکی خوانده نشد: %s", e)

    # وضعیت کوکی یوتیوب
    if youtube.has_cookies():
        logs.info("YouTube: فایل کوکی یافت شد ✅ (%s)", config.COOKIES_FILE)
    else:
        logs.warn(
            "YouTube: فایل کوکی موجود نیست — روی IP ابری ممکن است با خطای "
            "«Sign in to confirm you're not a bot» مواجه شوی. زنجیره کلاینت‌ها امتحان می‌شود."
        )

    logs.stage_ok("BOOT")
    logs.info("🎵 ربات آماده است.")

    await idle()

    logs.info("در حال خاموش شدن...")
    await app.stop()
    await assistant.stop()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
