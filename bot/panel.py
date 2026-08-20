"""ساخت پنل پخش (کاور + متن + دکمه‌ها) مطابق طرح نهایی کاربر."""
import os

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.queue import Track, progress_bar

# کاور ثابت برندینگ‌شده — کاربر بعداً فایل نهایی را جایگزین می‌کند.
COVER_PATH = os.environ.get("COVER_PATH", "assets/cover.jpg").strip() or "assets/cover.jpg"


def panel_text(track: Track, volume: int = 100, muted: bool = False) -> str:
    """متن زیر کاور پنل پخش (طبق طرح: وضعیت / نوع / میزان صدا / پخش‌کننده)."""
    if track.paused:
        status = "⏸ متوقف موقت"
    else:
        status = "▶️ در حال پخش"
    kind = "🎬 ویدیو" if track.is_video else "🎵 آهنگ"
    vol_txt = "🔇 بیصدا" if muted else f"{volume}%"
    return (
        f"🎧 **{track.title}**\n\n"
        f"❯❯ وضعیت : {status}\n"
        f"❯❯ نوع : {kind}\n"
        f"❯❯ میزان صدا : {vol_txt}\n"
        f"❯❯ پخش‌کننده : {track.requester}"
    )


def panel_keyboard(
    chat_id: int,
    track: Track,
    volume: int = 100,
    muted: bool = False,
) -> InlineKeyboardMarkup:
    """کیبورد اینلاین پنل پخش. الگوی callback: 'p|<action>|<chat_id>'."""
    def cb(action: str) -> str:
        return f"p|{action}|{chat_id}"

    # ردیف اول: نوار وضعیت (خودِ نوار پیشرفت به‌عنوان متنِ دکمه)
    bar = progress_bar(track.position(), track.duration)

    # دکمه پخش/مکث بسته به وضعیت
    play_btn = "▶️ پخش" if track.paused else "⏸ توقف موقت"
    mute_btn = "🔈 صدادار" if muted else "🔇 بیصدا"

    rows = [
        [InlineKeyboardButton(bar, callback_data=cb("refresh"))],
        [
            InlineKeyboardButton(play_btn, callback_data=cb("playpause")),
            InlineKeyboardButton("⏹ توقف", callback_data=cb("stop")),
        ],
        [
            InlineKeyboardButton("🔊 افزایش صدا", callback_data=cb("vol_up")),
            InlineKeyboardButton(f"{volume}%", callback_data=cb("noop")),
            InlineKeyboardButton("🔉 کاهش صدا", callback_data=cb("vol_down")),
        ],
        [InlineKeyboardButton(mute_btn, callback_data=cb("mute"))],
        [
            InlineKeyboardButton("⏭ آهنگ بعدی", callback_data=cb("skip")),
            InlineKeyboardButton("📃 پلی‌لیست", callback_data=cb("playlist")),
            InlineKeyboardButton("⏮ آهنگ قبلی", callback_data=cb("prev")),
        ],
        [InlineKeyboardButton("📥 دریافت رسانه", callback_data=cb("getmedia"))],
        [InlineKeyboardButton("⛔️ بستن پنل", callback_data=cb("close"))],
    ]
    return InlineKeyboardMarkup(rows)


def has_cover() -> bool:
    return os.path.isfile(COVER_PATH)
