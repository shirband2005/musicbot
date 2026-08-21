"""ساخت پنل پخش (کاور + متن + دکمه‌ها) با ایموجی پرمیوم (custom emoji).

ربات چون مالکش Premium است، می‌تواند custom emoji در متن و آیکون دکمه‌ها بگذارد.
طول entity برحسب UTF-16 code unit شمرده می‌شود (مبنای تلگرام).
"""
import os

from pyrogram import enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity

from bot.queue import Track, progress_bar
from bot import platform_pref

# میانبرهای رنگ دکمه
GREEN = enums.ButtonStyle.SUCCESS
RED = enums.ButtonStyle.DANGER
BLUE = enums.ButtonStyle.PRIMARY

_CE = enums.MessageEntityType.CUSTOM_EMOJI
_BOLD = enums.MessageEntityType.BOLD

# ---------- شناسه‌های ایموجی پرمیوم (custom_emoji_id) ----------
# آیکون دکمه‌ها
EMO_PAUSE = 5202196261591071609       # توقف موقت
EMO_STOP = 5465602779038895643        # توقف
EMO_PREV = 5870813397020318155        # آهنگ قبلی
EMO_NEXT = 5870738170668128957        # آهنگ بعدی
EMO_MUTE = 5974085198457867499        # بیصدا
EMO_UNMUTE = 5976746905655316100      # صدادار
EMO_VOL_DOWN = 5440751149076475199    # کاهش صدا
EMO_VOL_UP = 5305329417189340362      # افزایش صدا
EMO_PLAYLIST = 5237788939040874458    # پلی‌لیست
EMO_BACK = 5235864325540815679        # برگشت (راهنما)
EMO_CLOSE = 5215697242177939628       # بستن پنل
EMO_GETMEDIA = 5291983502101732021    # دریافت رسانه
EMO_PLATFORM_SC = 6046465713906914454   # پلتفرم: ساوندکلاد
EMO_PLATFORM_YT = 6046476910886656326   # پلتفرم: یوتیوب

# ایموجی‌های متن پنل
EMO_BULLET1 = 5870544922909613410     # نشانگر خطوط (وضعیت/میزان صدا)
EMO_BULLET2 = 5870606297992273496     # نشانگر خطوط (نوع/پخش‌کننده)
EMO_PLAYING = 5962964097904413958     # وضعیت: در حال پخش
EMO_SONG = 5929546997483704366        # نوع: آهنگ

# کاراکترهای پایه (fallback برای کاربران غیر پرمیوم)
_C_DOT = "🔹"
_C_PLAY = "▶️"
_C_NOTE = "🎵"

COVER_PATH = os.environ.get("COVER_PATH", "/data/cover").strip() or "/data/cover"
_COVER_EXTS = [".gif", ".mp4", ".jpg", ".jpeg", ".png", ".webp", ""]
_STATIC_EXTS = [".jpg", ".jpeg", ".png", ".webp", ""]
_ANIM_EXTS = (".gif", ".mp4")


def _u16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def cover_file() -> str:
    candidates = [COVER_PATH,
                  os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "cover")]
    for base in candidates:
        if os.path.isfile(base):
            return base
        for ext in _COVER_EXTS:
            p = base + ext
            if p and os.path.isfile(p):
                return p
    return ""


def cover_static_file() -> str:
    candidates = [COVER_PATH + "_static",
                  os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "cover_static")]
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
    f = cover_file()
    return bool(f) and f.lower().endswith(_ANIM_EXTS)


def _build(segs):
    """segs: list of (text, emoji_id|None, bold). برمی‌گرداند (text, entities)."""
    text, ents, off = "", [], 0
    for t, eid, bold in segs:
        L = _u16(t)
        if eid:
            ents.append(MessageEntity(type=_CE, offset=off, length=L, custom_emoji_id=eid))
        if bold:
            ents.append(MessageEntity(type=_BOLD, offset=off, length=L))
        text += t
        off += L
    return text, ents


