"""دستورات /start و /help."""
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import database as db

START_TEXT = (
    "🎵 **سلام! به موزیک‌پلیر فارسی خوش اومدی.**\n\n"
    "من می‌تونم آهنگ و ویدیو رو مستقیم داخل ویس‌چت گروه پخش کنم.\n\n"
    "برای شروع، منو رو به گروهت اضافه کن و ویس‌چت رو روشن کن، "
    "بعد دستور پخش رو بفرست."
)

HELP_TEXT = (
    "📖 **راهنمای دستورات**\n\n"
    "🎵 `/play <نام آهنگ یا لینک>` — پخش آهنگ در ویس‌چت\n"
    "🎬 `/vplay <نام یا لینک>` — پخش ویدیو در ویس‌چت\n"
    "⏸ `/pause` — مکث\n"
    "▶️ `/resume` — ادامه\n"
    "⏭ `/skip` — رد کردن و پخش بعدی\n"
    "⏹ `/stop` — توقف و خروج از کال\n"
    "📜 `/queue` — نمایش صف پخش\n\n"
    "همه‌ی این‌ها با دکمه‌های پنل هم قابل کنترل‌اند."
)


def _start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📖 راهنما", callback_data="help")],
            [
                InlineKeyboardButton(
                    "➕ افزودن به گروه", url="https://t.me/?startgroup=true"
                )
            ],
        ]
    )


@Client.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    if message.from_user:
        db.add_user(message.from_user.id)
    if message.chat.type.name != "PRIVATE":
        db.add_chat(message.chat.id)
    await message.reply_text(START_TEXT, reply_markup=_start_kb())


@Client.on_message(filters.command("help"))
async def help_cmd(client: Client, message: Message):
    await message.reply_text(HELP_TEXT)
