"""ساخت پنل پخش (کاور + متن + دکمه‌ها) مطابق طرح دلخواه کاربر."""
import os

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.queue import Track, progress_bar

# کاور ثابت برندینگ‌شده — کاربر بعداً فایل نهایی را جایگزین می‌کند.
# مسیر نسبت به ریشه‌ی پروژه.
COVER_PATH = os.environ.get("COVER_PATH", "assets/cover.jpg").strip() or "assets/cover.jpg"


def panel_text(track: Track) -> str:
    """متن زیر کاور پنل پخش."""
    status = "⏸ متوقف موقت" if track.paused else "▶️ در حال پخش"
    kind = "ویدیو 🎬" if track.is_video else "یوتیوب 🎵"
    bar = progress_bar(track.position(), track.duration)
    return (
        f"🎧 **{track.title}**\n\n"
        f"❯❯ وضعیت : {status}\n"
        f"❯❯ نوع : {kind}\n"
        f"❯❯ درخواست‌کننده پخش : {track.requester}\n\n"
        f"`{bar}`"
    )


def panel_keyboard(chat_id: int, volume: int = 100, speed: float = 1.0) -> InlineKeyboardMarkup:
    """کیبورد اینلاین پنل پخش. الگوی callback: 'p|<action>|<chat_id>'."""
    def cb(action: str) -> str:
        return f"p|{action}|{chat_id}"

    rows = [
        [
            InlineKeyboardButton("⏹ توقف", callback_data=cb("stop")),
            InlineKeyboardButton("⏭ رد کردن", callback_data=cb("skip")),
        ],
        [
            InlineKeyboardButton("⏸ مکث", callback_data=cb("pause")),
            InlineKeyboardButton("▶️ ادامه", callback_data=cb("resume")),
        ],
        [
            InlineKeyboardButton("🔉 −", callback_data=cb("vol_down")),
            InlineKeyboardButton(f"میزان صدا {volume}%", callback_data=cb("noop")),
            InlineKeyboardButton("🔊 +", callback_data=cb("vol_up")),
        ],
        [
            InlineKeyboardButton("🔇 بیصدا", callback_data=cb("mute")),
            InlineKeyboardButton("🔈 صدادار", callback_data=cb("unmute")),
        ],
        [
            InlineKeyboardButton("⏪ ۶۰", callback_data=cb("back60")),
            InlineKeyboardButton("◀️ ۳۰", callback_data=cb("back30")),
            InlineKeyboardButton("۳۰ ▶️", callback_data=cb("fwd30")),
            InlineKeyboardButton("۶۰ ⏩", callback_data=cb("fwd60")),
        ],
        [InlineKeyboardButton("🔄 بروزرسانی نوار", callback_data=cb("refresh"))],
        [InlineKeyboardButton("⛔️ بستن پنل", callback_data=cb("close"))],
    ]
    return InlineKeyboardMarkup(rows)


def has_cover() -> bool:
    return os.path.isfile(COVER_PATH)