def panel_content(track: Track, volume: int = 100, muted: bool = False):
    """متن پنل + entities ایموجی پرمیوم. برمی‌گرداند (text, entities).

    چیدمان طبق طرح کاربر:
      🎧 <عنوان>
      <ایموجی> وضعیت : ... <ایموجی وضعیت>
      <ایموجی> نوع : ... <ایموجی نوع>
      <ایموجی> میزان صدا : ...
      <ایموجی> پخش‌کننده : ...
    """
    status_txt = "متوقف موقت" if track.paused else "در حال پخش"
    kind = "ویدیو" if track.is_video else "آهنگ"
    vol_txt = "بیصدا" if muted else f"{volume}%"

    segs = [
        ("🎧 ", None, False),
        (track.title, None, True),
        ("\n\n", None, False),
        # وضعیت (نشانگر ابتدای خط + ایموجی وضعیت انتهای خط)
        (_C_DOT, EMO_BULLET1, False),
        (f" وضعیت : {status_txt} ", None, False),
        (_C_PLAY, EMO_PLAYING if not track.paused else None, False),
        ("\n", None, False),
        # نوع
        (_C_DOT, EMO_BULLET2, False),
        (f" نوع : {kind} ", None, False),
        (_C_NOTE, EMO_SONG if not track.is_video else None, False),
        ("\n", None, False),
        # میزان صدا
        (_C_DOT, EMO_BULLET1, False),
        (f" میزان صدا : {vol_txt}\n", None, False),
        # پخش‌کننده
        (_C_DOT, EMO_BULLET2, False),
        (f" پخش‌کننده : {track.requester}", None, False),
    ]
    return _build(segs)


def panel_text(track: Track, volume: int = 100, muted: bool = False) -> str:
    """فقط متن (بدون entities) — برای سازگاری."""
    return panel_content(track, volume, muted)[0]


def panel_entities(track: Track, volume: int = 100, muted: bool = False):
    return panel_content(track, volume, muted)[1]


def panel_keyboard(
    chat_id: int,
    track: Track,
    volume: int = 100,
    muted: bool = False,
) -> InlineKeyboardMarkup:
    """کیبورد اینلاین با آیکون ایموجی پرمیوم. callback: 'p|<action>|<chat_id>'."""
    def cb(action: str) -> str:
        return f"p|{action}|{chat_id}"

    bar = progress_bar(track.position(), track.duration)

    # دکمه پخش/مکث
    if track.paused:
        play_btn, play_style, play_icon = "پخش", GREEN, None
    else:
        play_btn, play_style, play_icon = "توقف موقت", BLUE, EMO_PAUSE
    # دکمه صدا
    if muted:
        mute_btn, mute_style, mute_icon = "صدادار", GREEN, EMO_UNMUTE
    else:
        mute_btn, mute_style, mute_icon = "بیصدا", RED, EMO_MUTE

    # آیکون پلتفرم بسته به حالت
    mode = platform_pref.get(chat_id)
    if mode == platform_pref.YOUTUBE:
        plat_icon = EMO_PLATFORM_YT
    elif mode == platform_pref.SOUNDCLOUD:
        plat_icon = EMO_PLATFORM_SC
    else:
        plat_icon = EMO_PLATFORM_YT  # حالت هر دو → آیکون یوتیوب

    def B(text, action, style, icon=None):
        return InlineKeyboardButton(text, callback_data=cb(action), style=style,
                                    icon_custom_emoji_id=icon)

    rows = [
        [InlineKeyboardButton(bar, callback_data=cb("refresh"), style=GREEN)],
        [
            B(play_btn, "playpause", play_style, play_icon),
            B("توقف", "stop", RED, EMO_STOP),
        ],
        [
            B("کاهش صدا", "vol_down", RED, EMO_VOL_DOWN),
            InlineKeyboardButton(f"{volume}%", callback_data=cb("noop"), style=BLUE),
            B("افزایش صدا", "vol_up", GREEN, EMO_VOL_UP),
        ],
        [B(mute_btn, "mute", mute_style, mute_icon)],
        [
            B("آهنگ قبلی", "prev", RED, EMO_PREV),
            B("پلی‌لیست", "playlist", BLUE, EMO_PLAYLIST),
            B("آهنگ بعدی", "skip", GREEN, EMO_NEXT),
        ],
        [B("دریافت رسانه", "getmedia", BLUE, EMO_GETMEDIA)],
    ]
    # دکمه پلتفرم فقط وقتی نمایش داده می‌شود که پلتفرم قفل نشده باشد.
    from bot import group_config as gc
    if not gc.is_locked(chat_id):
        rows.append([B(platform_pref.label(chat_id), "platform", BLUE, plat_icon)])
    rows.append([B("بستن پنل", "close", RED, EMO_CLOSE)])
    return InlineKeyboardMarkup(rows)
