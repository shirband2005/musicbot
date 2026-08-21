"""تنظیمات هر گروه: روشن/خاموش بودن پلیر + قفل پلتفرم.

- پیش‌فرض: پلیر برای هیچ گروهی روشن نیست (مالک باید «موزیک پلیر روشن» بزند).
- قفل پلتفرم: none (هر دو، دکمه پلتفرم در پنل هست) | youtube | soundcloud
  (قفل‌شده → دکمه پلتفرم در پنل نیست و مود ثابت است).
همه در جدول settings دیتابیس ذخیره می‌شود (پایدار).
"""
from bot import database as db

# ---- روشن/خاموش پلیر برای گروه ----
def is_enabled(chat_id: int) -> bool:
    return db.get_setting(f"player_on_{chat_id}") == "1"


def set_enabled(chat_id: int, on: bool) -> None:
    db.set_setting(f"player_on_{chat_id}", "1" if on else "0")


# ---- قفل پلتفرم برای گروه ----
LOCK_NONE = "none"        # هر دو منبع، دکمه پلتفرم در پنل هست و قابل تغییر است
LOCK_YOUTUBE = "youtube"  # فقط یوتیوب، بدون دکمه پلتفرم
LOCK_SOUNDCLOUD = "soundcloud"  # فقط ساوندکلاد، بدون دکمه پلتفرم


def get_lock(chat_id: int) -> str:
    v = db.get_setting(f"player_lock_{chat_id}")
    return v if v in (LOCK_YOUTUBE, LOCK_SOUNDCLOUD) else LOCK_NONE


def set_lock(chat_id: int, lock: str) -> None:
    db.set_setting(f"player_lock_{chat_id}", lock)


def is_locked(chat_id: int) -> bool:
    return get_lock(chat_id) != LOCK_NONE
