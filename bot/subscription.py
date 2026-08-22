"""منطق اشتراک — طرح واحد، بدون تیر.

تصمیم‌های تأییدشده‌ی کاربر:
  · تیرها (پایه/حرفه‌ای) حذف شدند؛ یک طرح واحد با سه مدت: ۱، ۲، ۳ ماه
  · سه روش پرداخت، هر کدام واحد پول خودش: کارت (تومان)، کریپتو (دلار)، استارز
  · تمدید روی اشتراک فعال از **انتهای** آن اضافه می‌شود، نه از امروز
  · مکث اشتراک: زمان باقی‌مانده یخ می‌زند و با ادامه از همان‌جا می‌رود
  · با پایان اشتراک، ربات برای آن گروه از کار می‌افتد
  · تاریخ فقط «N روز مانده» نمایش داده می‌شود (بدون تاریخ شمسی)
"""
from __future__ import annotations

import time
from typing import Optional

from bot import database as db

DAY = 24 * 3600
MONTH = 30 * DAY

# مدت‌های قابل خرید (ماه) — ترتیب نمایش همین است
DURATIONS = (1, 2, 3)

DURATION_LABEL = {1: "۱ ماهه", 2: "۲ ماهه", 3: "۳ ماهه"}

# روش‌های پرداخت و واحد پولشان
METHOD_CARD = "card"
METHOD_CRYPTO = "crypto"
METHOD_STARS = "stars"
METHODS = (METHOD_CARD, METHOD_CRYPTO, METHOD_STARS)

METHOD_LABEL = {
    METHOD_CARD: "کارت به کارت",
    METHOD_CRYPTO: "کریپتو (USDT)",
    METHOD_STARS: "استارز تلگرام",
}
CURRENCY_LABEL = {
    METHOD_CARD: "تومان",
    METHOD_CRYPTO: "دلار",
    METHOD_STARS: "استارز",
}

# قیمت‌های پیش‌فرض (مالک از پنل مدیریت فروش عوض می‌کند).
# کلید pay_settings: price_<method>_<months>
_DEFAULT_PRICES = {
    METHOD_CARD: {1: 120_000, 2: 220_000, 3: 300_000},
    METHOD_CRYPTO: {1: 1.5, 2: 2.7, 3: 3.6},
    METHOD_STARS: {1: 100, 2: 180, 3: 240},
}

# کلیدهای تنظیمات پرداخت
KEY_WALLET = "crypto_wallet"
KEY_NETWORK = "crypto_network"
DEFAULT_NETWORK = "TRC20 (TRON)"


def duration_label(months: int) -> str:
    return DURATION_LABEL.get(months, f"{months} ماهه")


# ---------------------------------------------------------------- قیمت‌ها
def _price_key(method: str, months: int) -> str:
    return f"price_{method}_{months}"


def get_price(method: str, months: int):
    """قیمت این مدت با این روش. کریپتو اعشاری است، بقیه صحیح."""
    raw = db.pay_get(_price_key(method, months))
    if raw:
        try:
            return float(raw) if method == METHOD_CRYPTO else int(float(raw))
        except ValueError:
            pass
    return _DEFAULT_PRICES.get(method, {}).get(months, 0)


def set_price(method: str, months: int, value) -> None:
    if method == METHOD_CRYPTO:
        db.pay_set(_price_key(method, months), str(float(value)))
    else:
        db.pay_set(_price_key(method, months), str(int(value)))


def price_text(method: str, months: int) -> str:
    """قیمت با واحد، آماده‌ی نمایش (ارقام فارسی در لایه‌ی ui اعمال می‌شود)."""
    p = get_price(method, months)
    unit = CURRENCY_LABEL[method]
    if method == METHOD_CRYPTO:
        return f"{p} {unit}"
    return f"{p:,} {unit}"


