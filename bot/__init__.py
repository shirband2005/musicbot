"""راه‌اندازی کلاینت‌ها: ربات (app)، یوزربات کمکی (assistant) و موتور پخش کال."""
import logging
import sys

from pyrogram import Client
from pytgcalls import PyTgCalls

import config

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# کاهش نویز لاگ‌های داخلی
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("ntgcalls").setLevel(logging.WARNING)

LOGGER = logging.getLogger("musicbot")


def _validate() -> None:
    missing = []
    if not config.API_ID:
        missing.append("API_ID")
    if not config.API_HASH:
        missing.append("API_HASH")
    if not config.BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not config.STRING_SESSION:
        missing.append("STRING_SESSION")
    if missing:
        LOGGER.error("متغیرهای محیطی زیر تنظیم نشده‌اند: %s", ", ".join(missing))
        sys.exit(1)


_validate()

# اکانت ربات: منوها، دستورات و رابط کاربری
app = Client(
    name="musicbot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    in_memory=True,
    plugins=dict(root="bot.plugins"),
)

# یوزربات کمکی: اکانتی که واقعاً وارد ویس‌چت می‌شود و استریم می‌کند
assistant = Client(
    name="assistant",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    session_string=config.STRING_SESSION,
    in_memory=True,
)

# موتور پخش صدا/ویدیو در کال (روی اکانت کمکی سوار می‌شود)
call = PyTgCalls(assistant)
