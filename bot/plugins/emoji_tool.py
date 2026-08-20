"""ابزار کمکی: گرفتن custom_emoji_id از ایموجی پرمیوم + تست ارسال توسط ربات.

استفاده (فقط مالک): یک یا چند ایموجی پرمیوم بفرست یا روی پیامی که ایموجی پرمیوم
دارد ریپلای کن و بنویس «ایدی ایموجی». ربات:
  1) شناسه‌ی هر ایموجی را می‌دهد (برای استفاده در پنل)
  2) همان ایموجی‌ها را دوباره می‌فرستد تا ببینیم ربات می‌تواند نمایش‌شان دهد
     (اگر مالکِ ربات Premium باشد کار می‌کند).
"""
import logging

from pyrogram import Client, enums
from pyrogram.types import Message, MessageEntity

from bot.facmd import fa_command

LOGGER = logging.getLogger("musicbot.emojitool")

OWNER_ID = 8406519786  # فقط مالک


def _extract(msg: Message):
    """شناسه‌ی ایموجی‌های پرمیوم یک پیام را استخراج می‌کند: [(emoji_text, id), ...]."""
    out = []
    if not msg or not msg.entities:
        return out
    text = msg.text or msg.caption or ""
    for ent in msg.entities:
        if ent.type == enums.MessageEntityType.CUSTOM_EMOJI:
            seg = text[ent.offset: ent.offset + ent.length]
            out.append((seg, ent.custom_emoji_id))
    return out


@Client.on_message(fa_command(["ایدی ایموجی", "آیدی ایموجی", "emojiid"]))
async def emoji_id_cmd(client: Client, message: Message):
    if not message.from_user or message.from_user.id != OWNER_ID:
        return

    # منبع: پیام ریپلای‌شده یا خودِ پیام
    source = message.reply_to_message or message
    found = _extract(source)

    if not found:
        await message.reply_text(
            "یک یا چند **ایموجی پرمیوم** را در همین پیام بفرست به‌همراه دستور، "
            "یا روی پیامی که ایموجی پرمیوم دارد ریپلای کن و بنویس «ایدی ایموجی»."
        )
        return

    # ۱) گزارش شناسه‌ها
    lines = ["🆔 **شناسه‌ی ایموجی‌ها:**\n"]
    ids = []
    for seg, eid in found:
        lines.append(f"`{eid}`")
        ids.append(eid)
    report = "\n".join(lines)

    # ۲) تست ارسال: همان ایموجی‌ها را با entity سفارشی از طرف ربات بفرست
    test_text = "".join("🎵" for _ in ids)  # هر ایموجی روی یک کاراکتر پایه
    entities = []
    offset = 0
    for eid in ids:
        entities.append(
            MessageEntity(
                type=enums.MessageEntityType.CUSTOM_EMOJI,
                offset=offset,
                length=len("🎵"),
                custom_emoji_id=eid,
            )
        )
        offset += len("🎵")

    await message.reply_text(report)
    try:
        await client.send_message(
            message.chat.id,
            "تست نمایش توسط ربات: " + test_text,
            entities=[
                MessageEntity(
                    type=enums.MessageEntityType.CUSTOM_EMOJI,
                    offset=len("تست نمایش توسط ربات: ") + i * len("🎵"),
                    length=len("🎵"),
                    custom_emoji_id=eid,
                )
                for i, eid in enumerate(ids)
            ],
        )
        await message.reply_text(
            "☝️ اگر بالا ایموجی‌های پرمیوم **متحرک** دیدی، یعنی ربات می‌تواند نمایش‌شان دهد ✅"
        )
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("emoji test send failed: %s", e)
        await message.reply_text(f"❌ ارسال تستی ناموفق: `{str(e)[:200]}`")