# ---------------------------------------------------------------- روش‌ها
def method_enabled(method: str) -> bool:
    """روش خاموش‌شده در پنل خرید به کاربر نشان داده نمی‌شود."""
    return db.pay_get(f"method_{method}_on", "1") != "0"


def set_method_enabled(method: str, on: bool) -> None:
    db.pay_set(f"method_{method}_on", "1" if on else "0")


def enabled_methods() -> list:
    return [m for m in METHODS if method_enabled(m)]


def wallet() -> str:
    return db.pay_get(KEY_WALLET, "")


def set_wallet(addr: str) -> None:
    db.pay_set(KEY_WALLET, addr.strip())


def network() -> str:
    return db.pay_get(KEY_NETWORK, DEFAULT_NETWORK)


def set_network(net: str) -> None:
    db.pay_set(KEY_NETWORK, net.strip())


# ---------------------------------------------------------------- وضعیت
def is_paused(chat_id: int) -> bool:
    sub = db.sub_get(chat_id)
    return bool(sub and (sub.get("paused_at") or 0) > 0)


def is_active(chat_id: int) -> bool:
    """اشتراک فعال است؟ اشتراک مکث‌شده فعال **نیست** (ربات خاموش است).

    مکث یعنی مالک موقتاً سرویس را قطع کرده؛ زمان باقی‌مانده مصرف نمی‌شود.
    """
    sub = db.sub_get(chat_id)
    if not sub:
        return False
    if (sub.get("paused_at") or 0) > 0:
        return False
    exp = sub.get("expires_at") or 0
    return exp == 0 or exp > time.time()


def has_subscription(chat_id: int) -> bool:
    """رکورد اشتراک وجود دارد (حتی منقضی یا مکث‌شده)."""
    return db.sub_get(chat_id) is not None


def is_expired(chat_id: int) -> bool:
    sub = db.sub_get(chat_id)
    if not sub:
        return False
    if (sub.get("paused_at") or 0) > 0:
        return False
    exp = sub.get("expires_at") or 0
    return exp != 0 and exp <= time.time()


def seconds_left(chat_id: int) -> Optional[float]:
    """ثانیه‌ی باقی‌مانده. None = بدون اشتراک · float('inf') = دائمی."""
    sub = db.sub_get(chat_id)
    if not sub:
        return None
    exp = sub.get("expires_at") or 0
    if exp == 0:
        return float("inf")
    paused = sub.get("paused_at") or 0
    ref = paused if paused > 0 else time.time()
    return max(0.0, exp - ref)


