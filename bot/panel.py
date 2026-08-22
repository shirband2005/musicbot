"""پنل پخش موزیک — متن، کیبورد و کاور.

ساختار (تصمیم‌های تأییدشده‌ی طراحی):

    🎧 <عنوان آهنگ>
    ◀️ وضعیت : در حال پخش
    ◀️ نوع : آهنگ
    ◀️ پلتفرم پخش : هر دو
    ◀️ پخش‌کننده : <نام قابل کلیک>

    [ 01:34 │ ━━━━◉──────── │ 04:12 ]      آبی، تمام‌عرض
    [ ⏮ ][ ⏸ ][ ⏹ ][ ⏭ ]                   قرمز، آبی، قرمز، سبز
    [ 🔉 ][ 100% ][ 🔊 ]                    بی‌رنگ (بیصدا → 0% قرمز)
    [ لیست پخش ][ حالت: پخش صف ]
    [ تایمر خواب ]
    [ دریافت رسانه ][ پلتفرم: هر دو ]
    [ بستن پنل ]

منوهای آکاردئونی (حالت پخش / تایمر خواب / پلتفرم) وضعیتشان per-chat در حافظه
نگه داشته می‌شود؛ وگرنه رفرش ۵ثانیه‌ای نوار زمان منو را وسط انتخاب می‌بندد.
"""
from __future__ import annotations

import os
import time
from typing import Dict, Optional

from pyrogram.types import InlineKeyboardMarkup

from bot import group_config as gc
from bot import platform_pref
from bot import ui
from bot.queue import Track

# ---------------------------------------------------------------- کاور
COVER_PATH = os.environ.get("COVER_PATH", "/data/cover").strip() or "/data/cover"
_COVER_EXTS = [".gif", ".mp4", ".jpg", ".jpeg", ".png", ".webp", ""]
_STATIC_EXTS = [".jpg", ".jpeg", ".png", ".webp", ""]
_ANIM_EXTS = (".gif", ".mp4")


def _find(base_names, exts) -> str:
    for base in base_names:
        if os.path.isfile(base):
            return base
        for ext in exts:
            p = base + ext
            if p and os.path.isfile(p):
                return p
    return ""


def cover_file() -> str:
    return _find(
        [COVER_PATH,
         os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "cover")],
        _COVER_EXTS,
    )


def cover_static_file() -> str:
    return _find(
        [COVER_PATH + "_static",
         os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets",
                      "cover_static")],
        _STATIC_EXTS,
    )


def has_cover() -> bool:
    return bool(cover_file())


def cover_is_animation() -> bool:
    f = cover_file()
    return bool(f) and f.lower().endswith(_ANIM_EXTS)


# ---------------------------------------------------------------- وضعیت منوها
# کدام منوی آکاردئونی در پنل این گروه باز است: None | 'mode' | 'sleep' | 'plat'
_open_menu: Dict[int, Optional[str]] = {}
# زمان باز شدن منو (برای پاک‌سازی منوهای رهاشده هنگام تعویض آهنگ)
_open_since: Dict[int, float] = {}

MENU_MODE = "mode"
MENU_SLEEP = "sleep"
MENU_PLAT = "plat"


def open_menu(chat_id: int) -> Optional[str]:
    return _open_menu.get(chat_id)


def set_menu(chat_id: int, menu: Optional[str]) -> None:
    """منوی باز را تنظیم می‌کند؛ None یعنی همه بسته."""
    if menu is None:
        _open_menu.pop(chat_id, None)
        _open_since.pop(chat_id, None)
    else:
        _open_menu[chat_id] = menu
        _open_since[chat_id] = time.time()


def toggle_menu(chat_id: int, menu: str) -> Optional[str]:
    """اگر همان منو باز است می‌بندد، وگرنه بازش می‌کند. منوی جدید را برمی‌گرداند."""
    new = None if _open_menu.get(chat_id) == menu else menu
    set_menu(chat_id, new)
    return new


def reset_menus(chat_id: int) -> None:
    """با تعویض آهنگ یا بستن پنل، منوهای باز باید پاک شوند."""
    set_menu(chat_id, None)


