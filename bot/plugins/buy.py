"""جریان خرید اشتراک در PV ربات + پرداخت Telegram Stars.

مسیر: دکمه «خرید اشتراک» → انتخاب گروه → تیر → مدت → روش پرداخت.
Stars: create_invoice_link با currency=XTR (بدون provider_token) → پرداخت →
pre_checkout_query → successful_payment → فعال‌سازی گروه.
کارت/کریپتو: نمایش اطلاعات پرداخت + ثبت سفارش pending برای تأیید دستی مالک.
"""
import logging
import uuid

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
)

from bot import database as db
from bot import subscription as sub
from bot.auth import OWNER_ID

LOGGER = logging.getLogger("musicbot.buy")

# payload پرداخت Stars: sub|<order_id>
_PAYLOAD_PREFIX = "sub"

# کاربرانی که منتظر ارسال کد هدیه هستند: {user_id: True}
_await_gift: dict = {}


def _tier_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐️ {sub.TIER_LABEL['basic']}", callback_data=f"buy|tier|{chat_id}|basic")],
        [InlineKeyboardButton(f"💎 {sub.TIER_LABEL['pro']}", callback_data=f"buy|tier|{chat_id}|pro")],
    ])


def _duration_kb(chat_id: int, tier: str) -> InlineKeyboardMarkup:
    rows = []
    for months, lbl in sub.DURATIONS:
        rows.append([InlineKeyboardButton(
            lbl, callback_data=f"buy|dur|{chat_id}|{tier}|{months}")])
    return InlineKeyboardMarkup(rows)


def _method_kb(chat_id: int, tier: str, months: int) -> InlineKeyboardMarkup:
    base = f"buy|pay|{chat_id}|{tier}|{months}"
    rows = [[InlineKeyboardButton("⭐️ پرداخت با استارز", callback_data=f"{base}|stars")]]
    if db.pay_get("method_card_on", "1") == "1":
        rows.append([InlineKeyboardButton("💳 کارت‌به‌کارت", callback_data=f"{base}|card")])
    if db.pay_get("method_crypto_on", "1") == "1":
        rows.append([InlineKeyboardButton("🪙 کریپتو (USDT)", callback_data=f"{base}|crypto")])
    return InlineKeyboardMarkup(rows)


async def _admin_groups(client: Client, user_id: int):
    """گروه‌هایی که کاربر در آنها ادمین است و ربات هم عضو است."""
    out = []
    for chat_id in db.get_chats():
        try:
            m = await client.get_chat_member(chat_id, user_id)
            if m.status.name in ("OWNER", "ADMINISTRATOR"):
                chat = await client.get_chat(chat_id)
                out.append((chat_id, chat.title or str(chat_id)))
        except Exception:  # noqa: BLE001
            continue
    return out


