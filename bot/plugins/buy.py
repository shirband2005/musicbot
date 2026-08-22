"""جریان خرید اشتراک — سمت کاربر (PV).

مسیر تأییدشده:
    خرید اشتراک
      ├─ گروه مشترکی ندارد → راهنما + دکمه‌ی افزودن به گروه
      └─ لیست گروه‌ها (هر گروه یک دکمه)
           ↓ انتخاب گروه
         روش پرداخت: کارت / کریپتو / استارز
           ↓
         مدت اشتراک (هر گزینه یک دکمه با قیمت همان روش)
           ↓
         فاکتور
           ├─ کارت   → شماره کارت‌ها با دکمه‌ی کپی + «پرداخت کردم — ارسال فیش»
           ├─ کریپتو → آدرس ولت و شبکه با دکمه‌ی کپی + همان دکمه
           └─ استارز → پرداخت آنی

الگوی callback:
    buy|start                     شروع (لیست گروه‌ها)
    buy|grp|<chat_id>             انتخاب گروه → روش پرداخت
    buy|m|<method>                انتخاب روش → لیست مدت‌ها
    buy|plan|<method>|<months>    ساخت فاکتور
    buy|paid|<oid>                «پرداخت کردم» → درخواست فیش
    buy|cancel|<oid>              انصراف از سفارش
    buy|back                      بازگشت به شروع
"""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional, Tuple

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, LabeledPrice, Message

from bot import database as db
from bot import subscription as sub
from bot import ui
from bot.plugins.start import add_group_url

LOGGER = logging.getLogger("musicbot.buy")

# پیشوند payload فاکتور استارز
PAYLOAD_PREFIX = "musicsub"

# سفارش‌هایی که کاربر «پرداخت کردم» را زده و منتظر فیش‌اند: user_id → order_id
_awaiting_receipt: dict = {}


def awaiting_receipt(user_id: int) -> Optional[str]:
    return _awaiting_receipt.get(user_id)


def clear_awaiting(user_id: int) -> None:
    _awaiting_receipt.pop(user_id, None)


# ---------------------------------------------------------------- گروه‌ها
async def admin_groups(client: Client, user_id: int) -> List[Tuple[int, str]]:
    """گروه‌هایی که ربات عضو است و این کاربر در آن‌ها ادمین/مالک است."""
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


async def chat_title(client: Client, chat_id: int) -> str:
    try:
        chat = await client.get_chat(chat_id)
        return chat.title or str(chat_id)
    except Exception:  # noqa: BLE001
        return str(chat_id)


# ---------------------------------------------------------------- صفحه‌ها
def page_no_group(add_url: str):
    """گروه مشترکی نیست: راهنمای سه‌گامی + دکمه‌ی افزودن."""
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "خرید اشتراک")
    t.add("برای خرید اشتراک، اول باید من را به گروهت اضافه کنی.\n\n")
    t.line(0, "۱. روی دکمه‌ی زیر بزن و گروهت را انتخاب کن")
    t.line(1, "۲. من را در گروه ادمین کن")
    t.line(2, "۳. برگرد اینجا و «خرید اشتراک» را بزن")
    t.add("\n")
    t.italic("هیچ گروه مشترکی با تو ندارم.")
    rows = []
    if add_url:
        rows.append([ui.btn("افزودن به گروه", None, ui.GREEN, None, url=add_url)])
    rows.append([ui.btn("بازگشت", "buy|back", ui.BLUE, ui.EMO_BACK)])
    return t.text, t.entities, ui.kb(rows)


def page_groups(groups: List[Tuple[int, str]], add_url: str = ""):
    """انتخاب گروه — هر گروه یک دکمه‌ی کامل (تصمیم کاربر)."""
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "خرید اشتراک")
    t.italic("اشتراک برای کدام گروه؟")
    rows = [[ui.btn(ui.trunc(name, 34), f"buy|grp|{cid}")]
            for cid, name in groups[:20]]
    if add_url:
        rows.append([ui.btn("افزودن به گروه جدید", None, ui.PLAIN, None,
                            url=add_url)])
    return t.text, t.entities, ui.kb(rows)


