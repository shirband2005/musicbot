"""مدیریت کاربران ویژه — فقط توسط مالک (با ریپلای).

- «تنظیم ویژه» (ریپلای روی کاربر) → آن کاربر دسترسی سراسری می‌گیرد.
- «حذف ویژه»  (ریپلای روی کاربر) → دسترسی سراسری‌اش پاک می‌شود.
- «لیست ویژه» → فهرست کاربران ویژه.
"""
import logging

from pyrogram import Client
from pyrogram.types import Message

from bot import database as db
from bot.auth import OWNER_ID
from bot.facmd import fa_command

LOGGER = logging.getLogger("musicbot.special")


def _target(message: Message):
    """کاربر هدف را از ریپلای برمی‌گرداند (یا None)."""
    r = message.reply_to_message
    if r and r.from_user:
        return r.from_user
    return None


@Client.on_message(fa_command(["تنظیم ویژه", "افزودن ویژه"]))
async def add_special_cmd(client: Client, message: Message):
    if not message.from_user or message.from_user.id != OWNER_ID:
        return  # فقط مالک
    user = _target(message)
    if not user:
        await message.reply_text("روی پیامِ کاربری که می‌خواهی ویژه شود ریپلای کن و بنویس «تنظیم ویژه».")
        return
    name = user.first_name or (user.username and "@" + user.username) or str(user.id)
    db.add_special(user.id, name)
    await message.reply_text(f"✅ کاربر ویژه شد:\n**{name}** (`{user.id}`)\nحالا دسترسی کامل به ربات دارد.")


@Client.on_message(fa_command(["حذف ویژه", "لغو ویژه"]))
async def remove_special_cmd(client: Client, message: Message):
    if not message.from_user or message.from_user.id != OWNER_ID:
        return
    user = _target(message)
    if not user:
        await message.reply_text("روی پیامِ کاربری که می‌خواهی دسترسی‌اش پاک شود ریپلای کن و بنویس «حذف ویژه».")
        return
    if not db.is_special(user.id):
        await message.reply_text("این کاربر ویژه نبود.")
        return
    db.remove_special(user.id)
    name = user.first_name or (user.username and "@" + user.username) or str(user.id)
    await message.reply_text(f"🗑 دسترسی ویژه حذف شد:\n**{name}** (`{user.id}`)")


@Client.on_message(fa_command(["لیست ویژه", "کاربران ویژه"]))
async def list_special_cmd(client: Client, message: Message):
    if not message.from_user or message.from_user.id != OWNER_ID:
        return
    ids = db.list_special()
    if not ids:
        await message.reply_text("هیچ کاربر ویژه‌ای ثبت نشده.")
        return
    lines = ["⭐️ **کاربران ویژه:**\n"]
    for uid in ids:
        name = db.special_name(uid)
        lines.append(f"• {name} (`{uid}`)")
    await message.reply_text("\n".join(lines))