# ---------------------------------------------------------------- برچسب‌ها
_MODE_FULL = {
    gc.MODE_QUEUE: "پخش صف",
    gc.MODE_REPEAT: "پخش تکرار",
    gc.MODE_RANDOM: "پخش رندوم",
}
_MODE_SHORT = {gc.MODE_QUEUE: "صف", gc.MODE_REPEAT: "تکرار", gc.MODE_RANDOM: "رندوم"}
_MODE_ICON = {
    gc.MODE_QUEUE: ui.EMO_LIST,
    gc.MODE_REPEAT: ui.EMO_REPEAT,
    gc.MODE_RANDOM: ui.EMO_SHUFFLE,
}
_MODE_ORDER = (gc.MODE_QUEUE, gc.MODE_REPEAT, gc.MODE_RANDOM)

_PLAT_FULL = {
    platform_pref.BOTH: "هر دو",
    platform_pref.YOUTUBE: "یوتیوب",
    platform_pref.SOUNDCLOUD: "ساوندکلاد",
}
_PLAT_ICON = {
    platform_pref.BOTH: ui.EMO_BOTH,
    platform_pref.YOUTUBE: ui.EMO_YOUTUBE,
    platform_pref.SOUNDCLOUD: ui.EMO_SOUNDCLOUD,
}
_PLAT_ORDER = (platform_pref.SOUNDCLOUD, platform_pref.YOUTUBE, platform_pref.BOTH)

# قفل پلتفرم توسط مالک → کدام پلتفرم مجاز است
_LOCK_TO_PLAT = {
    gc.LOCK_YOUTUBE: platform_pref.YOUTUBE,
    gc.LOCK_SOUNDCLOUD: platform_pref.SOUNDCLOUD,
}

# منبع واقعی پخش (از کجا آمده) برای خط «پلتفرم پخش»
_SOURCE_LABEL = {
    "archive": "آرشیو",
    "soundcloud": "ساوند کلاد",
    "youtube": "یوتیوب",
    "telegram": "تلگرام",
    "telegram_stream": "تلگرام",
}

# گزینه‌های تایمر خواب: (دقیقه, برچسب)
SLEEP_OPTIONS = ((15, "۱۵ دقیقه"), (30, "۳۰ دقیقه"), (45, "۴۵ دقیقه"), (60, "۱ ساعت"))


# ---------------------------------------------------------------- متن پنل
def panel_content(track: Track, volume: int = 100, muted: bool = False,
                  chat_id: int = 0):
    """متن پنل + entities. برمی‌گرداند (text, entities).

    چهار خط: وضعیت / نوع / پلتفرم پخش / پخش‌کننده. «میزان صدا» عمداً در متن
    نیست چون همان عدد روی دکمه‌ی صدا دیده می‌شود.
    """
    t = ui.Text().title(ui.EMO_HEADPHONE, ui.BASE_HEADPHONE, track.title)

    source = _SOURCE_LABEL.get(getattr(track, "source", "youtube"), "یوتیوب")
    if chat_id:
        lock = gc.get_lock(chat_id)
        if lock != gc.LOCK_NONE:
            source += " (قفل)"

    t.field(0, "وضعیت", "متوقف موقت" if track.paused else "در حال پخش")
    t.field(1, "نوع", "ویدیو" if track.is_video else "آهنگ")
    t.field(2, "پلتفرم پخش", source)
    t.field(3, "پخش‌کننده",
            mention=(track.requester, getattr(track, "requester_id", 0) or 0))
    return t.text, t.entities


def panel_text(track: Track, volume: int = 100, muted: bool = False,
               chat_id: int = 0) -> str:
    return panel_content(track, volume, muted, chat_id)[0]


def panel_entities(track: Track, volume: int = 100, muted: bool = False,
                   chat_id: int = 0):
    return panel_content(track, volume, muted, chat_id)[1]


