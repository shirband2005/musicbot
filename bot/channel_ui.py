"""پیام‌های کانال لاگ و کانال دیتابیس (آرشیو).

همه با لایه‌ی `bot/ui.py` ساخته می‌شوند: فلش پرمیوم یکی‌درمیان، ارقام فارسی،
بدون `parse_mode`. نسخه‌ی قبلی این پیام‌ها با `**Markdown**` و `•` می‌رفتند و
از بازطراحی جا مانده بودند.
"""
from __future__ import annotations

import time

from bot import ui


# ---------------------------------------------------------------- کمکی
def size_text(nbytes: int) -> str:
    """حجم خوانا: کیلوبایت / مگابایت."""
    n = int(nbytes or 0)
    if n <= 0:
        return "—"
    mb = n / (1024 * 1024)
    if mb >= 1:
        return f"{mb:.1f} مگابایت"
    return f"{n / 1024:.0f} کیلوبایت"


def dur_text(seconds: int) -> str:
    s = int(seconds or 0)
    if s <= 0:
        return "—"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


SOURCE_LABEL = {
    "youtube": "یوتیوب",
    "soundcloud": "ساوندکلاد",
    "archive": "آرشیو",
    "forward": "فوروارد مالک",
    "telegram": "فایل تلگرام",
    "telegram_stream": "استریم تلگرام",
}


def source_text(source: str) -> str:
    return SOURCE_LABEL.get(source or "", source or "—")


# ================================================================ کانال لاگ
def bot_started(username: str, n_chats: int, n_songs: int):
    t = ui.Text().title(ui.EMO_PLAY, ui.BASE_ARROW, "ربات روشن شد")
    t.field(0, "ربات", f"@{username}" if username else "—")
    t.field(1, "گروه‌های ثبت‌شده", ui.fa(n_chats))
    t.field(2, "آهنگ‌های دیتابیس", ui.fa(n_songs))
    return t.text, t.entities


def bot_stopped():
    t = ui.Text().title(ui.EMO_STOP, ui.BASE_ARROW, "ربات خاموش شد")
    return t.text, t.entities


def now_playing(title: str, source: str, group: str, requester: str,
                requester_id: int = 0):
    t = ui.Text().title(ui.EMO_HEADPHONE, ui.BASE_HEADPHONE, "پخش جدید")
    t.field(0, "آهنگ", ui.trunc(title, 40))
    t.field(1, "منبع", source_text(source))
    t.field(2, "گروه", ui.trunc(group, 30))
    if requester_id:
        t.field(3, "درخواست‌کننده", mention=(requester, requester_id))
    else:
        t.field(3, "درخواست‌کننده", requester)
    return t.text, t.entities


def group_added(title: str, chat_id: int, adder: str, adder_id: int = 0):
    t = ui.Text().title(ui.EMO_PLAY, ui.BASE_ARROW, "به گروه جدید اضافه شد")
    t.field(0, "گروه", ui.trunc(title, 34))
    t.field(1, "شناسه", code=str(chat_id))
    if adder_id:
        t.field(2, "توسط", mention=(adder, adder_id))
    elif adder:
        t.field(2, "توسط", adder)
    return t.text, t.entities


def group_removed(title: str, chat_id: int):
    t = ui.Text().title(ui.EMO_STOP, ui.BASE_ARROW, "از گروه حذف شد")
    t.field(0, "گروه", ui.trunc(title, 34))
    t.field(1, "شناسه", code=str(chat_id))
    return t.text, t.entities


# --- رویدادهای اشتراک (قبلاً هیچ‌جا لاگ نمی‌شدند) ---
def sub_activated(group: str, chat_id: int, months: int, method: str,
                  status: str):
    t = ui.Text().title(ui.EMO_BELL, ui.BASE_ARROW, "اشتراک فعال شد")
    t.field(0, "گروه", ui.trunc(group, 30))
    t.field(1, "شناسه", code=str(chat_id))
    t.field(2, "مدت", f"{ui.fa(months)} ماه")
    t.field(3, "روش پرداخت", method)
    t.field(4, "وضعیت", ui.fa(status))
    return t.text, t.entities


def sub_rejected(group: str, chat_id: int, oid: str):
    t = ui.Text().title(ui.EMO_STOP, ui.BASE_ARROW, "سفارش لغو شد")
    t.field(0, "گروه", ui.trunc(group, 30))
    t.field(1, "شناسه", code=str(chat_id))
    t.field(2, "کد سفارش", code=oid)
    return t.text, t.entities


def sub_expired(group: str, chat_id: int):
    t = ui.Text().title(ui.EMO_BELL, ui.BASE_ARROW, "اشتراک منقضی شد")
    t.field(0, "گروه", ui.trunc(group, 30))
    t.field(1, "شناسه", code=str(chat_id))
    t.field(2, "نتیجه", "ربات برای این گروه خاموش شد")
    return t.text, t.entities


