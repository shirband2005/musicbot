"""زمان‌بند انقضای اشتراک: هر ساعت گروه‌های منقضی را خاموش و پیام تمدید می‌دهد."""
import asyncio
import logging
import time

from bot import database as db
from bot import group_config as gc

LOGGER = logging.getLogger("musicbot.subwatch")

_CHECK_INTERVAL = 3600  # هر ساعت
_NOTIFY_COOLDOWN = 20 * 3600  # حداکثر یک پیام تمدید هر ~۲۰ ساعت برای هر گروه


async def expiry_loop(client) -> None:
    """لوپ دائمی: اشتراک‌های منقضی‌شده را خاموش می‌کند و پیام تمدید می‌فرستد."""
    while True:
        try:
            await _check_once(client)
        except Exception as e:  # noqa: BLE001
            LOGGER.warning("expiry check: %s", e)
        await asyncio.sleep(_CHECK_INTERVAL)


async def _check_once(client) -> None:
    now = time.time()
    for sub in db.sub_expired(now):
        chat_id = sub["chat_id"]
        # گروه را خاموش کن
        try:
            gc.set_enabled(chat_id, False)
        except Exception:  # noqa: BLE001
            pass
        # پیام تمدید (با ضد اسپم)
        if now - (sub.get("last_notified") or 0) < _NOTIFY_COOLDOWN:
            continue
        db.sub_set(chat_id, last_notified=now)
        msg = ("⛔️ **اشتراک این گروه به پایان رسید.**\n"
               "ربات موقتاً خاموش شد. برای تمدید، در خصوصی ربات "
               "دکمه «🛒 خرید اشتراک» را بزنید.")
        try:
            await client.send_message(chat_id, msg)
        except Exception:  # noqa: BLE001
            pass
        buyer = sub.get("buyer_id") or 0
        if buyer:
            try:
                await client.send_message(
                    buyer,
                    "⛔️ اشتراک گروه شما منقضی شد و ربات خاموش شد.\n"
                    "برای تمدید، دکمه «🛒 خرید اشتراک» را بزنید.",
                )
            except Exception:  # noqa: BLE001
                pass
        LOGGER.info("SUB EXPIRED | chat=%s خاموش شد", chat_id)