def days_left(chat_id: int) -> Optional[int]:
    left = seconds_left(chat_id)
    if left is None:
        return None
    if left == float("inf"):
        return -1              # علامت دائمی
    return int(left // DAY)


def status_text(chat_id: int) -> str:
    """وضعیت خوانا برای پنل‌ها — فقط «N روز مانده»، بدون تاریخ شمسی."""
    sub = db.sub_get(chat_id)
    if not sub:
        return "بدون اشتراک"
    d = days_left(chat_id)
    if d == -1:
        return "دائمی"
    if is_paused(chat_id):
        return f"مکث‌شده ({d} روز مانده)"
    if is_expired(chat_id):
        return "منقضی شده"
    return f"{d} روز مانده"


# ---------------------------------------------------------------- فعال‌سازی
def activate(chat_id: int, months: int, buyer_id: int = 0) -> float:
    """اشتراک را فعال یا تمدید می‌کند و expires_at جدید را برمی‌گرداند.

    تمدید روی اشتراک فعال از انتهای آن اضافه می‌شود تا روزی از کاربر سوخت نشود.
    """
    now = time.time()
    cur = db.sub_get(chat_id)
    base = now
    if cur:
        exp = cur.get("expires_at") or 0
        if exp == 0:
            return 0.0                      # دائمی است؛ تمدید معنا ندارد
        paused = cur.get("paused_at") or 0
        if paused > 0:
            # مکث‌شده: از انتهای یخ‌زده تمدید کن و مکث را نگه دار
            base = max(exp, now)
        elif exp > now:
            base = exp                      # فعال: از انتهای فعلی
    expires = base + int(months) * MONTH
    db.sub_set(
        chat_id,
        expires_at=expires,
        buyer_id=buyer_id or (cur or {}).get("buyer_id", 0),
        started_at=(cur or {}).get("started_at") or now,
        last_notified=0,
    )
    return expires


def add_days(chat_id: int, days: int) -> Optional[float]:
    """کم/زیاد کردن دستی روز توسط مالک. None اگر اشتراکی نبود."""
    sub = db.sub_get(chat_id)
    if not sub:
        return None
    exp = sub.get("expires_at") or 0
    if exp == 0:
        return 0.0                          # دائمی
    base = max(exp, time.time()) if days > 0 else exp
    new_exp = max(time.time(), base + days * DAY)
    db.sub_set(chat_id, expires_at=new_exp)
    return new_exp


def make_permanent(chat_id: int) -> None:
    db.sub_set(chat_id, expires_at=0, paused_at=0)


def pause(chat_id: int) -> bool:
    """اشتراک را مکث می‌کند (زمان باقی‌مانده یخ می‌زند). False اگر نشد."""
    sub = db.sub_get(chat_id)
    if not sub or (sub.get("paused_at") or 0) > 0:
        return False
    db.sub_set(chat_id, paused_at=time.time())
    return True


def resume(chat_id: int) -> bool:
    """ادامه‌ی اشتراک مکث‌شده: انقضا به اندازه‌ی مدت مکث جلو می‌رود."""
    sub = db.sub_get(chat_id)
    if not sub:
        return False
    paused = sub.get("paused_at") or 0
    if paused <= 0:
        return False
    exp = sub.get("expires_at") or 0
    if exp > 0:
        db.sub_set(chat_id, expires_at=exp + (time.time() - paused), paused_at=0)
    else:
        db.sub_set(chat_id, paused_at=0)
    return True


def cancel(chat_id: int) -> None:
    db.sub_delete(chat_id)


# ---------------------------------------------------------------- مهلت آزمایشی
def free_until(chat_id: int) -> float:
    """مهلت روشن ماندن بدون اشتراک (۰ = بدون مهلت)."""
    return float(db.group_get(chat_id).get("free_until") or 0)


def free_days_left(chat_id: int) -> int:
    fu = free_until(chat_id)
    if fu <= 0:
        return 0
    return max(0, int((fu - time.time()) // DAY))


def has_free_access(chat_id: int) -> bool:
    fu = free_until(chat_id)
    return fu > 0 and fu > time.time()


def set_free_days(chat_id: int, days: int) -> float:
    """مهلت آزمایشی را تنظیم می‌کند. days<=0 یعنی حذف مهلت."""
    if days <= 0:
        db.group_set(chat_id, free_until=0)
        return 0.0
    until = time.time() + days * DAY
    db.group_set(chat_id, free_until=until)
    return until


def add_free_days(chat_id: int, days: int) -> float:
    cur = free_until(chat_id)
    base = max(cur, time.time()) if days > 0 else cur
    if base <= 0:
        base = time.time()
    until = max(time.time(), base + days * DAY)
    if until <= time.time():
        until = 0.0
    db.group_set(chat_id, free_until=until)
    return until


def set_unlimited_free(chat_id: int) -> None:
    """بدون مهلت (نامحدود) — با عدد بسیار دور نشان داده می‌شود."""
    db.group_set(chat_id, free_until=time.time() + 3650 * DAY)


# ---------------------------------------------------------------- مجوز پخش
def can_play(chat_id: int) -> bool:
    """آیا ربات در این گروه اجازه‌ی پخش دارد؟

    اشتراک فعال، یا مهلت آزمایشیِ دستیِ مالک.
    """
    return is_active(chat_id) or has_free_access(chat_id)
