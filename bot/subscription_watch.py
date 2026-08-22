"""زمان‌بند انقضای اشتراک: گروه‌های منقضی را خاموش می‌کند و پیام تمدید می‌دهد.

طبق تصمیم کاربر: با پایان اشتراک، ربات برای آن گروه از کار می‌افتد و در گروه
پیام تمدید می‌رود. اگر تمدید داشته باشند (اشتراک فعال است) کاری انجام نمی‌شود.
مهلت آزمایشیِ دستیِ مالک (free_until) هم اینجا بررسی و در پایانش خاموش می‌شود.
"""
import asyncio
import logging
import time

from bot import database as db
from bot import group_config as gc
from bot import subscription as sub
from bot import ui

LOGGER = logging.getLogger("musicbot.subwatch")

_CHECK_INTERVAL = 3600           # هر ساعت
_NOTIFY_COOLDOWN = 20 * 3600     # حداکثر یک پیام تمدید هر ~۲۰ ساعت برای هر گروه


async def expiry_loop(client) -> None:
    """لوپ دائمی: اشتراک‌های منقضی‌شده را خاموش می‌کند و پیام تمدید می‌فرستد."""
    while True:
        try:
            await _check_once(client)
        except Exception as e:  # noqa: BLE001
            LOGGER.warning("expiry check: %s", e)
        await asyncio.sleep(_CHECK_INTERVAL)


def _expired_text():
    t = ui.Text().title(ui.EMO_BELL, ui.BASE_ARROW, "اشتراک این گروه تمام شد")
    t.why("ربات در این گروه از کار افتاده است.")
    t.how("برای فعال‌سازی مجدد، در پیوی ربات اشتراک را تمدید کن.")
    return t.text, t.entities


def _buyer_text():
    t = ui.Text().title(ui.EMO_BELL, ui.BASE_ARROW, "اشتراک گروه شما تمام شد")
    t.why("ربات در آن گروه از کار افتاده است.")
    t.how("برای فعال‌سازی مجدد، «اشتراک من» را بزن و تمدید کن.")
    rows = ui.kb([[ui.btn("اشتراک من", "my|list", ui.BLUE, ui.EMO_LIST)]])
    return t.text, t.entities, rows


async def _check_once(client) -> None:
    now = time.time()

    # ۱) اشتراک‌های منقضی‌شده
    for row in db.sub_expired(now):
        chat_id = row["chat_id"]
        # اشتراک مکث‌شده منقضی حساب نمی‌شود (زمانش یخ زده است)
        if (row.get("paused_at") or 0) > 0:
            continue
        # اگر مهلت آزمایشی دستی دارد، خاموش نکن
        if sub.has_free_access(chat_id):
            continue
        try:
            gc.set_enabled(chat_id, False)
        except Exception:  # noqa: BLE001
            pass

        if now - (row.get("last_notified") or 0) < _NOTIFY_COOLDOWN:
            continue
        db.sub_set(chat_id, last_notified=now)

        text, ents = _expired_text()
        try:
            await client.send_message(chat_id, text, entities=ents)
        except Exception:  # noqa: BLE001
            pass

        # ثبت در کانال لاگ (قبلاً هیچ‌جا ثبت نمی‌شد)
        try:
            from bot import channel
            from bot import channel_ui as cui
            name = await _chat_name(client, chat_id)
            await channel.log(*cui.sub_expired(name, chat_id))
        except Exception:  # noqa: BLE001
            pass

        buyer = row.get("buyer_id") or 0
        if buyer:
            btext, bents, bkb = _buyer_text()
            try:
                await client.send_message(buyer, btext, entities=bents,
                                          reply_markup=bkb)
            except Exception:  # noqa: BLE001
                pass
        LOGGER.info("SUB EXPIRED | chat=%s خاموش شد", chat_id)

    # ۲) مهلت‌های آزمایشی سرآمده (بدون اشتراک فعال)
    for chat_id in db.get_chats():
        fu = sub.free_until(chat_id)
        if fu <= 0 or fu > now:
            continue
        if sub.is_active(chat_id):
            continue
        db.group_set(chat_id, free_until=0)
        try:
            gc.set_enabled(chat_id, False)
        except Exception:  # noqa: BLE001
            pass
        try:
            from bot import channel
            from bot import channel_ui as cui
            name = await _chat_name(client, chat_id)
            await channel.log(*cui.free_access_ended(name, chat_id))
        except Exception:  # noqa: BLE001
            pass
        LOGGER.info("FREE ACCESS ENDED | chat=%s خاموش شد", chat_id)


async def _chat_name(client, chat_id: int) -> str:
    try:
        chat = await client.get_chat(chat_id)
        return chat.title or str(chat_id)
    except Exception:  # noqa: BLE001
        return str(chat_id)
