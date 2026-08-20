"""فیلتر دستورات فارسی چندکلمه‌ای (با یا بدون پیشوند / . ! ،).

برخلاف filters.command که فقط دستور تک‌کلمه‌ای با اسلش را می‌فهمد،
این فیلتر عبارت‌های فارسی چندکلمه‌ای مثل «پخش اهنگ» یا «صف پخش» را هم
در ابتدای متن پیام تشخیص می‌دهد و بقیه‌ی متن را به‌عنوان آرگومان جدا می‌کند.
"""
import re

from pyrogram import filters
from pyrogram.types import Message

_PREFIXES = ("/", ".", "!", "،")


def normalize(text: str) -> str:
    """یکسان‌سازی نویسه‌های عربی/فارسی برای تطبیق مطمئن‌تر."""
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = text.replace("آ", "ا").replace("أ", "ا").replace("إ", "ا").replace("ٱ", "ا")
    text = text.replace("ة", "ه").replace("ﻻ", "لا")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fa_command(phrases):
    """ساخت فیلتر برای مجموعه‌ای از عبارت‌های فارسی معادل یک دستور.

    عبارت منطبق (نرمال‌شده) در message.command[0] و آرگومان‌ها (متن اصلی)
    در message.command[1:] قرار می‌گیرند.
    """
    norm_phrases = sorted({normalize(p) for p in phrases}, key=lambda p: -len(p.split()))

    async def func(flt, _, message: Message) -> bool:
        text = message.text or message.caption
        if not text:
            return False
        s = text.strip()
        # حذف یک پیشوند اختیاری از ابتدای متن
        for pfx in _PREFIXES:
            if s.startswith(pfx):
                s = s[len(pfx):].strip()
                break
        words = s.split()
        if not words:
            return False
        nwords = [normalize(w) for w in words]
        for phrase in flt.phrases:
            pw = phrase.split()
            k = len(pw)
            if len(words) >= k and nwords[:k] == pw:
                # command[0] = عبارت منطبق، command[1:] = آرگومان‌های اصلی
                message.command = [phrase] + words[k:]
                return True
        return False

    return filters.create(func, phrases=norm_phrases)
