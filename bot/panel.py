"""ساخت پنل پخش (کاور + متن + دکمه‌ها) مطابق طرح نهایی کاربر."""
import os

from pyrogram import enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.queue import Track, progress_bar
from bot import platform_pref

# میانبرهای رنگ دکمه (kurigram: enums.ButtonStyle)
GREEN = enums.ButtonStyle.SUCCESS
RED = enums.ButtonStyle.DANGER
BLUE = enums.ButtonStyle.PRIMARY

# کاور ثابت پنل. می‌تواند عکس (jpg/png) یا گیف/ویدیو (gif/mp4) باشد.
# روی Volume ذخیره می‌شود تا با دیپلوی جدید پاک نشود.
COVER_PATH = os.environ.get("COVER_PATH", "/data/cover").strip() or "/data/cover"

# پسوندهای شناخته‌شده برای پیدا کردن فایل کاور (چون ممکن است بدون پسوند ذخیره شود)
_COVER_EXTS = [".gif", ".mp4", ".jpg", ".jpeg", ".png", ".webp", ""]
_STATIC_EXTS = [".jpg", ".jpeg", ".png", ".webp", ""]

_ANIM_EXTS = (".gif", ".mp4")


def cover_file() -> str:
    """مسیر کاور متحرک (گیف/ویدیو) موجود را برمی‌گرداند، یا رشته خالی.

    اول COVER_PATH (روی Volume) بعد فایل تعبیه‌شده در assets/ بررسی می‌شود.
    """
    candidates = [COVER_PATH]
    candidates.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "cover"))
    for base in candidates:
        if os.path.isfile(base):
            return base
        for ext in _COVER_EXTS:
            p = base + ext
            if p and os.path.isfile(p):
                return p
    return ""


def cover_static_file() -> str:
    """مسیر کاور ثابت (عکس اکولایزر بی‌حرکت) برای حالت مکث/توقف موقت."""
    candidates = [COVER_PATH + "_static"]
    candidates.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "cover_static"))
    for base in candidates:
        if os.path.isfile(base):
            return base
        for ext in _STATIC_EXTS:
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

    # دکمه پخش/مکث بسته به وضعیت (پخش=سبز، توقف‌موقت=آبی)
    if track.paused:
        play_btn, play_style = "▶️ پخش", GREEN
    else:
        play_btn, play_style = "⏸ توقف موقت", BLUE
    # دکمه صدا (بیصدا=قرمز، صدادار=سبز)
    if muted:
        mute_btn, mute_style = "🔈 صدادار", GREEN
    else:
        mute_btn, mute_style = "🔇 بیصدا", RED

    rows = [
        [InlineKeyboardButton(bar, callback_data=cb("refresh"), style=GREEN)],
        [
            InlineKeyboardButton(play_btn, callback_data=cb("playpause"), style=play_style),
            InlineKeyboardButton("⏹ توقف", callback_data=cb("stop"), style=RED),
        ],
        [
            InlineKeyboardButton("🔉 کاهش صدا", callback_data=cb("vol_down"), style=RED),
            InlineKeyboardButton(f"{volume}%", callback_data=cb("noop"), style=BLUE),
            InlineKeyboardButton("🔊 افزایش صدا", callback_data=cb("vol_up"), style=GREEN),
        ],
        [InlineKeyboardButton(mute_btn, callback_data=cb("mute"), style=mute_style)],
        [
            InlineKeyboardButton("⏮ آهنگ قبلی", callback_data=cb("prev"), style=RED),
            InlineKeyboardButton("📃 پلی‌لیست", callback_data=cb("playlist"), style=BLUE),
            InlineKeyboardButton("⏭ آهنگ بعدی", callback_data=cb("skip"), style=GREEN),
        ],
        [InlineKeyboardButton("📥 دریافت رسانه", callback_data=cb("getmedia"), style=BLUE)],
        [InlineKeyboardButton(f"🎛 {platform_pref.label(chat_id)}", callback_data=cb("platform"), style=BLUE)],
        [InlineKeyboardButton("⛔️ بستن پنل", callback_data=cb("close"), style=RED)],
    ]
    return InlineKeyboardMarkup(rows)


def has_cover() -> bool:
    return bool(cover_file())

