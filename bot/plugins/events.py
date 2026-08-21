"""لاگ رویدادهای عضویت + ثبت آهنگ‌های فوروارد‌شده به کانال آرشیو."""
import logging

from pyrogram import Client, filters
from pyrogram.types import ChatMemberUpdated, Message

import config
from bot import channel
from bot import database as db

LOGGER = logging.getLogger("musicbot.events")


@Client.on_message(filters.audio & filters.channel)
async def _on_archive_audio(client: Client, message: Message):
    """هر آهنگ صوتی که در کانال آرشیو فوروارد/آپلود شود → ثبت در دیتابیس.

    این‌طور آهنگ‌های فوروارد‌شده در جست‌وجو و پخش رندوم هم در دسترس می‌شوند.
    """
    try:
        if not config.ARCHIVE_CHANNEL:
            return
        if message.chat and message.chat.id == config.ARCHIVE_CHANNEL:
            await channel.store_forwarded(message)
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("archive audio store: %s", e)


@Client.on_message(filters.channel & filters.reply & filters.regex(r"^\s*حذف\s*$"))
async def _on_archive_delete(client: Client, message: Message):
    """ریپلای «حذف» روی یک آهنگ در کانال آرشیو → حذف آن از دیتابیس."""
    try:
        if not config.ARCHIVE_CHANNEL:
            return
        if not (message.chat and message.chat.id == config.ARCHIVE_CHANNEL):
            return
        target = message.reply_to_message
        if not target or not getattr(target, "audio", None):
            return
        rec = await channel.delete_from_archive(target)
        if rec:
            await message.reply_text(f"🗑 «{rec.get('title')}» از دیتابیس حذف شد.")
        else:
            await message.reply_text("این آهنگ در دیتابیس نبود.")
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("archive delete: %s", e)


@Client.on_chat_member_updated()
async def _on_member_update(client: Client, ev: ChatMemberUpdated):
    """وقتی وضعیت خودِ ربات در یک گروه عوض شد، در کانال لاگ اعلام کن."""
    try:
        me = client.me
        if me is None:
            me = await client.get_me()
        # فقط رویدادهای مربوط به خودِ ربات
        who = ev.new_chat_member or ev.old_chat_member
        if not who or not who.user or who.user.id != me.id:
            return

        chat = ev.chat
        title = getattr(chat, "title", "") or str(chat.id)
        adder = ev.from_user
        adder_name = ""
        if adder:
            adder_name = adder.first_name or (adder.username and "@" + adder.username) or str(adder.id)

        old_status = ev.old_chat_member.status.name if ev.old_chat_member else None
        new_status = ev.new_chat_member.status.name if ev.new_chat_member else None

        added = (old_status in (None, "LEFT", "BANNED")) and new_status in ("MEMBER", "ADMINISTRATOR")
        removed = new_status in ("LEFT", "BANNED")

        if added:
            db.add_chat(chat.id)
            await channel.log(
                f"➕ **به گروه جدید اضافه شد**\n"
                f"• گروه: {title}\n"
                f"• آیدی: `{chat.id}`\n"
                f"• توسط: {adder_name}"
            )
        elif removed:
            await channel.log(
                f"➖ **از گروه حذف/بلاک شد**\n"
                f"• گروه: {title}\n"
                f"• آیدی: `{chat.id}`"
            )
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("member update log: %s", e)