def page_methods(group_name: str, chat_id: int, renew: bool = False):
    """انتخاب روش پرداخت. روش خاموش‌شده در پنل مالک نمایش داده نمی‌شود."""
    title = "تمدید اشتراک" if renew else "خرید اشتراک"
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, title)
    t.field(0, "گروه", ui.trunc(group_name, 34))
    if renew:
        t.field(1, "وضعیت فعلی", sub.status_text(chat_id))
    t.add("\n")
    t.italic("روش پرداخت را انتخاب کن:")

    rows = [[ui.btn(sub.METHOD_LABEL[m], f"buy|m|{m}",
                    ui.BLUE if m == sub.METHOD_STARS else ui.PLAIN)]
            for m in sub.enabled_methods()]
    if not rows:
        t.add("\n")
        t.italic("فعلاً هیچ روش پرداختی فعال نیست. با پشتیبانی تماس بگیر.")
    rows.append([ui.btn("بازگشت", "buy|start", ui.BLUE, ui.EMO_BACK)])
    return t.text, t.entities, ui.kb(rows)


def page_plans(group_name: str, method: str):
    """انتخاب مدت — هر گزینه یک دکمه با قیمت (تصمیم کاربر)."""
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "خرید اشتراک")
    t.field(0, "گروه", ui.trunc(group_name, 34))
    t.field(1, "روش پرداخت", sub.METHOD_LABEL[method])
    t.add("\n")
    t.italic("مدت اشتراک را انتخاب کن:")
    rows = [[ui.btn(f"اشتراک {sub.duration_label(m)}  ·  "
                    f"{ui.fa(sub.price_text(method, m))}",
                    f"buy|plan|{method}|{m}")]
            for m in sub.DURATIONS]
    rows.append([ui.btn("بازگشت", "buy|m_back", ui.BLUE, ui.EMO_BACK)])
    return t.text, t.entities, ui.kb(rows)


_APPROVAL_NOTE = ("تأیید توسط مدیریت در تایم کاری انجام می‌شود و حداکثر ۳ ساعت "
                  "طول می‌کشد.")


def page_invoice_card(group_name: str, months: int, oid: str, cards: list):
    """فاکتور کارت به کارت — چند شماره کارت، هر کدام دکمه‌ی کپی."""
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "فاکتور پرداخت")
    t.field(0, "گروه", ui.trunc(group_name, 34))
    t.field(1, "اشتراک", sub.duration_label(months))
    t.field(2, "مبلغ", ui.fa(sub.price_text(sub.METHOD_CARD, months)))
    t.field(3, "کد سفارش", code=oid)
    t.add("\n")
    if cards:
        t.italic("مبلغ را به یکی از کارت‌های زیر واریز کن:")
        t.add("\n")
        for i, c in enumerate(cards, 1):
            t.emoji(ui.alt_arrow(i - 1)).add(f" شماره کارت {ui.fa(i)} : ")
            t.code(c["number"])
            if c.get("holder"):
                t.add(f"  ·  {c['holder']}")
            t.add("\n")
    else:
        t.italic("شماره کارتی ثبت نشده است؛ با پشتیبانی تماس بگیر.")
        t.add("\n")
    t.add("\n")
    t.italic(_APPROVAL_NOTE)

    rows = []
    if cards:
        rows.append([ui.btn(f"کپی کارت {ui.fa(i)}", None, ui.PLAIN, None,
                            copy=c["number"].replace("-", "").replace(" ", ""))
                     for i, c in enumerate(cards, 1)])
        rows.append([ui.btn("پرداخت کردم — ارسال فیش", f"buy|paid|{oid}",
                            ui.GREEN)])
    rows.append([ui.btn("انصراف", f"buy|cancel|{oid}", ui.RED),
                 ui.btn("بازگشت", "buy|m_back", ui.BLUE, ui.EMO_BACK)])
    return t.text, t.entities, ui.kb(rows)


