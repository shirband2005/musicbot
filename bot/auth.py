"""کنترل دسترسی: فقط مالک/سازنده و ادمین‌های همان گروه به ربات دسترسی دارند.

- در گروه: فقط ادمین‌های گروه + OWNER_ID مجازند.
- در خصوصی (PV): فقط OWNER_ID.
"""
import logging

from pyrogram import Client, enums
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import database as db

LOGGER = logging.getLogger("musicbot.auth")

OWNER_ID = 8406519786  # سازنده/مالک ربات (= پشتیبانی)

# لینک پشتیبانی به‌صورت پویا از روی آیدی عددی مالک ساخته می‌شود:
# اگر مالک یوزرنیم عمومی داشته باشد → https://t.me/<username> (در دکمه قطعی کار می‌کند)
# در غیر این صورت → tg://user?id=<OWNER_ID> (fallback)
import time as _time
_support_cache = {"url": f"tg://user?id={OWNER_ID}", "ts": 0.0}
_SUPPORT_TTL = 600  # هر ۱۰ دقیقه یک‌بار یوزرنیم را دوباره بررسی کن


async def resolve_support_url(client: Client) -> str:
    """یوزرنیم فعلی مالک را از آیدی عددی می‌گیرد و لینک پشتیبانی را کش می‌کند."""
    now = _time.time()
    if now - _support_cache["ts"] < _SUPPORT_TTL:
        return _support_cache["url"]
    url = f"tg://user?id={OWNER_ID}"
    try:
        chat = await client.get_chat(OWNER_ID)
        if getattr(chat, "username", None):
            url = f"https://t.me/{chat.username}"
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("resolve support url: %s", e)
    _support_cache["url"] = url
    _support_cache["ts"] = now
    return url


def support_kb(url: str | None = None) -> InlineKeyboardMarkup:
    link = url or _support_cache["url"]
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("💬 ارتباط با پشتیبانی", url=link,
                                style=enums.ButtonStyle.PRIMARY)]]
    )


DENY_GROUP = (
    "⛔️ **گروه دسترسی ندارد**\n\n"
    "برای مجاز کردن دسترسی با پشتیبانی تماس بگیرید."
)
DENY_USER = "⛔️ **شما دسترسی ندارید**"
DENY_CALLBACK = "⛔️ شما دسترسی ندارید\nبا پشتیبانی تماس بگیرید."

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
    """برای هندلرهای پیام. True یعنی مجاز؛ در غیر این صورت پیام مناسب می‌دهد و False."""
    user = message.from_user
    if not user:
        return False  # پیام کانال/ناشناس
    is_private = message.chat.type.name == "PRIVATE"
    if await is_allowed(client, message.chat.id, user.id, is_private):
        return True
    # کاربر مجاز نیست → پیام «شما دسترسی ندارید» + دکمه پشتیبانی
    try:
        url = await resolve_support_url(client)
        await message.reply_text(DENY_USER, reply_markup=support_kb(url))
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
        await cq.answer(DENY_CALLBACK, show_alert=True)
    except Exception:  # noqa: BLE001
        pass
    return False