# ---------------------------------------------------------------- کیبورد پنل
def panel_keyboard(
    chat_id: int,
    track: Track,
    volume: int = 100,
    muted: bool = False,
    sleep_left: Optional[float] = None,
) -> InlineKeyboardMarkup:
    """کیبورد پنل پخش. الگوی callback: `p|<action>` یا `p|<action>|<arg>`.

    sleep_left: ثانیه‌ی باقی‌مانده‌ی تایمر خواب (None = تایمر خاموش).
    """
    menu = open_menu(chat_id)
    rows = []

    # ۱) نوار زمان — کلیک = تازه‌سازی دستی
    rows.append([ui.btn(ui.timebar(track.position(), track.duration),
                        "p|refresh", ui.BLUE)])

    # ۲) کنترل: قبلی(قرمز) پخش/مکث(آبی|سبز) توقف(قرمز) بعدی(سبز)
    if track.paused:
        play_btn = ui.icon_btn("p|playpause", ui.EMO_PLAY, ui.GREEN)
    else:
        play_btn = ui.icon_btn("p|playpause", ui.EMO_PAUSE, ui.BLUE)
    rows.append([
        ui.icon_btn("p|prev", ui.EMO_PREV, ui.RED),
        play_btn,
        ui.icon_btn("p|stop", ui.EMO_STOP, ui.RED),
        ui.icon_btn("p|skip", ui.EMO_NEXT, ui.GREEN),
    ])

    # ۳) صدا: کاهش/افزایش بی‌رنگ، وسط درصد (بیصدا → 0% قرمز)
    rows.append([
        ui.icon_btn("p|vol_down", ui.EMO_VOL_DOWN),
        ui.btn("0%" if muted else f"{volume}%", "p|mute",
               ui.RED if muted else ui.PLAIN,
               ui.EMO_MUTE if muted else ui.EMO_UNMUTE),
        ui.icon_btn("p|vol_up", ui.EMO_VOL_UP),
    ])

    # ۴) لیست پخش + حالت پخش (آکاردئونی)
    mode = gc.get_mode(chat_id)
    playlist_btn = ui.btn("لیست پخش", "p|playlist", ui.PLAIN, ui.EMO_LIST)
    if menu == MENU_MODE:
        rows.append([playlist_btn,
                     ui.btn("حالت پخش ▾", "p|mode_close", ui.BLUE, _MODE_ICON[mode])])
        rows.append([
            ui.btn(_MODE_SHORT[m], f"p|mode_set|{m}",
                   ui.GREEN if m == mode else ui.PLAIN, _MODE_ICON[m])
            for m in _MODE_ORDER
        ])
    else:
        rows.append([playlist_btn,
                     ui.btn(f"حالت: {_MODE_FULL[mode]}", "p|mode_open",
                            ui.PLAIN, _MODE_ICON[mode])])

    # ۵) تایمر خواب — همیشه یک ردیف، سه وضعیت
    if menu == MENU_SLEEP:
        rows.append([ui.btn(lbl, f"p|sleep_set|{m}") for m, lbl in SLEEP_OPTIONS])
    elif sleep_left is not None:
        rows.append([ui.btn(f"تایمر خواب : {ui.countdown(sleep_left)}",
                            "p|sleep_off", ui.RED, ui.EMO_BELL)])
    else:
        rows.append([ui.btn("تایمر خواب", "p|sleep_open", ui.PLAIN, ui.EMO_BELL_OFF)])

    # ۶) دریافت رسانه + پلتفرم (آکاردئونی؛ در حالت قفل منو باز نمی‌شود)
    media_btn = ui.btn("دریافت رسانه", "p|getmedia", ui.PLAIN, ui.EMO_DOWNLOAD)
    lock = gc.get_lock(chat_id)
    if lock != gc.LOCK_NONE:
        locked = _LOCK_TO_PLAT[lock]
        rows.append([media_btn,
                     ui.btn(f"{_PLAT_FULL[locked]} (قفل)", "p|plat_locked",
                            ui.PLAIN, _PLAT_ICON[locked])])
    else:
        plat = platform_pref.get(chat_id)
        if menu == MENU_PLAT:
            rows.append([media_btn,
                         ui.btn(f"پلتفرم: {_PLAT_FULL[plat]} ▾", "p|plat_close",
                                ui.BLUE, _PLAT_ICON[plat])])
            rows.append([
                ui.btn(_PLAT_FULL[p], f"p|plat_set|{p}",
                       ui.GREEN if p == plat else ui.PLAIN, _PLAT_ICON[p])
                for p in _PLAT_ORDER
            ])
        else:
            rows.append([media_btn,
                         ui.btn(f"پلتفرم: {_PLAT_FULL[plat]}", "p|plat_open",
                                ui.PLAIN, _PLAT_ICON[plat])])

    # ۷) بستن
    rows.append([ui.btn("بستن پنل", "p|close", ui.RED, ui.EMO_CLOSE)])
    return ui.kb(rows)


# ---------------------------------------------------------------- برچسب‌های عمومی
def mode_label(mode: str) -> str:
    return _MODE_FULL.get(mode, mode)


def platform_label(chat_id: int) -> str:
    """برچسب پلتفرم مؤثر (با در نظر گرفتن قفل مالک)."""
    lock = gc.get_lock(chat_id)
    if lock != gc.LOCK_NONE:
        return f"{_PLAT_FULL[_LOCK_TO_PLAT[lock]]} (قفل)"
    return _PLAT_FULL[platform_pref.get(chat_id)]
