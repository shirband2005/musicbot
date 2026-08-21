"""پنل «مدیریت پلیر» — فقط برای مالک. جدا از پنل پخش.

با دستور «مدیریت پلیر» در هر گروه باز می‌شود و تنظیماتِ همان گروه را نشان/تغییر می‌دهد:
  - روشن/خاموش کردن کل پلیر برای گروه
  - قفل پلتفرم: هر دو / فقط یوتیوب / فقط ساوندکلاد

دستورهای متنی هم پشتیبانی می‌شوند (طبق خواستهٔ کاربر):
  موزیک پلیر روشن / خاموش
  موزیک پلیر یوتیوب روشن / موزیک پلیر ساوندکلاد روشن / موزیک پلیر هردو
"""
import logging

from pyrogram import Client, enums, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import group_config as gc
from bot.auth import OWNER_ID
from bot.facmd import fa_command

LOGGER = logging.getLogger("musicbot.adminpanel")

_GREEN = enums.ButtonStyle.SUCCESS
_RED = enums.ButtonStyle.DANGER
_BLUE = enums.ButtonStyle.PRIMARY

ON, OFF = "🟢", "🔴"
SEL, NOSEL = "🔘", "⚪️"


def _is_owner(message: Message) -> bool:
    return bool(message.from_user) and message.from_user.id == OWNER_ID


def _panel(chat_id: int):
    enabled = gc.is_enabled(chat_id)
    lock = gc.get_lock(chat_id)

    text = (
        "🎛 **پنل مدیریت پلیر**\n\n"
        f"وضعیت پلیر : {'🟢 روشن' if enabled else '🔴 خاموش'}\n"
        f"پلتفرم گروه : {_lock_label(lock)}\n\n"
        "از دکمه‌های زیر تنظیمات همین گروه را تغییر بده."
    )

    def cb(a):
        return f"mp|{a}|{chat_id}"

    rows = [
        [InlineKeyboardButton(
            ("🔴 خاموش کردن پلیر" if enabled else "🟢 روشن کردن پلیر"),
            callback_data=cb("toggle"),
            style=(_RED if enabled else _GREEN),
        )],
        [InlineKeyboardButton("— پلتفرم گروه —", callback_data=cb("noop"), style=_BLUE)],
        [
            InlineKeyboardButton(
                f"{SEL if lock==gc.LOCK_NONE else NOSEL} هر دو",
                callback_data=cb("lock_none"), style=_BLUE),
        ],
        [
            InlineKeyboardButton(
                f"{SEL if lock==gc.LOCK_YOUTUBE else NOSEL} فقط یوتیوب",
                callback_data=cb("lock_yt"), style=_BLUE),
            InlineKeyboardButton(
                f"{SEL if lock==gc.LOCK_SOUNDCLOUD else NOSEL} فقط ساوندکلاد",
                callback_data=cb("lock_sc"), style=_BLUE),
        ],
        [InlineKeyboardButton("⛔️ بستن", callback_data=cb("close"), style=_RED)],
    ]
    return text, InlineKeyboardMarkup(rows)


def _lock_label(lock: str) -> str:
    return {
        gc.LOCK_NONE: "یوتیوب + ساوندکلاد (قابل تغییر در پنل پخش)",
        gc.LOCK_YOUTUBE: "فقط یوتیوب (قفل‌شده)",
        gc.LOCK_SOUNDCLOUD: "فقط ساوندکلاد (قفل‌شده)",
    }.get(lock, lock)


# ---------- دستور اصلی: «مدیریت پلیر» ----------
@Client.on_message(fa_command(["مدیریت پلیر", "پنل مدیریت پلیر"]))
async def admin_panel_cmd(client: Client, message: Message):
    if not _is_owner(message):
        return  # فقط مالک — بی‌صدا نادیده بگیر
    if message.chat.type.name == "PRIVATE":
        await message.reply_text("این پنل باید داخل گروه باز شود تا تنظیمات همان گروه را ذخیره کند.")
        return
    text, kb = _panel(message.chat.id)
    await message.reply_text(text, reply_markup=kb)