@Client.on_callback_query(filters.regex(r"^buy\|"))
async def buy_cb(client: Client, cq: CallbackQuery):
    parts = cq.data.split("|")
    action = parts[1]

    if action == "start":
        groups = await _admin_groups(client, cq.from_user.id)
        if not groups:
            await cq.answer("اول ربات را به گروهت اضافه کن و ادمین شو.", show_alert=True)
            return
        rows = [[InlineKeyboardButton(title, callback_data=f"buy|grp|{cid}")]
                for cid, title in groups[:20]]
        rows.append([InlineKeyboardButton("📊 اشتراک‌های من", callback_data="buy|mine")])
        rows.append([InlineKeyboardButton("🎁 کد هدیه دارم", callback_data="buy|gift")])
        await cq.message.reply_text(
            "🛒 **خرید اشتراک**\n\nگروهی که می‌خواهی اشتراک برایش بخری را انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        await cq.answer()
        return

    if action == "mine":
        # اشتراک‌های گروه‌هایی که این کاربر خریده/ادمینشه
        groups = await _admin_groups(client, cq.from_user.id)
        lines = ["📊 **وضعیت اشتراک گروه‌های تو:**\n"]
        any_sub = False
        for cid, title in groups:
            s = db.sub_get(cid)
            if s:
                any_sub = True
                lines.append(f"• {title}\n  تیر: {sub.TIER_LABEL.get(s['tier'], s['tier'])} | "
                             f"{sub.expires_text(cid)}")
        if not any_sub:
            lines.append("هیچ اشتراک فعالی نداری.")
        await cq.message.reply_text("\n".join(lines))
        await cq.answer()
        return

    if action == "gift":
        _await_gift[cq.from_user.id] = True
        await cq.message.reply_text(
            "🎁 کد هدیه را بفرست.\nبعد از تأیید، باید گروه مقصد را انتخاب کنی.")
        await cq.answer()
        return

    if action == "gapply":
        # buy|gapply|<code>|<chat_id>
        code, chat_id = parts[2], int(parts[3])
        g = db.gift_get(code)
        if not g or g["used_count"] >= g["max_uses"]:
            await cq.answer("کد نامعتبر یا مصرف‌شده است.", show_alert=True)
            return
        if not db.gift_redeem(code):
            await cq.answer("کد قابل استفاده نیست.", show_alert=True)
            return
        from bot import group_config as gc
        sub.activate(chat_id, g["tier"], g["months"], buyer_id=cq.from_user.id)
        gc.set_enabled(chat_id, True)
        await cq.message.edit_text(
            f"🎁 کد هدیه اعمال شد!\nگروه فعال شد: {sub.TIER_LABEL.get(g['tier'])} — "
            f"{sub.expires_text(chat_id)}")
        try:
            await client.send_message(chat_id, "🎉 اشتراک این گروه با کد هدیه فعال شد!")
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("فعال شد!")
        return

    if action == "grp":
        chat_id = int(parts[2])
        await cq.message.edit_text(
            "پلن (تیر امکانات) را انتخاب کن:\n\n"
            "⭐️ **پایه**: پخش صوت، صف، یوتیوب+ساوندکلاد، پنل\n"
            "💎 **حرفه‌ای**: همه‌ی پایه + ویدیو/فیلم حجیم + پخش رندوم + کیفیت بالاتر",
            reply_markup=_tier_kb(chat_id),
        )
        await cq.answer()
        return

    if action == "tier":
        chat_id, tier = int(parts[2]), parts[3]
        await cq.message.edit_text(
            f"تیر: **{sub.TIER_LABEL[tier]}**\n\nمدت اشتراک را انتخاب کن:",
            reply_markup=_duration_kb(chat_id, tier),
        )
        await cq.answer()
        return

    if action == "dur":
        chat_id, tier, months = int(parts[2]), parts[3], int(parts[4])
        stars = sub.get_price(tier, months, "stars")
        toman = sub.get_price(tier, months, "toman")
        await cq.message.edit_text(
            f"تیر: **{sub.TIER_LABEL[tier]}** | مدت: **{sub.duration_label(months)}**\n\n"
            f"💰 قیمت: **{stars}** استارز  یا  **{toman:,}** تومان\n\n"
            "روش پرداخت را انتخاب کن:",
            reply_markup=_method_kb(chat_id, tier, months),
        )
        await cq.answer()
        return

    if action == "pay":
        chat_id, tier, months, method = int(parts[2]), parts[3], int(parts[4]), parts[5]
        await _start_payment(client, cq, chat_id, tier, months, method)
        return


async def _start_payment(client, cq, chat_id, tier, months, method):
    oid = uuid.uuid4().hex[:16]
    buyer = cq.from_user.id
    if method == "stars":
        stars = sub.get_price(tier, months, "stars")
        db.order_create(oid, buyer, chat_id, tier, months, stars, "stars")
        title = f"اشتراک {sub.TIER_LABEL[tier]} — {sub.duration_label(months)}"
        try:
            link = await client.create_invoice_link(
                title=title,
                description=f"فعال‌سازی ربات موزیک برای گروه (پلن {sub.TIER_LABEL[tier]}).",
                payload=f"{_PAYLOAD_PREFIX}|{oid}",
                currency="XTR",
                prices=[LabeledPrice(label=title, amount=stars)],
            )
        except Exception as e:  # noqa: BLE001
            LOGGER.error("create_invoice_link: %s", e)
            await cq.answer("خطا در ساخت فاکتور استارز.", show_alert=True)
            return
        await cq.message.reply_text(
            f"⭐️ برای پرداخت **{stars}** استارز روی دکمه بزن:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("پرداخت ⭐️", url=link)]]),
        )
        await cq.answer()
        return

    if method == "card":
        toman = sub.get_price(tier, months, "toman")
        card = db.pay_get("card_number", "(تنظیم نشده)")
        holder = db.pay_get("card_holder", "")
        db.order_create(oid, buyer, chat_id, tier, months, toman, "card")
        await cq.message.reply_text(
            f"💳 **کارت‌به‌کارت**\n\n"
            f"مبلغ: **{toman:,} تومان**\n"
            f"شماره کارت: `{card}`\n"
            f"{('به‌نام: ' + holder) if holder else ''}\n\n"
            f"پس از واریز، **عکس رسید** را همین‌جا ریپلای کن روی این پیام و بفرست.\n"
            f"کد سفارش: `{oid}`\n"
            "بعد از تأیید مالک، گروهت فعال می‌شود.",
        )
        await cq.answer()
        return

    if method == "crypto":
        toman = sub.get_price(tier, months, "toman")
        addr = db.pay_get("crypto_addr", "(تنظیم نشده)")
        net = db.pay_get("crypto_net", "TRON (TRC20)")
        rate = int(db.pay_get("usdt_rate", "0") or 0)
        db.order_create(oid, buyer, chat_id, tier, months, toman, "crypto")
        usdt_line = ""
        if rate > 0:
            from bot import crypto_verify as cv
            usdt_line = f"(≈ **{cv.toman_to_usdt(toman, rate)} USDT**)\n"
        await cq.message.reply_text(
            f"🪙 **پرداخت کریپتو ({net})**\n\n"
            f"معادل **{toman:,} تومان** {usdt_line}را به‌صورت **USDT** به این آدرس بفرست:\n`{addr}`\n\n"
            f"سپس **هش تراکنش (TxID)** را همین‌جا ریپلای کن (روی همین پیام).\n"
            f"تأیید خودکار است؛ اگر نشد، دستی بررسی می‌شود.\n"
            f"کد سفارش: `{oid}`",
        )
        await cq.answer()
        return


# --- دریافت کد هدیه (پیام متنی ساده در PV، وقتی کاربر منتظر است) ---
@Client.on_message(filters.private & filters.text, group=-2)
async def gift_input(client: Client, message: Message):
    uid = message.from_user.id if message.from_user else 0
    if not _await_gift.get(uid):
        return
    # اگر ریپلای است، احتمالاً رسید است نه کد هدیه → رد کن
    if message.reply_to_message:
        return
    code = message.text.strip()
    _await_gift.pop(uid, None)
    g = db.gift_get(code)
    if not g:
        await message.reply_text("❌ کد هدیه نامعتبر است.")
        return
    if g["used_count"] >= g["max_uses"]:
        await message.reply_text("❌ ظرفیت این کد هدیه تمام شده است.")
        return
    # انتخاب گروه مقصد
    groups = await _admin_groups(client, uid)
    if not groups:
        await message.reply_text("اول ربات را به گروهت اضافه کن و ادمین شو.")
        return
    rows = [[InlineKeyboardButton(title, callback_data=f"buy|gapply|{code}|{cid}")]
            for cid, title in groups[:20]]
    await message.reply_text(
        f"🎁 کد معتبر است: {sub.TIER_LABEL.get(g['tier'])} — "
        f"{sub.duration_label(g['months'])}\n\nگروه مقصد را انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


# --- دریافت رسید/هش برای سفارش کارت/کریپتو (ریپلای در PV) → فوروارد به مالک ---
@Client.on_message(filters.private & filters.reply
                   & (filters.photo | filters.text | filters.document))
async def receipt_handler(client: Client, message: Message):
    r = message.reply_to_message
    if not r or not r.text:
        return
    # کد سفارش را از متن پیام ریپلای‌شده استخراج کن
    import re
    m = re.search(r"کد سفارش: `?([a-f0-9]{16})`?", r.text or "")
    if not m:
        return
    oid = m.group(1)
    order = db.order_get(oid)
    if not order or order["status"] != "pending":
        return

    # --- کریپتو: تلاش برای تأیید خودکار با TronGrid ---
    if order["method"] == "crypto" and (message.text or ""):
        txid = message.text.strip()
        # ضد استفاده‌ی دوباره: این TxID قبلاً برای سفارش دیگری ثبت نشده باشد
        if _txid_used(txid, oid):
            await message.reply_text("⛔️ این تراکنش قبلاً استفاده شده است.")
            return
        wallet = db.pay_get("crypto_addr", "")
        rate = int(db.pay_get("usdt_rate", "0") or 0)
        if wallet and rate > 0:
            from bot import crypto_verify as cv
            need = cv.toman_to_usdt(order["amount"], rate)
            status = await message.reply_text("🔍 در حال بررسی خودکار تراکنش...")
            ok, reason = await cv.verify_usdt(txid, wallet, need)
            if ok:
                db.order_set_status(oid, "paid", ref=txid)
                await _fulfill(client, order)
                await status.edit_text(f"{reason}\n✅ اشتراک گروه فعال شد!")
                return
            # ناموفق → پیام + سقوط به تأیید دستی
            await status.edit_text(
                f"⚠️ تأیید خودکار نشد: {reason}\n"
                "رسید/تراکنش برای بررسی دستی به مدیریت ارسال شد.")
            db.order_set_status(oid, "pending", ref=txid)  # ذخیره‌ی txid برای مالک

    # به مالک بفرست با دکمه‌های تأیید/رد
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأیید", callback_data=f"ordr|ok|{oid}"),
        InlineKeyboardButton("❌ رد", callback_data=f"ordr|no|{oid}"),
    ]])
    cap = (f"🧾 **رسید سفارش**\nکد: `{oid}`\n"
           f"تیر: {sub.TIER_LABEL.get(order['tier'], order['tier'])} | "
           f"مدت: {sub.duration_label(order['months'])}\n"
           f"مبلغ: {order['amount']:,} | روش: {order['method']}\n"
           f"خریدار: {message.from_user.id}")
    try:
        await message.forward(OWNER_ID)
        await client.send_message(OWNER_ID, cap, reply_markup=kb)
        await message.reply_text("✅ رسید برای بررسی ارسال شد. منتظر تأیید بمان.")
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("forward receipt: %s", e)