def page_invoice_crypto(group_name: str, months: int, oid: str):
    """فاکتور کریپتو — آدرس ولت و شبکه با دکمه‌ی کپی."""
    addr = sub.wallet()
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "فاکتور پرداخت")
    t.field(0, "گروه", ui.trunc(group_name, 34))
    t.field(1, "اشتراک", sub.duration_label(months))
    t.field(2, "مبلغ", ui.fa(sub.price_text(sub.METHOD_CRYPTO, months)))
    t.field(3, "شبکه", sub.network())
    t.field(4, "کد سفارش", code=oid)
    t.add("\n")
    if addr:
        t.italic("آدرس کیف‌پول:")
        t.add("\n")
        t.code(addr)
        t.add("\n\n")
    else:
        t.italic("آدرس کیف‌پولی ثبت نشده است؛ با پشتیبانی تماس بگیر.")
        t.add("\n\n")
    t.italic(_APPROVAL_NOTE)

    rows = []
    if addr:
        rows.append([ui.btn("کپی آدرس کیف‌پول", None, ui.PLAIN, None, copy=addr)])
        rows.append([ui.btn("پرداخت کردم — ارسال فیش", f"buy|paid|{oid}",
                            ui.GREEN)])
    rows.append([ui.btn("انصراف", f"buy|cancel|{oid}", ui.RED),
                 ui.btn("بازگشت", "buy|m_back", ui.BLUE, ui.EMO_BACK)])
    return t.text, t.entities, ui.kb(rows)


def page_invoice_stars(group_name: str, months: int, link: str):
    """فاکتور استارز — تأیید آنی، بدون نیاز به فیش."""
    stars = sub.get_price(sub.METHOD_STARS, months)
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "فاکتور پرداخت")
    t.field(0, "گروه", ui.trunc(group_name, 34))
    t.field(1, "اشتراک", sub.duration_label(months))
    t.field(2, "مبلغ", f"{ui.fa(stars)} استارز")
    t.add("\n")
    t.italic("پرداخت با استارز آنی است؛ اشتراک بلافاصله فعال می‌شود.")
    rows = []
    if link:
        rows.append([ui.btn(f"پرداخت {ui.fa(stars)} استارز", None, ui.GREEN,
                            None, url=link)])
    rows.append([ui.btn("بازگشت", "buy|m_back", ui.BLUE, ui.EMO_BACK)])
    return t.text, t.entities, ui.kb(rows)


def page_awaiting(oid: str):
    """پس از دریافت فیش."""
    t = ui.Text().title(ui.EMO_BELL, ui.BASE_ARROW, "فیش دریافت شد")
    t.field(0, "کد سفارش", code=oid)
    t.field(1, "وضعیت", "در انتظار تأیید مدیریت")
    t.add("\n")
    t.italic(_APPROVAL_NOTE + " نتیجه همین‌جا به تو اطلاع داده می‌شود.")
    return t.text, t.entities, ui.kb([])


def page_send_receipt(oid: str):
    """درخواست ارسال فیش."""
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "ارسال فیش پرداخت")
    t.field(0, "کد سفارش", code=oid)
    t.add("\n")
    t.italic("عکس رسید پرداخت را همین‌جا بفرست.")
    rows = [[ui.btn("انصراف", f"buy|cancel|{oid}", ui.RED)]]
    return t.text, t.entities, ui.kb(rows)


# ---------------------------------------------------------------- روتر
async def _edit(cq: CallbackQuery, payload) -> None:
    text, ents, kb = payload
    try:
        await cq.message.edit_text(text, entities=ents, reply_markup=kb)
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("buy edit: %s", e)


