"""ساخت پنل پخش (کاور + متن + دکمه‌ها) مطابق طرح نهایی کاربر."""
import os

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.queue import Track, progress_bar

# کاور ثابت پنل. می‌تواند عکس (jpg/png) یا گیف/ویدیو (gif/mp4) باشد.
# روی Volume ذخیره می‌شود تا با دیپلوی جدید پاک نشود.
COVER_PATH = os.environ.get("COVER_PATH", "/data/cover").strip() or "/data/cover"

# پسوندهای شناخته‌شده برای پیدا کردن فایل کاور (چون ممکن است بدون پسوند ذخیره شود)
_COVER_EXTS = [".gif", ".mp4", ".jpg", ".jpeg", ".png", ".webp", ""]

_ANIM_EXTS = (".gif", ".mp4")


def cover_file() -> str:
    """مسیر فایل کاور موجود را برمی‌گرداند (با هر پسوند)، یا رشته خالی.

    اول COVER_PATH (روی Volume) بعد فایل تعبیه‌شده در assets/ بررسی می‌شود.
    """
    candidates = [COVER_PATH]
    # مسیر تعبیه‌شده در ریپو به‌عنوان fallback
    candidates.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "cover"))
    for base in candidates:
        if os.path.isfile(base):
            return base
        for ext in _COVER_EXTS:
            p = base + ext
            if p and os.path.isfile(p):
                return p
    return ""


def has_cover() -> bool:
    return bool(cover_file())


def cover_is_animation() -> bool:
    """آیا کاور گیف/ویدیو است (نیازمند send_animation)؟"""
    f = cover_file()
    return bool(f) and f.lower().endswith(_ANIM_EXTS)


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
            InlineKeyboardButton("🔉 کاهش صدا", callback_data=cb("vol_down")),
            InlineKeyboardButton(f"{volume}%", callback_data=cb("noop")),
            InlineKeyboardButton("🔊 افزایش صدا", callback_data=cb("vol_up")),
        ],
        [InlineKeyboardButton(mute_btn, callback_data=cb("mute"))],
        [
            InlineKeyboardButton("⏮ آهنگ قبلی", callback_data=cb("prev")),
            InlineKeyboardButton("📃 پلی‌لیست", callback_data=cb("playlist")),
            InlineKeyboardButton("⏭ آهنگ بعدی", callback_data=cb("skip")),
        ],
        [InlineKeyboardButton("📥 دریافت رسانه", callback_data=cb("getmedia"))],
        [InlineKeyboardButton("⛔️ بستن پنل", callback_data=cb("close"))],
    ]
    return InlineKeyboardMarkup(rows)


def has_cover() -> bool:
    return bool(cover_file())

