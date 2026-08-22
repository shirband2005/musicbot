"""لایه‌ی ظاهر ربات — تنها منبع حقیقت برای متن، دکمه و رنگ.

هر پنل و پیامی که کاربر می‌بیند از همین ماژول ساخته می‌شود. اگر ظاهری باید
عوض شود، اینجا عوض می‌شود نه در پلاگین‌ها.

قواعد ثابت (تصمیم‌های تأییدشده‌ی طراحی):
  · نوار زمان: تک‌دکمه‌ی تمام‌عرض آبی → `01:34 │ ━━━━◉──────── │ 04:12`
  · خطوط متن: فلش چپ پرمیوم یکی‌درمیان (آبی، قرمز، آبی، ...)
  · رنگ: قرمز=عقب/توقف/خطر · سبز=جلو/تأیید · آبی=کنش اصلی · بی‌رنگ=خنثی
  · هر خطا سه چیز می‌گوید: چه شد، چرا، چه کار کنم
  · خطای خام پایتون هرگز به کاربر نشان داده نمی‌شود (کد خطا به کاربر، متن به لاگ)

نکته‌ی فنی حیاتی: تلگرام طول entity را با **UTF-16 code unit** می‌شمرد، نه با
len پایتون. همه‌ی محاسبات آفست از `_u16` می‌گذرد. همچنین اگر `parse_mode` بدهی،
تلگرام آرگومان `entities` را نادیده می‌گیرد — پس هرگز این دو را با هم نفرست.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, Optional

from pyrogram import enums
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MessageEntity,
)

# ---------------------------------------------------------------- رنگ دکمه‌ها
BLUE = enums.ButtonStyle.PRIMARY
GREEN = enums.ButtonStyle.SUCCESS
RED = enums.ButtonStyle.DANGER
PLAIN = enums.ButtonStyle.DEFAULT      # بی‌رنگ (پیش‌فرض اپ)

# کاراکتر بی‌عرض برای دکمه‌های فقط-آیکون (تلگرام text خالی نمی‌پذیرد)
ZW = "\u200b"

# ---------------------------------------------------------- ایموجی پرمیوم
# عنوان پنل‌ها
EMO_HEADPHONE = "5262852255056417213"     # پنل موزیک
EMO_MOVIE = "5400030843315960317"         # پنل فیلم

# نشانگر خطوط متن (یکی‌درمیان)
EMO_ARROW_BLUE = "5870464843244378597"
EMO_ARROW_RED = "5870598141849377961"

# کنترل پخش
EMO_PLAY = "5321436910348942569"
EMO_PAUSE = "5202196261591071609"
EMO_STOP = "5323734662017727761"
EMO_NEXT = "5321300317504030049"
EMO_PREV = "5321532361702127913"

# صدا
EMO_MUTE = "5346075393969398240"
EMO_UNMUTE = "5346065893501740092"
EMO_VOL_UP = "5343818032173064183"
EMO_VOL_DOWN = "5345899227295817212"

# حالت پخش
EMO_REPEAT = "5345935545539267974"
EMO_SHUFFLE = "5343819397972668777"
EMO_LIST = "4969829017524896906"

# ناوبری و ابزار
EMO_CLOSE = "5345857527458339814"
EMO_BACK = "5343677548087780533"
EMO_GEAR = "5345802049365778252"
EMO_SEARCH = "5343927472234734763"
EMO_DOWNLOAD = "5188563846415014158"
EMO_BELL = "5345799927651934809"           # تایمر فعال
EMO_BELL_OFF = "5343959916417688307"       # تایمر خاموش

# پلتفرم
EMO_YOUTUBE = "5438350726214484980"
EMO_SOUNDCLOUD = "5438167966766103342"
EMO_DATABASE = "5890849007139296140"       # روش «دیتابیس» (ربات جستجو)
EMO_BOTH = "5222353152996578577"           # (منسوخ) حالت «هر دو» — جایش دیتابیس آمد

# کاراکترهای پایه — کاربران بدون پرمیوم همین‌ها را می‌بینند
BASE_ARROW = "◀️"
BASE_HEADPHONE = "🎧"
BASE_MOVIE = "🎬"

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


# ---------------------------------------------------------------- کمکی‌ها
def _u16(s: str) -> int:
    """طول رشته برحسب UTF-16 code unit (مبنای شمارش تلگرام)."""
    return len(s.encode("utf-16-le")) // 2


def fa(value) -> str:
    """ارقام لاتین → فارسی، با جداکننده‌ی هزار برای اعداد صحیح."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}".translate(_FA_DIGITS)
    return str(value).translate(_FA_DIGITS)


