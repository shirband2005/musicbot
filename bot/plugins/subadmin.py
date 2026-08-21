"""پنل مدیریت اشتراک‌ها + تنظیمات پرداخت — فقط مالک، در PV.

دستور «مدیریت اشتراک» → لیست اشتراک‌ها + تنظیمات پرداخت.
تنظیمات پرداخت (قیمت، شماره کارت، آدرس کریپتو، نرخ) با ریپلای مقدار جدید ویرایش می‌شوند.
"""
import logging

from pyrogram import Client, enums, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import database as db
from bot import subscription as sub
from bot.auth import OWNER_ID
from bot.facmd import fa_command

LOGGER = logging.getLogger("musicbot.subadmin")

_GREEN = enums.ButtonStyle.SUCCESS
_RED = enums.ButtonStyle.DANGER
_BLUE = enums.ButtonStyle.PRIMARY

# وضعیت انتظار ورودی مالک برای ویرایش یک تنظیم: {owner_id: pay_settings_key}
_awaiting: dict = {}


def _is_owner(m) -> bool:
    return bool(m.from_user) and m.from_user.id == OWNER_ID


def _main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 لیست اشتراک‌ها", callback_data="sadm|list")],
        [InlineKeyboardButton("💰 تنظیم قیمت‌ها", callback_data="sadm|prices")],
        [InlineKeyboardButton("💳 شماره کارت", callback_data="sadm|set|card_number"),
         InlineKeyboardButton("👤 نام صاحب کارت", callback_data="sadm|set|card_holder")],
        [InlineKeyboardButton("🪙 آدرس کریپتو", callback_data="sadm|set|crypto_addr"),
         InlineKeyboardButton("💱 نرخ USDT", callback_data="sadm|set|usdt_rate")],
        [InlineKeyboardButton("❌ بستن", callback_data="sadm|close")],
    ])


@Client.on_message(fa_command(["مدیریت اشتراک", "مدیریت اشتراک ها", "پنل اشتراک"]))
async def subadmin_cmd(client: Client, message: Message):
    if not _is_owner(message):
        return
    card = db.pay_get("card_number", "(تنظیم نشده)")
    addr = db.pay_get("crypto_addr", "(تنظیم نشده)")
    rate = db.pay_get("usdt_rate", "(تنظیم نشده)")
    txt = (
        "🗂 **مدیریت اشتراک‌ها و پرداخت**\n\n"
        f"💳 شماره کارت: `{card}`\n"
        f"🪙 آدرس کریپتو: `{addr}`\n"
        f"💱 نرخ هر USDT: {rate} تومان\n\n"
        "یکی را انتخاب کن:"
    )
    await message.reply_text(txt, reply_markup=_main_kb())


def _prices_kb() -> InlineKeyboardMarkup:
    rows = []
    for tier in (sub.TIER_BASIC, sub.TIER_PRO):
        for months, lbl in sub.DURATIONS:
            key = f"{tier}_{months}"
            st = sub.get_price(tier, months, "stars")
            tm = sub.get_price(tier, months, "toman")
            rows.append([InlineKeyboardButton(
                f"{sub.TIER_LABEL[tier]} {lbl}: ⭐️{st} / {tm:,}ت",
                callback_data=f"sadm|price|{key}")])
    rows.append([InlineKeyboardButton("🔙 برگشت", callback_data="sadm|back")])
    return InlineKeyboardMarkup(rows)


