"""لاگ رویدادهای عضویت: افزوده/حذف شدن ربات از گروه‌ها → کانال لاگ."""
import logging

from pyrogram import Client
from pyrogram.types import ChatMemberUpdated

from bot import channel
from bot import database as db

LOGGER = logging.getLogger("musicbot.events")


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
