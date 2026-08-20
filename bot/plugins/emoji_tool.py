"""ابزار کمکی: گرفتن custom_emoji_id از ایموجی پرمیوم + تست ارسال توسط ربات.

استفاده (فقط مالک): یک یا چند ایموجی پرمیوم بفرست همراه دستور «ایدی ایموجی»،
یا روی پیامی که ایموجی پرمیوم دارد ریپلای کن. ربات:
  1) شناسه‌ی هر ایموجی را می‌دهد (برای استفاده در پنل)
  2) همان ایموجی‌ها را دوباره می‌فرستد (تست نمایش‌پذیری توسط ربات).

نکته فنی: تلگرام طول entity را با UTF-16 code unit می‌شمرد (نه len پایتون).
"""
import logging

from pyrogram import Client, enums
from pyrogram.types import Message, MessageEntity

from bot.facmd import fa_command

LOGGER = logging.getLogger("musicbot.emojitool")

OWNER_ID = 8406519786  # فقط مالک


def _u16len(s: str) -> int:
    """طول رشته برحسب UTF-16 code unit (مبنای شمارش تلگرام)."""
    return len(s.encode("utf-16-le")) // 2


def _extract(msg: Message):
    """[(emoji_text, id), ...] از ایموجی‌های پرمیوم یک پیام."""
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

    source = message.reply_to_message or message
    found = _extract(source)

    if not found:
        await message.reply_text(
            "یک یا چند **ایموجی پرمیوم** را همراه دستور «ایدی ایموجی» بفرست، "
            "یا روی پیامی که ایموجی پرمیوم دارد ریپلای کن."
        )
        return

    # ۱) گزارش شناسه‌ها (هر کدام روی یک خط برای کپی راحت)
    ids = [eid for _, eid in found]
    report = "🆔 **شناسه‌ی ایموجی‌ها:**\n\n" + "\n".join(f"`{eid}`" for eid in ids)
    await message.reply_text(report)

    # ۲) تست ارسال با ایموجی‌های واقعی کاربر و طول UTF-16 صحیح
    prefix = "تست نمایش توسط ربات: "
    # کاراکترهای پایه‌ی همان ایموجی‌های کاربر را استفاده کن (طول واقعی‌شان)
    segs = [seg for seg, _ in found]
    test_text = prefix + "".join(segs)

    entities = []
    offset = _u16len(prefix)
    for (seg, eid) in found:
        seg_len = _u16len(seg)
        entities.append(
            MessageEntity(
                type=enums.MessageEntityType.CUSTOM_EMOJI,
                offset=offset,
                length=seg_len,
                custom_emoji_id=eid,
            )
        )
        offset += seg_len

    try:
        await client.send_message(message.chat.id, test_text, entities=entities)
        await message.reply_text(
            "☝️ اگر بالا ایموجی‌های پرمیوم **متحرک** دیدی، یعنی ربات می‌تواند نمایش‌شان دهد ✅\n"
            "حالا بگو کدام ایموجی کجا برود (کنار کدام دکمه یا در عنوان)."
        )
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("emoji test send failed: %s", e)
        await message.reply_text(f"❌ ارسال تستی ناموفق: `{str(e)[:200]}`")