def free_access_ended(group: str, chat_id: int):
    t = ui.Text().title(ui.EMO_BELL, ui.BASE_ARROW, "مهلت آزمایشی تمام شد")
    t.field(0, "گروه", ui.trunc(group, 30))
    t.field(1, "شناسه", code=str(chat_id))
    t.field(2, "نتیجه", "ربات برای این گروه خاموش شد")
    return t.text, t.entities


def backup_caption(n_songs: int, n_chats: int = 0):
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "بکاپ دیتابیس")
    t.field(0, "زمان", time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()))
    t.field(1, "آهنگ‌های دیتابیس", ui.fa(n_songs))
    if n_chats:
        t.field(2, "گروه‌ها", ui.fa(n_chats))
    return t.text, t.entities


def restore_blob_caption():
    t = ui.Text().title(ui.EMO_GEAR, ui.BASE_ARROW, "رشته‌ی بازیابی کامل")
    t.add("برای انتقال به سرور جدید، محتوای این فایل را در فیلد ")
    t.code("RESTORE_BLOB")
    t.add(" هنگام دیپلوی بگذار. همه‌ی توکن‌ها و تنظیمات خودکار ساخته می‌شوند.\n\n")
    t.italic("این رشته را محرمانه نگه دار.")
    return t.text, t.entities


# ================================================================ کانال دیتابیس
def song_caption(title: str, performer: str = "", duration: int = 0,
                 file_size: int = 0, source: str = "", url: str = "",
                 n_total: int = 0, is_video: bool = False):
    """کپشن کامل آهنگ در کانال دیتابیس.

    نسخه‌ی قبلی فقط `🎵 {title}` بود — بدون مدت، منبع، حجم یا خواننده.
    """
    icon = ui.EMO_MOVIE if is_video else ui.EMO_HEADPHONE
    base = ui.BASE_MOVIE if is_video else ui.BASE_HEADPHONE
    t = ui.Text().title(icon, base, ui.trunc(title, 40))
    i = 0
    if performer:
        t.field(i, "خواننده", ui.trunc(performer, 30)); i += 1
    t.field(i, "مدت", ui.fa(dur_text(duration))); i += 1
    t.field(i, "حجم", ui.fa(size_text(file_size))); i += 1
    t.field(i, "منبع", source_text(source)); i += 1
    if url:
        t.field(i, "لینک", code=ui.trunc(url, 50)); i += 1
    if n_total:
        t.field(i, "شماره در دیتابیس", ui.fa(n_total))
    return t.text, t.entities


def song_keyboard(key: str):
    """دکمه‌ی حذف زیر هر آهنگ در کانال دیتابیس."""
    return ui.kb([[ui.btn("حذف از دیتابیس", f"arch|del|{_short(key)}", ui.RED,
                          ui.EMO_CLOSE)]])


def confirm_keyboard(key: str):
    """تأیید حذف — تا با یک لمس اشتباه آهنگ پاک نشود."""
    return ui.kb([[ui.btn("بله، حذف کن", f"arch|yes|{_short(key)}", ui.RED),
                   ui.btn("انصراف", f"arch|no|{_short(key)}", ui.BLUE)]])


def _short(key: str) -> str:
    """کلید آرشیو ممکن است بلند باشد؛ callback_data سقف ۶۴ بایت دارد.

    برای کلیدهای بلند از هش کوتاه استفاده می‌شود و نگاشتش در دیتابیس
    با جست‌وجوی پیشوندی پیدا می‌شود.
    """
    import hashlib
    if len(key.encode()) <= 40:
        return key
    return "h:" + hashlib.sha1(key.encode()).hexdigest()[:16]


def song_deleted(title: str, n_total: int):
    t = ui.Text().title(ui.EMO_CLOSE, ui.BASE_ARROW, "از دیتابیس حذف شد")
    t.field(0, "آهنگ", ui.trunc(title, 40))
    t.field(1, "باقی‌مانده", f"{ui.fa(n_total)} آهنگ")
    return t.text, t.entities


def song_added_log(title: str, source: str, n_total: int):
    t = ui.Text().title(ui.EMO_PLAY, ui.BASE_ARROW, "آهنگ به دیتابیس اضافه شد")
    t.field(0, "آهنگ", ui.trunc(title, 40))
    t.field(1, "منبع", source_text(source))
    t.field(2, "مجموع دیتابیس", f"{ui.fa(n_total)} آهنگ")
    return t.text, t.entities


def forward_processing(title: str):
    """پیام موقت هنگام پردازش فوروارد مالک."""
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "در حال پردازش فوروارد")
    t.field(0, "آهنگ", ui.trunc(title, 40))
    t.add("\n")
    t.italic("دانلود و ارسال مجدد با اطلاعات کامل...")
    return t.text, t.entities
