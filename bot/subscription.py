"""منطق اشتراک: پلن‌ها، تیرها، قیمت‌ها، فعال‌سازی و انقضا.

- تیرها: basic (پایه) | pro (حرفه‌ای)
- مدت‌ها: ۱/۳/۶ ماه یا دائمی (months=0)
- قیمت‌ها و تنظیمات پرداخت در جدول pay_settings (قابل ویرایش از پنل مالک).
"""
import time

from bot import database as db

MONTH = 30 * 24 * 3600  # ثانیه در یک ماه (۳۰ روز)

TIER_BASIC = "basic"
TIER_PRO = "pro"

TIER_LABEL = {TIER_BASIC: "پایه", TIER_PRO: "حرفه‌ای"}

# مدت‌های قابل خرید: (months, برچسب). months=0 یعنی دائمی.
DURATIONS = [(1, "۱ ماهه"), (3, "۳ ماهه"), (6, "۶ ماهه"), (0, "دائمی")]

# کلید قیمت در pay_settings: price_<tier>_<months>_<stars|toman>
# پیش‌فرض‌ها (مالک از پنل تغییر می‌دهد). Stars عدد صحیح، تومان عدد صحیح.
_DEFAULT_PRICES = {
    "basic_1": {"stars": 50, "toman": 50000},
    "basic_3": {"stars": 120, "toman": 120000},
    "basic_6": {"stars": 200, "toman": 200000},
    "basic_0": {"stars": 500, "toman": 500000},
    "pro_1": {"stars": 100, "toman": 100000},
    "pro_3": {"stars": 250, "toman": 250000},
    "pro_6": {"stars": 400, "toman": 400000},
    "pro_0": {"stars": 900, "toman": 900000},
}


def plan_key(tier: str, months: int) -> str:
    return f"{tier}_{months}"


def get_price(tier: str, months: int, currency: str) -> int:
    """قیمت پلن به currency ('stars' یا 'toman'). از pay_settings یا پیش‌فرض."""
    key = plan_key(tier, months)
    stored = db.pay_get(f"price_{key}_{currency}")
    if stored:
        try:
            return int(stored)
        except ValueError:
            pass
    return _DEFAULT_PRICES.get(key, {}).get(currency, 0)


def set_price(tier: str, months: int, currency: str, value: int) -> None:
    db.pay_set(f"price_{plan_key(tier, months)}_{currency}", str(int(value)))


def duration_label(months: int) -> str:
    for m, lbl in DURATIONS:
        if m == months:
            return lbl
    return f"{months} ماهه"


# ---------------- وضعیت اشتراک ----------------
def is_active(chat_id: int) -> bool:
    """آیا گروه اشتراک فعال دارد؟ (دائمی یا انقضای در آینده)."""
    sub = db.sub_get(chat_id)
    if not sub:
        return False
    exp = sub.get("expires_at") or 0
    return exp == 0 or exp > time.time()


def get_tier(chat_id: int) -> str:
    sub = db.sub_get(chat_id)
    if sub and is_active(chat_id):
        return sub.get("tier") or TIER_BASIC
    return TIER_BASIC


def is_pro(chat_id: int) -> bool:
    return is_active(chat_id) and get_tier(chat_id) == TIER_PRO


def activate(chat_id: int, tier: str, months: int, buyer_id: int = 0) -> float:
    """اشتراک را فعال/تمدید می‌کند. اگر اشتراک فعال باشد، از انتهای آن تمدید می‌شود.

    برمی‌گرداند: expires_at جدید (0 = دائمی).
    """
    now = time.time()
    if months == 0:
        expires = 0  # دائمی
    else:
        cur = db.sub_get(chat_id)
        base = now
        if cur and cur.get("expires_at", 0) > now:
            base = cur["expires_at"]  # تمدید از انتهای فعلی
        expires = base + months * MONTH
    db.sub_set(chat_id, tier=tier, expires_at=expires,
               buyer_id=buyer_id or (db.sub_get(chat_id) or {}).get("buyer_id", 0),
               started_at=now, last_notified=0)
    return expires


def deactivate(chat_id: int) -> None:
    db.sub_delete(chat_id)


def expires_text(chat_id: int) -> str:
    sub = db.sub_get(chat_id)
    if not sub:
        return "بدون اشتراک"
    exp = sub.get("expires_at") or 0
    if exp == 0:
        return "دائمی"
    if exp <= time.time():
        return "منقضی‌شده"
    days = int((exp - time.time()) / (24 * 3600))
    return f"{days} روز باقی‌مانده"
