"""ترجیح پلتفرم جست‌وجو برای هر گروه (یوتیوب+ساوندکلاد / یوتیوب / ساوندکلاد)."""
from bot import database as db

# حالت‌ها به‌ترتیب چرخش دکمه
BOTH = "both"        # اول ساوندکلاد، اگر نبود یوتیوب
YOUTUBE = "youtube"  # فقط یوتیوب
SOUNDCLOUD = "soundcloud"  # فقط ساوندکلاد

_ORDER = [BOTH, YOUTUBE, SOUNDCLOUD]

_LABEL = {
    BOTH: "پلتفرم: یوتیوب + ساوند کلاد",
    YOUTUBE: "پلتفرم: یوتیوب",
    SOUNDCLOUD: "پلتفرم: ساوند کلاد",
}


def get(chat_id: int) -> str:
    v = db.get_setting(f"platform_{chat_id}", BOTH)
    return v if v in _ORDER else BOTH


def cycle(chat_id: int) -> str:
    """به حالت بعدی می‌رود و ذخیره می‌کند؛ حالت جدید را برمی‌گرداند."""
    cur = get(chat_id)
    nxt = _ORDER[(_ORDER.index(cur) + 1) % len(_ORDER)]
    db.set_setting(f"platform_{chat_id}", nxt)
    return nxt


def label(chat_id: int) -> str:
    return _LABEL[get(chat_id)]
