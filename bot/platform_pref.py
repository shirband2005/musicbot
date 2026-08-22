"""ترجیح روش جست‌وجوی هر گروه: دیتابیس (ربات جستجو) / یوتیوب / ساوندکلاد.

سه روش (تصمیم کاربر — حالت «هر دو» حذف و «دیتابیس» جایش آمد):

  · DATABASE   — از طریق ربات جستجوی خودمان (inline) در گروه جستجو.
                 یوزربات کمکی inline query می‌زند، نتیجه را می‌گیرد، فایل را
                 در گروه جستجو می‌فرستد و دانلود می‌کند. اگر جواب نداد،
                 fallback به یوتیوب.
  · YOUTUBE    — مستقیم از یوتیوب دانلود و استریم (بدون امتحان ساوندکلاد).
  · SOUNDCLOUD — اول خودِ دستور را در ساوندکلاد جست‌وجو می‌کند؛ اگر پیدا نشد،
                 اسم دقیق را از یوتیوب می‌گیرد و با آن اسم دوباره ساوندکلاد.

هر سه روش **اول کانال دیتابیس خودمان** را چک می‌کنند؛ اگر آهنگ آنجا بود،
بدون دانلود از تلگرام بازیابی می‌شود.
"""
from bot import database as db

# حالت‌ها به‌ترتیب چرخش دکمه
DATABASE = "database"        # ربات جستجوی خودمان (روش پیش‌فرض)
YOUTUBE = "youtube"          # فقط یوتیوب
SOUNDCLOUD = "soundcloud"    # ساوندکلاد (با کمک اسم یوتیوب)

# نام قدیمی که در دیتابیس گروه‌های موجود ذخیره شده است
LEGACY_BOTH = "both"

_ORDER = [DATABASE, YOUTUBE, SOUNDCLOUD]

_LABEL = {
    DATABASE: "پلتفرم: دیتابیس",
    YOUTUBE: "پلتفرم: یوتیوب",
    SOUNDCLOUD: "پلتفرم: ساوند کلاد",
}


def get(chat_id: int) -> str:
    """روش جست‌وجوی این گروه. مقدار قدیمی `both` به `database` نگاشت می‌شود."""
    v = db.group_get(chat_id)["platform"]
    if v == LEGACY_BOTH:
        return DATABASE
    return v if v in _ORDER else DATABASE


def effective(chat_id: int) -> str:
    """مود مؤثر با در نظر گرفتن قفل پلتفرمِ گروه.

    اگر مالک پلتفرم را قفل کرده باشد (فقط یوتیوب / فقط ساوندکلاد)، همان قفل
    برمی‌گردد و انتخاب کاربر نادیده گرفته می‌شود.
    """
    from bot import group_config as gc
    lock = gc.get_lock(chat_id)
    if lock == gc.LOCK_YOUTUBE:
        return YOUTUBE
    if lock == gc.LOCK_SOUNDCLOUD:
        return SOUNDCLOUD
    return get(chat_id)


def cycle(chat_id: int) -> str:
    """به حالت بعدی می‌رود و ذخیره می‌کند؛ حالت جدید را برمی‌گرداند."""
    cur = get(chat_id)
    nxt = _ORDER[(_ORDER.index(cur) + 1) % len(_ORDER)]
    db.group_set(chat_id, platform=nxt)
    return nxt


def label(chat_id: int) -> str:
    return _LABEL[get(chat_id)]
