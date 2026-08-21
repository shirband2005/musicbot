"""کنترل دسترسی: فقط مالک/سازنده و ادمین‌های همان گروه به ربات دسترسی دارند.

- در گروه: فقط ادمین‌های گروه + OWNER_ID مجازند.
- در خصوصی (PV): فقط OWNER_ID.
"""
import logging

from pyrogram import Client, enums
from pyrogram.types import CallbackQuery, Message

from bot import database as db

LOGGER = logging.getLogger("musicbot.auth")

OWNER_ID = 8406519786  # سازنده/مالک ربات

_DENY_MSG = "⛔️ فقط ادمین‌های گروه می‌توانند از ربات استفاده کنند."
_DENY_PV = "⛔️ این ربات فقط برای مالک و ادمین‌های گروه‌هاست."

# کش کوتاه‌مدت ادمین‌ها برای هر چت: {chat_id: (timestamp, set(user_ids))}
import time
_admin_cache: dict = {}
_CACHE_TTL = 120  # ثانیه


async def _admin_ids(client: Client, chat_id: int) -> set:
    now = time.time()
    hit = _admin_cache.get(chat_id)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    ids = set()
    try:
        async for m in client.get_chat_members(
            chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS
        ):
            if m.user:
                ids.add(m.user.id)
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("get admins failed for %s: %s", chat_id, e)
    _admin_cache[chat_id] = (now, ids)
    return ids


async def is_allowed(client: Client, chat_id: int, user_id: int, is_private: bool) -> bool:
    """آیا این کاربر مجاز به استفاده از ربات است؟"""
    if user_id == OWNER_ID:
        return True
    if db.is_special(user_id):  # کاربر ویژه: دسترسی سراسری (گروه و PV)
        return True
    if is_private:
        return False  # در PV فقط مالک و کاربران ویژه
    admins = await _admin_ids(client, chat_id)
    return user_id in admins


async def guard_message(client: Client, message: Message) -> bool:
    """برای هندلرهای پیام. True یعنی مجاز؛ در غیر این صورت پیام رد می‌دهد و False."""
    user = message.from_user
    if not user:
        return False  # پیام کانال/ناشناس
    is_private = message.chat.type.name == "PRIVATE"
    if await is_allowed(client, message.chat.id, user.id, is_private):
        return True
    try:
        await message.reply_text(_DENY_PV if is_private else _DENY_MSG)
    except Exception:  # noqa: BLE001
        pass
    return False


async def guard_callback(client: Client, cq: CallbackQuery) -> bool:
    """برای هندلرهای دکمه. True یعنی مجاز؛ در غیر این صورت alert و False."""
    user = cq.from_user
    if not user:
        return False
    is_private = not cq.message or cq.message.chat.type.name == "PRIVATE"
    chat_id = cq.message.chat.id if cq.message else 0
    if await is_allowed(client, chat_id, user.id, is_private):
        return True
    try:
        await cq.answer(_DENY_MSG, show_alert=True)
    except Exception:  # noqa: BLE001
        pass
    return False
