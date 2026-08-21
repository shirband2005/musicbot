"""تنظیمات هر گروه: روشن/خاموش بودن پلیر + قفل پلتفرم.

- پیش‌فرض: پلیر برای هیچ گروهی روشن نیست (مالک باید «موزیک پلیر روشن» بزند).
- قفل پلتفرم: none (هر دو، دکمه پلتفرم در پنل هست) | youtube | soundcloud
  (قفل‌شده → دکمه پلتفرم در پنل نیست و مود ثابت است).
همه در جدول اختصاصی group_settings دیتابیس ذخیره می‌شود (پایدار).
"""
from bot import database as db

LOCK_NONE = "none"        # هر دو منبع، دکمه پلتفرم در پنل هست و قابل تغییر است
LOCK_YOUTUBE = "youtube"  # فقط یوتیوب، بدون دکمه پلتفرم
LOCK_SOUNDCLOUD = "soundcloud"  # فقط ساوندکلاد، بدون دکمه پلتفرم


# ---- روشن/خاموش پلیر برای گروه ----
def is_enabled(chat_id: int) -> bool:
    return db.group_get(chat_id)["enabled"] == 1


def set_enabled(chat_id: int, on: bool) -> None:
    db.group_set(chat_id, enabled=1 if on else 0)


# ---- قفل پلتفرم برای گروه ----
def get_lock(chat_id: int) -> str:
    v = db.group_get(chat_id)["lock"]
    return v if v in (LOCK_YOUTUBE, LOCK_SOUNDCLOUD) else LOCK_NONE


def set_lock(chat_id: int, lock: str) -> None:
    db.group_set(chat_id, lock=lock)


def is_locked(chat_id: int) -> bool:
    return get_lock(chat_id) != LOCK_NONE


# ---- حالت پخش برای گروه: queue | repeat | random ----
MODE_QUEUE = "queue"    # پخش صف: تمام شد → بعدی (پیش‌فرض)
MODE_REPEAT = "repeat"  # پخش تکرار: همان آهنگ دوباره
MODE_RANDOM = "random"  # پخش رندوم: آهنگ تصادفی از آرشیو کانال
_MODES = (MODE_QUEUE, MODE_REPEAT, MODE_RANDOM)


def get_mode(chat_id: int) -> str:
    v = db.group_get(chat_id)["mode"]
    return v if v in _MODES else MODE_QUEUE


def set_mode(chat_id: int, mode: str) -> None:
    if mode in _MODES:
        db.group_set(chat_id, mode=mode)