def _txid_used(txid: str, current_oid: str) -> bool:
    """آیا این TxID قبلاً برای سفارش paid دیگری استفاده شده؟ (ضد تقلب)."""
    txid = txid.strip()
    for o in db.orders_all_paid():
        if o["id"] != current_oid and (o.get("ref") or "").strip() == txid:
            return True
    return False


# --- تأیید/رد سفارش توسط مالک ---
@Client.on_callback_query(filters.regex(r"^ordr\|"))
async def order_review_cb(client: Client, cq: CallbackQuery):
    if cq.from_user.id != OWNER_ID:
        await cq.answer("فقط مالک.", show_alert=True)
        return
    _, decision, oid = cq.data.split("|")
    order = db.order_get(oid)
    if not order:
        await cq.answer("سفارش یافت نشد.", show_alert=True)
        return
    if decision == "ok":
        db.order_set_status(oid, "paid", ref="manual")
        await _fulfill(client, order)
        await cq.message.edit_text(f"✅ سفارش `{oid}` تأیید و گروه فعال شد.")
    else:
        db.order_set_status(oid, "rejected")
        try:
            await client.send_message(order["buyer_id"],
                                      "❌ سفارش شما رد شد. برای بررسی با پشتیبانی تماس بگیر.")
        except Exception:  # noqa: BLE001
            pass
        await cq.message.edit_text(f"❌ سفارش `{oid}` رد شد.")
    await cq.answer()