def alt_arrow(i: int) -> str:
    """فلش یکی‌درمیان: زوج=آبی، فرد=قرمز."""
    return EMO_ARROW_BLUE if i % 2 == 0 else EMO_ARROW_RED


def clock(seconds) -> str:
    """ثانیه → mm:ss یا h:mm:ss (ارقام لاتین؛ برای نوار زمان)."""
    sec = int(max(0, seconds or 0))
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def trunc(s: str, limit: int = 38) -> str:
    """کوتاه‌کردن عنوان بلند با «…» (برای برچسب دکمه و خطوط لیست)."""
    s = (s or "").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


# ---------------------------------------------------------------- نوار زمان
def timebar(position, duration, length: int = 12) -> str:
    """نوار زمان تک‌دکمه‌ای: `01:34 │ ━━━━◉──────── │ 04:12`.

    duration صفر/None یعنی استریم زنده → نوار معنا ندارد.
    """
    if not duration:
        return f"🔴 زنده  │  {clock(position)}"
    filled = int(length * (position or 0) / duration)
    filled = max(0, min(length, filled))
    bar = "━" * filled + "◉" + "─" * (length - filled)
    return f"{clock(position)} │ {bar} │ {clock(duration)}"


def countdown(seconds) -> str:
    """زمان باقی‌مانده‌ی تایمر خواب: m:ss یا h:mm:ss."""
    sec = int(max(0, seconds or 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------------------------------------------------------------- دکمه‌ها
def btn(
    label: str,
    callback: Optional[str] = None,
    style=PLAIN,
    icon: Optional[str] = None,
    url: Optional[str] = None,
    copy: Optional[str] = None,
) -> InlineKeyboardButton:
    """سازنده‌ی دکمه. دقیقاً یکی از callback/url/copy باید داده شود.

    icon = شناسه‌ی ایموجی پرمیوم (فقط یکی؛ تلگرام دو آیکون نمی‌پذیرد).
    """
    kwargs = {"text": label, "style": style}
    if icon:
        kwargs["icon_custom_emoji_id"] = icon
    if url:
        kwargs["url"] = url
    elif copy:
        kwargs["copy_text"] = copy
    else:
        kwargs["callback_data"] = callback
    return InlineKeyboardButton(**kwargs)


def icon_btn(callback: str, icon: str, style=PLAIN) -> InlineKeyboardButton:
    """دکمه‌ی فقط-آیکون (بدون متن) — برای ردیف کنترل پخش."""
    return btn(ZW, callback, style, icon)


def kb(rows: Iterable[Iterable[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    """ردیف‌های خالی را حذف می‌کند تا کیبورد ناقص نسازیم."""
    clean = [list(r) for r in rows if r]
    return InlineKeyboardMarkup(clean)


def nav_row(back: Optional[str] = None, close: Optional[str] = None):
    """ردیف ناوبری یکسان در همه‌ی پنل‌ها: بازگشت(بی‌رنگ) + بستن(قرمز)."""
    row = []
    if back:
        row.append(btn("بازگشت", back, PLAIN, EMO_BACK))
    if close:
        row.append(btn("بستن", close, RED, EMO_CLOSE))
    return row


# ---------------------------------------------------------------- متن + entities
class Text:
    """سازنده‌ی متن همراه entities (بولد/کد/ایتالیک/ایموجی پرمیوم/منشن).

    چرا کلاس؟ چون آفست هر entity باید برحسب UTF-16 و نسبت به متن ساخته‌شده
    تا آن لحظه حساب شود؛ دستی نوشتنش منبع باگ است.

    استفاده:
        t = Text().emoji(EMO_HEADPHONE, BASE_HEADPHONE).add(" ").bold(title)
        await msg.reply_text(t.text, entities=t.entities)   # بدون parse_mode!
    """

    __slots__ = ("text", "entities")

    def __init__(self) -> None:
        self.text: str = ""
        self.entities: list[MessageEntity] = []

    # --- پایه ---
    def add(self, s: str) -> "Text":
        self.text += s
        return self

    def _mark(self, s: str, etype, **extra) -> "Text":
        off, ln = _u16(self.text), _u16(s)
        self.entities.append(MessageEntity(type=etype, offset=off, length=ln, **extra))
        self.text += s
        return self

    # --- قالب‌ها ---
    def bold(self, s: str) -> "Text":
        return self._mark(s, enums.MessageEntityType.BOLD)

    def italic(self, s: str) -> "Text":
        return self._mark(s, enums.MessageEntityType.ITALIC)

    def code(self, s: str) -> "Text":
        """متن قابل کپی با یک لمس — برای دستورها، شماره کارت، کد سفارش."""
        return self._mark(s, enums.MessageEntityType.CODE)

    def emoji(self, emoji_id: str, base: str = BASE_ARROW) -> "Text":
        """ایموجی پرمیوم؛ `base` همان چیزی است که کاربر غیرپرمیوم می‌بیند."""
        return self._mark(
            base, enums.MessageEntityType.CUSTOM_EMOJI, custom_emoji_id=emoji_id
        )

    def mention(self, name: str, user_id: int) -> "Text":
        """نام قابل کلیک بدون نیاز به یوزرنیم (text_mention با شناسه‌ی عددی).

        اگر user_id نداشته باشیم، نام ساده اضافه می‌شود (تخریب بی‌صدا نداریم).
        """
        if not user_id:
            return self.add(name)
        from pyrogram.types import User

        return self._mark(
            name,
            enums.MessageEntityType.TEXT_MENTION,
            user=User(id=user_id, first_name=name),
        )

    # --- الگوهای تکرارشونده ---
    def title(self, icon: str, base: str, text: str) -> "Text":
        """سرصفحه‌ی پنل: آیکون پرمیوم + عنوان بولد + یک خط خالی."""
        return self.emoji(icon, base).add(" ").bold(text).add("\n\n")

    def field(self, i: int, label: str, value=None, *, code=None, mention=None) -> "Text":
        """یک خط اطلاعات با فلش یکی‌درمیان: `◀️ برچسب : مقدار`."""
        self.emoji(alt_arrow(i)).add(f" {label} : ")
        if code is not None:
            self.code(str(code))
        elif mention is not None:
            self.mention(mention[0], mention[1])
        else:
            self.add(str(value))
        return self.add("\n")

    def line(self, i: int, text: str) -> "Text":
        """خط ساده با فلش (بدون برچسب/مقدار) — برای توضیح و گام‌ها."""
        return self.emoji(alt_arrow(i)).add(f" {text}\n")

    def why(self, text: str) -> "Text":
        """علت خطا — همیشه فلش قرمز."""
        return self.emoji(EMO_ARROW_RED).add(f" {text}\n")

    def how(self, text: str) -> "Text":
        """راه‌حل — همیشه فلش آبی."""
        return self.emoji(EMO_ARROW_BLUE).add(f" {text}\n")


# ---------------------------------------------------------------- امضای رفرش
def signature(text: str, markup: Optional[InlineKeyboardMarkup]) -> str:
    """هش محتوای یک پیام (متن + برچسب/رنگ/آیکون دکمه‌ها).

    برای رفرش شرطی: اگر امضا با قبلی یکی بود، ادیت نزن. تلگرام در این حالت
    خطای «message is not modified» می‌دهد و درخواست هدر می‌رود؛ با نوار زمانی
    که هر ۵ ثانیه رفرش می‌شود، این صرفه‌جویی حدود ۸۰٪ درخواست‌ها است.
    """
    parts = [text or ""]
    if markup is not None:
        for row in markup.inline_keyboard:
            for b in row:
                parts.append(
                    "|".join(
                        [
                            b.text or "",
                            str(getattr(b, "callback_data", "") or ""),
                            str(getattr(b, "style", "") or ""),
                            str(getattr(b, "icon_custom_emoji_id", "") or ""),
                            str(getattr(b, "url", "") or ""),
                        ]
                    )
                )
            parts.append("//")
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()
