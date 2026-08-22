"""تایمر خواب: پس از مدت انتخابی، پخش قطع و ربات از ویس‌چت خارج می‌شود.

هر گروه حداکثر یک تایمر دارد. زمان پایان در حافظه نگه داشته می‌شود (نه دیتابیس)
چون با ری‌استارت ربات پخش هم قطع می‌شود و تایمرِ معلق معنا ندارد.

شمارش معکوس روی دکمه‌ی پنل مجانی به‌دست می‌آید: نوار زمان هر چند ثانیه پنل را
رفرش می‌کند و همان رفرش عدد تایمر را هم به‌روز می‌کند.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Dict, Optional

LOGGER = logging.getLogger("musicbot.sleep")

# chat_id → timestamp پایان
_deadline: Dict[int, float] = {}
# chat_id → تسک انتظار
_task: Dict[int, asyncio.Task] = {}

# تابعی که تایمر در پایان صدا می‌زند؛ player آن را ثبت می‌کند تا وابستگی
# دوطرفه‌ی import پیش نیاید (player → sleep_timer، نه برعکس).
_on_expire: Optional[Callable] = None


def set_expire_handler(func: Callable) -> None:
    """`async def handler(chat_id: int)` که هنگام سر رسیدن تایمر اجرا می‌شود."""
    global _on_expire
    _on_expire = func


def left(chat_id: int) -> Optional[float]:
    """ثانیه‌ی باقی‌مانده، یا None اگر تایمری فعال نیست."""
    end = _deadline.get(chat_id)
    if end is None:
        return None
    remain = end - time.time()
    if remain <= 0:
        return 0.0
    return remain


def is_active(chat_id: int) -> bool:
    return chat_id in _deadline


def cancel(chat_id: int) -> bool:
    """تایمر را خاموش می‌کند. True اگر تایمری فعال بود."""
    had = _deadline.pop(chat_id, None) is not None
    t = _task.pop(chat_id, None)
    if t and not t.done():
        t.cancel()
    return had


def start(chat_id: int, minutes: int) -> float:
    """تایمر را روی `minutes` دقیقه می‌گذارد (تایمر قبلی جایگزین می‌شود).

    برمی‌گرداند: ثانیه‌ی باقی‌مانده (برای نمایش فوری روی دکمه).

    اگر حلقه‌ی asyncio در جریان نباشد (مثلاً در تست همگام)، فقط مهلت ثبت
    می‌شود و تسک انتظار ساخته نمی‌شود؛ `left()` همچنان درست کار می‌کند.
    """
    cancel(chat_id)
    seconds = max(1, int(minutes) * 60)
    _deadline[chat_id] = time.time() + seconds
    coro = _wait(chat_id, seconds)
    try:
        _task[chat_id] = asyncio.create_task(coro)
    except RuntimeError:
        coro.close()   # وگرنه هشدار «coroutine was never awaited» می‌دهد
        LOGGER.debug("تایمر خواب بدون حلقه‌ی asyncio ثبت شد (chat=%s)", chat_id)
    return float(seconds)


async def _wait(chat_id: int, seconds: float) -> None:
    try:
        await asyncio.sleep(seconds)
    except asyncio.CancelledError:
        return
    # تایمر ممکن است در این فاصله خاموش یا جابه‌جا شده باشد
    end = _deadline.get(chat_id)
    if end is None or end - time.time() > 1:
        return
    _deadline.pop(chat_id, None)
    _task.pop(chat_id, None)
    if _on_expire is None:
        LOGGER.warning("تایمر خواب سر رسید ولی هندلر ثبت نشده بود (chat=%s)", chat_id)
        return
    try:
        await _on_expire(chat_id)
    except Exception as e:  # noqa: BLE001
        LOGGER.error("اجرای پایان تایمر خواب: %s", e)


def clear_all() -> None:
    """پاک‌سازی کامل (برای تست)."""
    for cid in list(_deadline):
        cancel(cid)