async def _fulfill(client: Client, order: dict):
    """اشتراک را فعال و به خریدار/گروه اطلاع می‌دهد."""
    from bot import group_config as gc
    chat_id = order["chat_id"]
    sub.activate(chat_id, order["tier"], order["months"], buyer_id=order["buyer_id"])
    gc.set_enabled(chat_id, True)
    exp = sub.expires_text(chat_id)
    try:
        await client.send_message(
            order["buyer_id"],
            f"✅ اشتراک **{sub.TIER_LABEL.get(order['tier'])}** فعال شد!\n"
            f"وضعیت: {exp}\nربات در گروهت روشن شد. 🎵",
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        await client.send_message(
            chat_id,
            f"🎉 اشتراک این گروه فعال شد ({sub.TIER_LABEL.get(order['tier'])} — {exp}).\n"
            "حالا می‌تونید موزیک پخش کنید! 🎵",
        )
    except Exception:  # noqa: BLE001
        pass


# --- Stars: pre-checkout (باید سریع ok بدهد) ---
@Client.on_pre_checkout_query()
async def pre_checkout(client: Client, pcq):
    try:
        await pcq.answer(ok=True)
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("pre_checkout: %s", e)


# --- Stars: پرداخت موفق ---
@Client.on_message(filters.successful_payment)
async def on_paid(client: Client, message: Message):
    sp = message.successful_payment
    payload = sp.invoice_payload or ""
    if not payload.startswith(f"{_PAYLOAD_PREFIX}|"):
        return
    oid = payload.split("|", 1)[1]
    order = db.order_get(oid)
    if not order or order["status"] == "paid":
        return
    db.order_set_status(oid, "paid", ref=sp.telegram_payment_charge_id or "stars")
    await _fulfill(client, order)