# ---------- دستورهای متنی سریع ----------
@Client.on_message(fa_command(["موزیک پلیر روشن"]))
async def mp_on(client: Client, message: Message):
    if not _is_owner(message) or message.chat.type.name == "PRIVATE":
        return
    gc.set_enabled(message.chat.id, True)
    await message.reply_text("🟢 موزیک‌پلیر برای این گروه **روشن** شد.")


@Client.on_message(fa_command(["موزیک پلیر خاموش"]))
async def mp_off(client: Client, message: Message):
    if not _is_owner(message) or message.chat.type.name == "PRIVATE":
        return
    gc.set_enabled(message.chat.id, False)
    await message.reply_text("🔴 موزیک‌پلیر برای این گروه **خاموش** شد.")


@Client.on_message(fa_command(["موزیک پلیر یوتیوب روشن", "موزیک پلیر فقط یوتیوب"]))
async def mp_yt(client: Client, message: Message):
    if not _is_owner(message) or message.chat.type.name == "PRIVATE":
        return
    gc.set_enabled(message.chat.id, True)
    gc.set_lock(message.chat.id, gc.LOCK_YOUTUBE)
    await message.reply_text("🟢 روشن شد. پلتفرم گروه: **فقط یوتیوب** (دکمه پلتفرم در پنل حذف شد).")


@Client.on_message(fa_command(["موزیک پلیر ساوندکلاد روشن", "موزیک پلیر فقط ساوندکلاد"]))
async def mp_sc(client: Client, message: Message):
    if not _is_owner(message) or message.chat.type.name == "PRIVATE":
        return
    gc.set_enabled(message.chat.id, True)
    gc.set_lock(message.chat.id, gc.LOCK_SOUNDCLOUD)
    await message.reply_text("🟢 روشن شد. پلتفرم گروه: **فقط ساوندکلاد** (دکمه پلتفرم در پنل حذف شد).")


@Client.on_message(fa_command(["موزیک پلیر هردو", "موزیک پلیر هر دو"]))
async def mp_both(client: Client, message: Message):
    if not _is_owner(message) or message.chat.type.name == "PRIVATE":
        return
    gc.set_enabled(message.chat.id, True)
    gc.set_lock(message.chat.id, gc.LOCK_NONE)
    await message.reply_text("🟢 روشن شد. پلتفرم گروه: **یوتیوب + ساوندکلاد** (قابل تغییر در پنل پخش).")


# ---------- callback پنل مدیریت ----------
@Client.on_callback_query(filters.regex(r"^mp\|"))
async def admin_panel_cb(client: Client, cq: CallbackQuery):
    if not cq.from_user or cq.from_user.id != OWNER_ID:
        await cq.answer("فقط مالک ربات به این پنل دسترسی دارد.", show_alert=True)
        return
    try:
        _, action, chat_id_s = cq.data.split("|", 2)
        chat_id = int(chat_id_s)
    except (ValueError, IndexError):
        await cq.answer("داده نامعتبر", show_alert=True)
        return

    if action == "noop":
        await cq.answer()
        return
    if action == "close":
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("بسته شد")
        return

    if action == "toggle":
        new = not gc.is_enabled(chat_id)
        gc.set_enabled(chat_id, new)
        await cq.answer("🟢 روشن شد" if new else "🔴 خاموش شد")
    elif action == "lock_none":
        gc.set_lock(chat_id, gc.LOCK_NONE)
        await cq.answer("پلتفرم: هر دو")
    elif action == "lock_yt":
        gc.set_lock(chat_id, gc.LOCK_YOUTUBE)
        await cq.answer("پلتفرم: فقط یوتیوب")
    elif action == "lock_sc":
        gc.set_lock(chat_id, gc.LOCK_SOUNDCLOUD)
        await cq.answer("پلتفرم: فقط ساوندکلاد")

    text, kb = _panel(chat_id)
    try:
        await cq.message.edit_text(text, reply_markup=kb)
    except Exception:  # noqa: BLE001
        pass