@Client.on_callback_query(filters.regex(r"^buy\|"))
async def buy_cb(client: Client, cq: CallbackQuery):
    if not cq.from_user:
        await cq.answer()
        return
    parts = str(cq.data or "").split("|")
    action = parts[1] if len(parts) > 1 else ""
    uid = cq.from_user.id

    # وضعیت جریان خرید این کاربر (گروه و روش انتخاب‌شده)
    state = _flow.setdefault(uid, {})

    if action in ("start", "back"):
        groups = await admin_groups(client, uid)
        add_url = await add_group_url(client)
        if not groups:
            await _edit(cq, page_no_group(add_url))
        else:
            state.clear()
            await _edit(cq, page_groups(groups, add_url))
        await cq.answer()
        return

    if action == "grp":
        try:
            chat_id = int(parts[2])
        except (IndexError, ValueError):
            await cq.answer("گروه نامعتبر", show_alert=True)
            return
        name = await chat_title(client, chat_id)
        state["chat_id"] = chat_id
        state["name"] = name
        renew = sub.has_subscription(chat_id)
        await _edit(cq, page_methods(name, chat_id, renew))
        await cq.answer()
        return

    if action == "m_back":
        chat_id = state.get("chat_id")
        if not chat_id:
            await cq.answer()
            return
        await _edit(cq, page_methods(state.get("name", ""), chat_id,
                                    sub.has_subscription(chat_id)))
        await cq.answer()
        return

    if action == "m":
        method = parts[2] if len(parts) > 2 else ""
        if method not in sub.METHODS:
            await cq.answer("روش نامعتبر", show_alert=True)
            return
        if not sub.method_enabled(method):
            await cq.answer("این روش پرداخت فعال نیست.", show_alert=True)
            return
        state["method"] = method
        await _edit(cq, page_plans(state.get("name", ""), method))
        await cq.answer()
        return

    if action == "plan":
        method = parts[2] if len(parts) > 2 else ""
        try:
            months = int(parts[3])
        except (IndexError, ValueError):
            months = 0
        chat_id = state.get("chat_id")
        if not chat_id or method not in sub.METHODS or months not in sub.DURATIONS:
            await cq.answer("انتخاب نامعتبر", show_alert=True)
            return

        oid = uuid.uuid4().hex[:16]
        amount = sub.get_price(method, months)
        # مبلغ در دیتابیس صحیح ذخیره می‌شود؛ برای کریپتو سِنت (×۱۰۰)
        stored = int(round(amount * 100)) if method == sub.METHOD_CRYPTO else int(amount)
        db.order_create(oid, uid, chat_id, "single", months, stored, method)
        state["oid"] = oid

        name = state.get("name", "")
        if method == sub.METHOD_CARD:
            await _edit(cq, page_invoice_card(name, months, oid, db.cards_all()))
        elif method == sub.METHOD_CRYPTO:
            await _edit(cq, page_invoice_crypto(name, months, oid))
        else:
            link = await _stars_link(client, oid, months, name)
            await _edit(cq, page_invoice_stars(name, months, link))
        await cq.answer()
        return

    if action == "paid":
        oid = parts[2] if len(parts) > 2 else ""
        order = db.order_get(oid)
        if not order or order.get("status") != "pending":
            await cq.answer("این سفارش دیگر معتبر نیست.", show_alert=True)
            return
        _awaiting_receipt[uid] = oid
        await _edit(cq, page_send_receipt(oid))
        await cq.answer("عکس رسید را بفرست")
        return

    if action == "cancel":
        oid = parts[2] if len(parts) > 2 else ""
        order = db.order_get(oid)
        if order and order.get("status") == "pending":
            db.order_set_status(oid, "rejected", "انصراف کاربر")
        clear_awaiting(uid)
        groups = await admin_groups(client, uid)
        await _edit(cq, page_groups(groups, await add_group_url(client)))
        await cq.answer("سفارش لغو شد")
        return

    await cq.answer()


# وضعیت جریان خرید هر کاربر (گروه/روش/سفارش جاری)
_flow: dict = {}


async def _stars_link(client: Client, oid: str, months: int, group_name: str) -> str:
    stars = sub.get_price(sub.METHOD_STARS, months)
    title = f"اشتراک {sub.duration_label(months)}"
    try:
        return await client.create_invoice_link(
            title=title,
            description=f"فعال‌سازی ربات موزیک برای گروه {group_name}",
            payload=f"{PAYLOAD_PREFIX}|{oid}",
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=int(stars))],
        )
    except Exception as e:  # noqa: BLE001
        LOGGER.error("create_invoice_link: %s", e)
        return ""
