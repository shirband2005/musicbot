"""پنل پخش فیلم — نسخه‌ی کمینه‌ی تأییدشده.

تفاوت‌های ساختاری با پنل موزیک (تصمیم کاربر):
  · بدون پلتفرم، بدون حالت پخش، بدون لیست پخش — فیلم صف ندارد
  · ردیف کنترل فقط دو دکمه: مکث/پخش و توقف (قبلی/بعدی بی‌معناست)
  · سه خط متن: وضعیت / نوع / پخش‌کننده (پلتفرم و صدا حذف شدند)
  · آیکون عنوان: 5400030843315960317

    🎬 <عنوان فیلم>
    ◀️ وضعیت : در حال پخش
    ◀️ نوع : فیلم
    ◀️ پخش‌کننده : <نام قابل کلیک>

    [ 24:10 │ ━━◉────────── │ 2:02:00 ]
    [ ⏸ ][ ⏹ ]
    [ 🔉 ][ 100% ][ 🔊 ]
    [ تایمر خواب ]
    [ دریافت فیلم ]
    [ بستن پنل ]
"""
from __future__ import annotations

from typing import Optional

from pyrogram.types import InlineKeyboardMarkup

from bot import panel as panel_mod
from bot import ui
from bot.queue import Track


def content(track: Track, volume: int = 100, muted: bool = False,
            chat_id: int = 0):
    """متن پنل فیلم. برمی‌گرداند (text, entities)."""
    t = ui.Text().title(ui.EMO_MOVIE, ui.BASE_MOVIE, track.title)
    t.field(0, "وضعیت", "متوقف موقت" if track.paused else "در حال پخش")
    t.field(1, "نوع", "فیلم")
    t.field(2, "پخش‌کننده",
            mention=(track.requester, getattr(track, "requester_id", 0) or 0))
    return t.text, t.entities


def keyboard(chat_id: int, track: Track, volume: int = 100, muted: bool = False,
             sleep_left: Optional[float] = None) -> InlineKeyboardMarkup:
    """کیبورد پنل فیلم. الگوی callback: `v|<action>[|<arg>]`."""
    menu = panel_mod.open_menu(chat_id)
    rows = []

    # ۱) نوار زمان (قالب ساعت برای فیلم بلند)
    rows.append([ui.btn(ui.timebar(track.position(), track.duration),
                        "v|refresh", ui.BLUE)])

    # ۲) کنترل: فقط مکث/پخش و توقف — فیلم صف ندارد
    if track.paused:
        play_btn = ui.icon_btn("v|playpause", ui.EMO_PLAY, ui.GREEN)
    else:
        play_btn = ui.icon_btn("v|playpause", ui.EMO_PAUSE, ui.BLUE)
    rows.append([play_btn, ui.icon_btn("v|stop", ui.EMO_STOP, ui.RED)])

    # ۳) صدا — همان قاعده‌ی پنل موزیک
    rows.append([
        ui.icon_btn("v|vol_down", ui.EMO_VOL_DOWN),
        ui.btn("0%" if muted else f"{volume}%", "v|mute",
               ui.RED if muted else ui.PLAIN,
               ui.EMO_MUTE if muted else ui.EMO_UNMUTE),
        ui.icon_btn("v|vol_up", ui.EMO_VOL_UP),
    ])

    # ۴) تایمر خواب — سه وضعیت، همیشه یک ردیف
    if menu == panel_mod.MENU_SLEEP:
        rows.append([ui.btn(lbl, f"v|sleep_set|{m}")
                     for m, lbl in panel_mod.SLEEP_OPTIONS])
    elif sleep_left is not None:
        rows.append([ui.btn(f"تایمر خواب : {ui.countdown(sleep_left)}",
                            "v|sleep_off", ui.RED, ui.EMO_BELL)])
    else:
        rows.append([ui.btn("تایمر خواب", "v|sleep_open", ui.PLAIN,
                            ui.EMO_BELL_OFF)])

    # ۵) دریافت فیلم
    rows.append([ui.btn("دریافت فیلم", "v|getmedia", ui.PLAIN, ui.EMO_DOWNLOAD)])

    # ۶) بستن
    rows.append([ui.btn("بستن پنل", "v|close", ui.RED, ui.EMO_CLOSE)])
    return ui.kb(rows)