@Client.on_callback_query(filters.regex(r"^sadm\|"))
async def subadmin_cb(client: Client, cq: CallbackQuery):
    if cq.from_user.id != OWNER_ID:
        await cq.answer("فقط مالک.", show_alert=True)
        return
    parts = cq.data.split("|")
    action = parts[1]

    if action == "close":
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("بسته شد")
        return

    if action == "back":
        await cq.message.edit_text("🗂 **مدیریت اشتراک‌ها و پرداخت**\n\nیکی را انتخاب کن:",
                                   reply_markup=_main_kb())
        await cq.answer()
        return

    if action == "list":
        subs = db.sub_all()
        if not subs:
            await cq.answer("هیچ اشتراکی نیست.", show_alert=True)
            return
        rows = []
        for s in subs[:20]:
            exp = sub.expires_text(s["chat_id"])
            rows.append([InlineKeyboardButton(
                f"{s['chat_id']} | {sub.TIER_LABEL.get(s['tier'], s['tier'])} | {exp}",
                callback_data=f"sadm|sub|{s['chat_id']}")])
        rows.append([InlineKeyboardButton("🔙 برگشت", callback_data="sadm|back")])
        await cq.message.edit_text("📋 **اشتراک‌های فعال:**", reply_markup=InlineKeyboardMarkup(rows))
        await cq.answer()
        return

    if action == "sub":
        chat_id = int(parts[2])
        exp = sub.expires_text(chat_id)
        s = db.sub_get(chat_id) or {}
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ ۱ ماه", callback_data=f"sadm|ext|{chat_id}|1"),
             InlineKeyboardButton("➕ ۳ ماه", callback_data=f"sadm|ext|{chat_id}|3")],
            [InlineKeyboardButton("♾ دائمی", callback_data=f"sadm|ext|{chat_id}|perm")],
            [InlineKeyboardButton("🔄 تغییر تیر (پایه↔حرفه‌ای)", callback_data=f"sadm|tier|{chat_id}")],
            [InlineKeyboardButton("🗑 لغو اشتراک", callback_data=f"sadm|cancel|{chat_id}")],
            [InlineKeyboardButton("🔙 برگشت", callback_data="sadm|list")],
        ])
        await cq.message.edit_text(
            f"گروه `{chat_id}`\nتیر: {sub.TIER_LABEL.get(s.get('tier'), '؟')}\nوضعیت: {exp}",
            reply_markup=kb)
        await cq.answer()
        return

    if action == "ext":
        chat_id = int(parts[2])
        months = 0 if parts[3] == "perm" else int(parts[3])
        s = db.sub_get(chat_id) or {}
        tier = s.get("tier", sub.TIER_BASIC)
        from bot import group_config as gc
        sub.activate(chat_id, tier, months, buyer_id=s.get("buyer_id", 0))
        gc.set_enabled(chat_id, True)
        await cq.answer(f"تمدید شد: {sub.expires_text(chat_id)}", show_alert=True)
        try:
            await client.send_message(chat_id, "✅ اشتراک گروه توسط مدیریت تمدید شد.")
        except Exception:  # noqa: BLE001
            pass
        return

    if action == "tier":
        chat_id = int(parts[2])
        s = db.sub_get(chat_id) or {}
        new_tier = sub.TIER_PRO if s.get("tier") == sub.TIER_BASIC else sub.TIER_BASIC
        db.sub_set(chat_id, tier=new_tier)
        await cq.answer(f"تیر شد: {sub.TIER_LABEL[new_tier]}", show_alert=True)
        return

    if action == "cancel":
        chat_id = int(parts[2])
        sub.deactivate(chat_id)
        from bot import group_config as gc
        gc.set_enabled(chat_id, False)
        await cq.answer("اشتراک لغو و گروه خاموش شد.", show_alert=True)
        try:
            await cq.message.edit_text(f"🗑 اشتراک گروه `{chat_id}` لغو شد.")
        except Exception:  # noqa: BLE001
            pass
        return

    if action == "prices":
        await cq.message.edit_text("💰 روی هر پلن بزن تا قیمتش را عوض کنی:",
                                   reply_markup=_prices_kb())
        await cq.answer()
        return

    if action == "price":
        key = parts[2]  # tier_months
        _awaiting[cq.from_user.id] = f"price::{key}"
        await cq.message.reply_text(
            f"قیمت جدید پلن `{key}` را بفرست به شکل:\n`استارز تومان`\n"
            "مثال: `100 150000`  (۱۰۰ استارز و ۱۵۰هزار تومان)")
        await cq.answer()
        return

    if action == "set":
        key = parts[2]  # card_number | card_holder | crypto_addr | usdt_rate
        _awaiting[cq.from_user.id] = key
        labels = {"card_number": "شماره کارت", "card_holder": "نام صاحب کارت",
                  "crypto_addr": "آدرس کیف‌پول کریپتو", "usdt_rate": "نرخ هر USDT (تومان)"}
        await cq.message.reply_text(f"مقدار جدید «{labels.get(key, key)}» را بفرست:")
        await cq.answer()
        return


# --- دریافت ورودی مالک برای ویرایش تنظیمات (بالاترین اولویت در PV) ---
@Client.on_message(filters.private & filters.text, group=-1)
async def subadmin_input(client: Client, message: Message):
    if not _is_owner(message):
        return
    key = _awaiting.get(message.from_user.id)
    if not key:
        return
    _awaiting.pop(message.from_user.id, None)
    val = message.text.strip()
    if key.startswith("price::"):
        plan = key.split("::", 1)[1]  # tier_months
        try:
            stars_s, toman_s = val.split()
            tier, months = plan.rsplit("_", 1)
            sub.set_price(tier, int(months), "stars", int(stars_s))
            sub.set_price(tier, int(months), "toman", int(toman_s))
            await message.reply_text(f"✅ قیمت پلن {plan} ثبت شد: ⭐️{stars_s} / {int(toman_s):,}ت")
        except Exception:  # noqa: BLE001
            await message.reply_text("❌ قالب اشتباه. مثال: `100 150000`")
    else:
        db.pay_set(key, val)
        await message.reply_text(f"✅ ثبت شد: `{val}`")
