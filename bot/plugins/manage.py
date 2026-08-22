"""پنل مدیریت مالک (PV) — گروه‌های اشتراک‌دار / بدون اشتراک / مدیریت فروش.

درخت تأییدشده:
    مدیریت
      ├─ [سفارش‌های در انتظار (n)]        فقط وقتی سفارشی باشد
      ├─ گروه‌های اشتراک‌دار
      │    └─ گروه → [−۷][−۱][+۱][+۷] · [+۱ماه][+۳ماه]
      │              [مکث/ادامه] [لغو اشتراک]
      ├─ گروه‌های بدون اشتراک
      │    └─ گروه → [روشن][خاموش]
      │              [−۷][−۱][+۱][+۷] مهلت · [بدون مهلت]
      └─ مدیریت فروش
           ├─ کارت به کارت → [شماره کارت‌ها][قیمت‌گذاری]
           ├─ کریپتو       → [آدرس ولت][شبکه][قیمت‌گذاری]
           └─ استارز       → [قیمت‌گذاری]

الگوی callback: `adm|<action>[|<arg>[|<arg2>]]`
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import auth
from bot import database as db
from bot import group_config as gc
from bot import subscription as sub
from bot import ui
from bot.facmd import fa_command
from bot.plugins import buy

LOGGER = logging.getLogger("musicbot.manage")

# مالکی که منتظر ورودی متنی است: user_id → کلید ورودی
# (افزودن کارت، تغییر قیمت، آدرس ولت، شبکه)
_awaiting: dict = {}

INPUT_CARD = "card_add"
INPUT_WALLET = "wallet"
INPUT_NETWORK = "network"
INPUT_PRICE = "price"       # price|<method>|<months>


def awaiting(user_id: int) -> Optional[str]:
    return _awaiting.get(user_id)


def _is_owner(uid: int) -> bool:
    return uid == auth.OWNER_ID


# ---------------------------------------------------------------- کمکی
async def _group_name(client: Client, chat_id: int) -> str:
    return await buy.chat_title(client, chat_id)


def _subbed_ids() -> List[int]:
    return [int(r["chat_id"]) for r in db.sub_all()]


def _free_ids() -> List[int]:
    subbed = set(_subbed_ids())
    return [cid for cid in db.get_chats() if cid not in subbed]


def _free_state(chat_id: int) -> str:
    on = gc.is_enabled(chat_id)
    days = sub.free_days_left(chat_id)
    if on and days:
        return f"روشن · {ui.fa(days)} روز مهلت"
    return "روشن" if on else "خاموش"


# ---------------------------------------------------------------- صفحه‌ها
def page_main(n_subbed: int, n_free: int, n_pending: int):
    t = ui.Text().title(ui.EMO_GEAR, ui.BASE_ARROW, "مدیریت")
    t.field(0, "گروه‌های اشتراک‌دار", f"{ui.fa(n_subbed)} گروه")
    t.field(1, "گروه‌های بدون اشتراک", f"{ui.fa(n_free)} گروه")
    t.field(2, "سفارش در انتظار", ui.fa(n_pending) if n_pending else "ندارد")

    rows = []
    if n_pending:
        rows.append([ui.btn(f"سفارش‌های در انتظار ({ui.fa(n_pending)})",
                            "adm|pending", ui.RED, ui.EMO_BELL)])
    rows += [
        [ui.btn("گروه‌های اشتراک‌دار", "adm|subbed", ui.PLAIN, ui.EMO_LIST)],
        [ui.btn("گروه‌های بدون اشتراک", "adm|free", ui.PLAIN, ui.EMO_HEADPHONE)],
        [ui.btn("مدیریت فروش", "adm|sales", ui.BLUE, ui.EMO_DOWNLOAD)],
        [ui.btn("بستن", "adm|close", ui.RED, ui.EMO_CLOSE)],
    ]
    return t.text, t.entities, ui.kb(rows)


def page_subbed(groups: List[Tuple[int, str]]):
    t = ui.Text().title(ui.EMO_LIST, ui.BASE_ARROW, "گروه‌های اشتراک‌دار")
    if not groups:
        t.add("هیچ گروهی اشتراک ندارد.\n")
        return t.text, t.entities, ui.kb([_back_row("adm|main")])
    t.italic("گروه را انتخاب کن:")
    rows = [[ui.btn(f"{ui.trunc(name, 22)}  ·  {ui.fa(sub.status_text(cid))}",
                    f"adm|sub|{cid}")]
            for cid, name in groups]
    rows.append(_back_row("adm|main"))
    return t.text, t.entities, ui.kb(rows)


def page_sub(chat_id: int, name: str, buyer_name: str = ""):
    paused = sub.is_paused(chat_id)
    permanent = sub.days_left(chat_id) == -1

    t = ui.Text().title(ui.EMO_HEADPHONE, ui.BASE_HEADPHONE, ui.trunc(name, 34))
    t.field(0, "وضعیت اشتراک", "مکث‌شده" if paused else
            ("منقضی شده" if sub.is_expired(chat_id) else "فعال"))
    t.field(1, "باقی‌مانده", ui.fa(sub.status_text(chat_id)))
    if buyer_name:
        t.field(2, "خریدار", buyer_name)
    t.field(3 if buyer_name else 2, "شناسه گروه", code=str(chat_id))
    if paused:
        t.add("\n")
        t.italic("در حالت مکث، زمان باقی‌مانده مصرف نمی‌شود و ربات خاموش است.")

    rows = []
    if not permanent:
        rows.append([
            ui.btn("− ۷ روز", f"adm|day|{chat_id}|-7", ui.RED),
            ui.btn("− ۱ روز", f"adm|day|{chat_id}|-1", ui.RED),
            ui.btn("+ ۱ روز", f"adm|day|{chat_id}|1", ui.GREEN),
            ui.btn("+ ۷ روز", f"adm|day|{chat_id}|7", ui.GREEN),
        ])
        rows.append([
            ui.btn("+ ۱ ماه", f"adm|day|{chat_id}|30", ui.GREEN),
            ui.btn("+ ۳ ماه", f"adm|day|{chat_id}|90", ui.GREEN),
            ui.btn("دائمی", f"adm|perm|{chat_id}", ui.GREEN),
        ])
    if paused:
        rows.append([ui.btn("ادامه اشتراک", f"adm|resume|{chat_id}", ui.GREEN,
                            ui.EMO_PLAY)])
    else:
        rows.append([ui.btn("مکث اشتراک", f"adm|pause|{chat_id}", ui.PLAIN,
                            ui.EMO_PAUSE)])
    rows.append([ui.btn("لغو اشتراک", f"adm|cancel|{chat_id}", ui.RED,
                        ui.EMO_STOP)])
    rows.append(_back_row("adm|subbed"))
    return t.text, t.entities, ui.kb(rows)


def page_free(groups: List[Tuple[int, str]]):
    t = ui.Text().title(ui.EMO_HEADPHONE, ui.BASE_HEADPHONE,
                        "گروه‌های بدون اشتراک")
    if not groups:
        t.add("همه‌ی گروه‌ها اشتراک دارند.\n")
        return t.text, t.entities, ui.kb([_back_row("adm|main")])
    t.italic("گروه را انتخاب کن:")
    rows = [[ui.btn(f"{ui.trunc(name, 20)}  ·  {_free_state(cid)}",
                    f"adm|fg|{cid}")]
            for cid, name in groups]
    rows.append(_back_row("adm|main"))
    return t.text, t.entities, ui.kb(rows)


def page_free_group(chat_id: int, name: str):
    on = gc.is_enabled(chat_id)
    days = sub.free_days_left(chat_id)

    t = ui.Text().title(ui.EMO_HEADPHONE, ui.BASE_HEADPHONE, ui.trunc(name, 34))
    t.field(0, "اشتراک", "ندارد")
    t.field(1, "وضعیت ربات", "روشن" if on else "خاموش")
    t.field(2, "مهلت روشن ماندن", f"{ui.fa(days)} روز" if days else "بدون مهلت")
    t.field(3, "شناسه گروه", code=str(chat_id))
    if on and days:
        t.add("\n")
        t.italic("پس از پایان مهلت، ربات خودکار خاموش می‌شود.")

    rows = [[
        ui.btn("روشن", f"adm|on|{chat_id}", ui.GREEN if on else ui.PLAIN,
               ui.EMO_PLAY),
        ui.btn("خاموش", f"adm|off|{chat_id}", ui.RED if not on else ui.PLAIN,
               ui.EMO_STOP),
    ]]
    if on:
        rows.append([
            ui.btn("− ۷ روز", f"adm|fday|{chat_id}|-7", ui.RED),
            ui.btn("− ۱ روز", f"adm|fday|{chat_id}|-1", ui.RED),
            ui.btn("+ ۱ روز", f"adm|fday|{chat_id}|1", ui.GREEN),
            ui.btn("+ ۷ روز", f"adm|fday|{chat_id}|7", ui.GREEN),
        ])
        rows.append([ui.btn("بدون مهلت (نامحدود)", f"adm|funlim|{chat_id}",
                            ui.BLUE)])
    rows.append(_back_row("adm|free"))
    return t.text, t.entities, ui.kb(rows)


def page_sales():
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "مدیریت فروش")
    t.field(0, "کارت به کارت",
            f"{ui.fa(len(db.cards_all()))} کارت ثبت‌شده"
            if sub.method_enabled(sub.METHOD_CARD) else "خاموش")
    t.field(1, "کریپتو", sub.network()
            if sub.method_enabled(sub.METHOD_CRYPTO) else "خاموش")
    t.field(2, "استارز", "فعال"
            if sub.method_enabled(sub.METHOD_STARS) else "خاموش")
    rows = [
        [ui.btn("کارت به کارت", "adm|s|card")],
        [ui.btn("کریپتو (USDT)", "adm|s|crypto")],
        [ui.btn("استارز تلگرام", "adm|s|stars")],
        _back_row("adm|main"),
    ]
    return t.text, t.entities, ui.kb(rows)


def _method_toggle_btn(method: str):
    on = sub.method_enabled(method)
    return ui.btn("فعال است — خاموش کن" if on else "خاموش است — فعال کن",
                  f"adm|mtog|{method}", ui.GREEN if on else ui.RED)


def page_card():
    cards = db.cards_all()
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "کارت به کارت")
    if cards:
        for i, c in enumerate(cards, 1):
            t.emoji(ui.alt_arrow(i - 1)).add(f" کارت {ui.fa(i)} : ")
            t.code(c["number"])
            if c.get("holder"):
                t.add(f"  ·  {c['holder']}")
            t.add("\n")
    else:
        t.add("هیچ کارتی ثبت نشده.\n")
    t.add("\n")
    t.bold("قیمت‌ها:")
    t.add("\n")
    for i, m in enumerate(sub.DURATIONS):
        t.emoji(ui.alt_arrow(i)).add(
            f" {sub.duration_label(m)} : {ui.fa(sub.price_text(sub.METHOD_CARD, m))}\n")
    rows = [
        [ui.btn("شماره کارت‌ها", "adm|cards"),
         ui.btn("قیمت‌گذاری", "adm|price|card", ui.BLUE)],
        [_method_toggle_btn(sub.METHOD_CARD)],
        _back_row("adm|sales"),
    ]
    return t.text, t.entities, ui.kb(rows)


def page_cards():
    cards = db.cards_all()
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "شماره کارت‌ها")
    if cards:
        for i, c in enumerate(cards, 1):
            t.emoji(ui.alt_arrow(i - 1)).add(f" کارت {ui.fa(i)} : ")
            t.code(c["number"])
            if c.get("holder"):
                t.add(f"  ·  {c['holder']}")
            t.add("\n")
    else:
        t.add("هیچ کارتی ثبت نشده.\n")
        t.italic("با دکمه‌ی زیر کارت اضافه کن.")
    rows = []
    if cards:
        rows.append([ui.btn(f"حذف کارت {ui.fa(i)}", f"adm|cdel|{c['id']}", ui.RED)
                     for i, c in enumerate(cards, 1)])
    rows.append([ui.btn("افزودن کارت", "adm|cadd", ui.GREEN)])
    rows.append(_back_row("adm|s|card"))
    return t.text, t.entities, ui.kb(rows)


def page_crypto():
    addr = sub.wallet()
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "کریپتو (USDT)")
    if addr:
        t.field(0, "آدرس کیف‌پول", code=addr)
    else:
        t.emoji(ui.EMO_ARROW_BLUE).add(" آدرس کیف‌پول : ثبت نشده\n")
    t.field(1, "شبکه", sub.network())
    t.add("\n")
    t.bold("قیمت‌ها:")
    t.add("\n")
    for i, m in enumerate(sub.DURATIONS):
        t.emoji(ui.alt_arrow(i)).add(
            f" {sub.duration_label(m)} : "
            f"{ui.fa(sub.price_text(sub.METHOD_CRYPTO, m))}\n")
    rows = [
        [ui.btn("تغییر آدرس کیف‌پول", "adm|set|wallet"),
         ui.btn("تغییر شبکه", "adm|set|network")],
        [ui.btn("قیمت‌گذاری", "adm|price|crypto", ui.BLUE)],
        [_method_toggle_btn(sub.METHOD_CRYPTO)],
        _back_row("adm|sales"),
    ]
    return t.text, t.entities, ui.kb(rows)


def page_stars():
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "استارز تلگرام")
    t.italic("تأیید آنی — بدون نیاز به بررسی مالک.")
    t.add("\n\n")
    t.bold("قیمت‌ها:")
    t.add("\n")
    for i, m in enumerate(sub.DURATIONS):
        t.emoji(ui.alt_arrow(i)).add(
            f" {sub.duration_label(m)} : "
            f"{ui.fa(sub.price_text(sub.METHOD_STARS, m))}\n")
    rows = [
        [ui.btn("قیمت‌گذاری", "adm|price|stars", ui.BLUE)],
        [_method_toggle_btn(sub.METHOD_STARS)],
        _back_row("adm|sales"),
    ]
    return t.text, t.entities, ui.kb(rows)


def page_price(method: str):
    t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW,
                        f"قیمت‌گذاری — {sub.METHOD_LABEL[method]}")
    t.italic("روی هر اشتراک بزن تا قیمتش را عوض کنی:")
    t.add("\n\n")
    for i, m in enumerate(sub.DURATIONS):
        t.emoji(ui.alt_arrow(i)).add(
            f" {sub.duration_label(m)} : {ui.fa(sub.price_text(method, m))}\n")
    rows = [[ui.btn(f"{sub.duration_label(m)}  ·  "
                    f"{ui.fa(sub.price_text(method, m))}",
                    f"adm|pset|{method}|{m}")]
            for m in sub.DURATIONS]
    rows.append(_back_row(f"adm|s|{method}"))
    return t.text, t.entities, ui.kb(rows)


def page_pending(orders: List[dict], names: dict):
    t = ui.Text().title(ui.EMO_BELL, ui.BASE_ARROW, "سفارش‌های در انتظار تأیید")
    if not orders:
        t.add("سفارشی در انتظار نیست.\n")
        return t.text, t.entities, ui.kb([_back_row("adm|main")])
    for i, o in enumerate(orders[:10]):
        name = names.get(int(o["chat_id"]), str(o["chat_id"]))
        t.emoji(ui.alt_arrow(i)).add(f" {ui.trunc(name, 20)}  ·  "
                                    f"{sub.duration_label(int(o['months']))}\n")
        t.add(f"      {ui.fa(_amount(o))}  ·  "
              f"{sub.METHOD_LABEL.get(o['method'], o['method'])}  ·  ")
        t.code(str(o["id"])[:8])
        t.add("\n")
    rows = [[ui.btn(f"تأیید {ui.fa(i)}", f"ord|ok|{o['id']}", ui.GREEN),
             ui.btn(f"لغو {ui.fa(i)}", f"ord|no|{o['id']}", ui.RED)]
            for i, o in enumerate(orders[:10], 1)]
    rows.append(_back_row("adm|main"))
    return t.text, t.entities, ui.kb(rows)


def _amount(order: dict) -> str:
    method = order.get("method", "")
    amount = int(order.get("amount") or 0)
    unit = sub.CURRENCY_LABEL.get(method, "")
    if method == sub.METHOD_CRYPTO:
        return f"{amount / 100:g} {unit}"
    return f"{amount:,} {unit}"


def _back_row(target: str):
    return [ui.btn("بازگشت", target, ui.BLUE, ui.EMO_BACK)]


# ---------------------------------------------------------------- روتر
async def _edit(cq: CallbackQuery, payload) -> None:
    text, ents, kb = payload
    try:
        await cq.message.edit_text(text, entities=ents, reply_markup=kb)
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("manage edit: %s", e)


async def _main_payload(client: Client):
    return page_main(len(_subbed_ids()), len(_free_ids()),
                     len(db.orders_pending()))


@Client.on_callback_query(filters.regex(r"^adm\|"))
async def manage_cb(client: Client, cq: CallbackQuery):
    if not cq.from_user or not _is_owner(cq.from_user.id):
        await cq.answer("فقط مالک به این پنل دسترسی دارد.", show_alert=True)
        return

    parts = str(cq.data or "").split("|")
    action = parts[1] if len(parts) > 1 else ""
    a1 = parts[2] if len(parts) > 2 else None
    a2 = parts[3] if len(parts) > 3 else None
    uid = cq.from_user.id

    if action == "close":
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("بسته شد")
        return

    if action == "main":
        _awaiting.pop(uid, None)
        await _edit(cq, await _main_payload(client))
        await cq.answer()
        return

    # ---------------- سفارش‌های در انتظار ----------------
    if action == "pending":
        orders = db.orders_pending()
        names = {}
        for o in orders[:10]:
            cid = int(o["chat_id"])
            names[cid] = await _group_name(client, cid)
        await _edit(cq, page_pending(orders, names))
        await cq.answer()
        return

    # ---------------- گروه‌های اشتراک‌دار ----------------
    if action == "subbed":
        groups = [(cid, await _group_name(client, cid)) for cid in _subbed_ids()]
        await _edit(cq, page_subbed(groups))
        await cq.answer()
        return

    if action == "sub":
        cid = _int(a1)
        if cid is None:
            await cq.answer("گروه نامعتبر", show_alert=True)
            return
        await _edit(cq, page_sub(cid, await _group_name(client, cid)))
        await cq.answer()
        return

    if action == "day":
        cid, days = _int(a1), _int(a2)
        if cid is None or days is None:
            await cq.answer("مقدار نامعتبر", show_alert=True)
            return
        if sub.add_days(cid, days) is None:
            await cq.answer("این گروه اشتراک ندارد.", show_alert=True)
            return
        await _edit(cq, page_sub(cid, await _group_name(client, cid)))
        await cq.answer(f"{'+' if days > 0 else ''}{ui.fa(days)} روز اعمال شد")
        return

    if action == "perm":
        cid = _int(a1)
        if cid is None:
            await cq.answer("گروه نامعتبر", show_alert=True)
            return
        sub.make_permanent(cid)
        await _edit(cq, page_sub(cid, await _group_name(client, cid)))
        await cq.answer("اشتراک دائمی شد")
        return

    if action == "pause":
        cid = _int(a1)
        if cid is None:
            return
        ok = sub.pause(cid)
        gc.set_enabled(cid, False)
        await _edit(cq, page_sub(cid, await _group_name(client, cid)))
        await cq.answer("اشتراک مکث شد" if ok else "قبلاً مکث بود")
        return

    if action == "resume":
        cid = _int(a1)
        if cid is None:
            return
        ok = sub.resume(cid)
        if ok:
            gc.set_enabled(cid, True)
        await _edit(cq, page_sub(cid, await _group_name(client, cid)))
        await cq.answer("اشتراک ادامه یافت" if ok else "مکث نبود")
        return

    if action == "cancel":
        cid = _int(a1)
        if cid is None:
            return
        sub.cancel(cid)
        gc.set_enabled(cid, False)
        groups = [(c, await _group_name(client, c)) for c in _subbed_ids()]
        await _edit(cq, page_subbed(groups))
        await cq.answer("اشتراک لغو شد و ربات خاموش شد")
        return

    # ---------------- گروه‌های بدون اشتراک ----------------
    if action == "free":
        groups = [(cid, await _group_name(client, cid)) for cid in _free_ids()]
        await _edit(cq, page_free(groups))
        await cq.answer()
        return

    if action == "fg":
        cid = _int(a1)
        if cid is None:
            return
        await _edit(cq, page_free_group(cid, await _group_name(client, cid)))
        await cq.answer()
        return

    if action in ("on", "off"):
        cid = _int(a1)
        if cid is None:
            return
        gc.set_enabled(cid, action == "on")
        await _edit(cq, page_free_group(cid, await _group_name(client, cid)))
        await cq.answer("روشن شد" if action == "on" else "خاموش شد")
        return

    if action == "fday":
        cid, days = _int(a1), _int(a2)
        if cid is None or days is None:
            return
        sub.add_free_days(cid, days)
        await _edit(cq, page_free_group(cid, await _group_name(client, cid)))
        await cq.answer(f"مهلت: {ui.fa(sub.free_days_left(cid))} روز")
        return

    if action == "funlim":
        cid = _int(a1)
        if cid is None:
            return
        sub.set_unlimited_free(cid)
        gc.set_enabled(cid, True)
        await _edit(cq, page_free_group(cid, await _group_name(client, cid)))
        await cq.answer("بدون مهلت (نامحدود) شد")
        return

    # ---------------- مدیریت فروش ----------------
    if action == "sales":
        await _edit(cq, page_sales())
        await cq.answer()
        return

    if action == "s":
        pages = {"card": page_card, "crypto": page_crypto, "stars": page_stars}
        fn = pages.get(a1 or "")
        if not fn:
            await cq.answer()
            return
        await _edit(cq, fn())
        await cq.answer()
        return

    if action == "mtog":
        method = a1 or ""
        if method not in sub.METHODS:
            await cq.answer()
            return
        new = not sub.method_enabled(method)
        sub.set_method_enabled(method, new)
        pages = {"card": page_card, "crypto": page_crypto, "stars": page_stars}
        await _edit(cq, pages[method]())
        await cq.answer("فعال شد" if new else "خاموش شد")
        return

    if action == "cards":
        await _edit(cq, page_cards())
        await cq.answer()
        return

    if action == "cdel":
        cid_ = _int(a1)
        if cid_ is None:
            return
        ok = db.card_delete(cid_)
        await _edit(cq, page_cards())
        await cq.answer("کارت حذف شد" if ok else "کارت پیدا نشد")
        return

    if action == "cadd":
        _awaiting[uid] = INPUT_CARD
        await cq.answer()
        await _ask(cq, "افزودن کارت",
                   "شماره کارت و نام صاحب کارت را در یک پیام بفرست:",
                   "6037997712345678 علی رضایی")
        return

    if action == "set":
        if a1 == "wallet":
            _awaiting[uid] = INPUT_WALLET
            await cq.answer()
            await _ask(cq, "آدرس کیف‌پول", "آدرس جدید کیف‌پول را بفرست:",
                       "TXn8kR4mQp7vZ2wLd9Fq2sYbN6hJ3xAe1")
        elif a1 == "network":
            _awaiting[uid] = INPUT_NETWORK
            await cq.answer()
            await _ask(cq, "شبکه", "نام شبکه را بفرست:", "TRC20 (TRON)")
        else:
            await cq.answer()
        return

    if action == "price":
        method = a1 or ""
        if method not in sub.METHODS:
            await cq.answer()
            return
        await _edit(cq, page_price(method))
        await cq.answer()
        return

    if action == "pset":
        method, months = a1 or "", _int(a2)
        if method not in sub.METHODS or months not in sub.DURATIONS:
            await cq.answer("انتخاب نامعتبر", show_alert=True)
            return
        _awaiting[uid] = f"{INPUT_PRICE}|{method}|{months}"
        await cq.answer()
        unit = sub.CURRENCY_LABEL[method]
        example = "1.5" if method == sub.METHOD_CRYPTO else "120000"
        await _ask(cq, f"قیمت {sub.duration_label(months)}",
                   f"قیمت جدید را به {unit} بفرست:", example)
        return

    await cq.answer()


def _int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


async def _ask(cq: CallbackQuery, title: str, prompt: str, example: str) -> None:
    t = ui.Text().title(ui.EMO_GEAR, ui.BASE_ARROW, title)
    t.add(prompt + "\n\n")
    t.emoji(ui.EMO_ARROW_BLUE).add(" نمونه : ")
    t.code(example)
    t.add("\n")
    kb = ui.kb([_back_row("adm|main")])
    try:
        await cq.message.edit_text(t.text, entities=t.entities, reply_markup=kb)
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("ask: %s", e)


# ---------------------------------------------------------------- ورودی متنی
@Client.on_message(filters.private & filters.text, group=3)
async def manage_input(client: Client, message: Message):
    """ورودی متنی مالک برای افزودن کارت / تغییر قیمت / ولت / شبکه."""
    if not message.from_user or not _is_owner(message.from_user.id):
        return
    uid = message.from_user.id
    key = _awaiting.get(uid)
    if not key:
        return
    raw = (message.text or "").strip()
    if not raw:
        return
    _awaiting.pop(uid, None)

    if key == INPUT_CARD:
        parts = raw.split(maxsplit=1)
        number = parts[0]
        holder = parts[1] if len(parts) > 1 else ""
        db.card_add(number, holder)
        await _reply(message, page_cards(), "کارت اضافه شد")
        return

    if key == INPUT_WALLET:
        sub.set_wallet(raw)
        await _reply(message, page_crypto(), "آدرس کیف‌پول ذخیره شد")
        return

    if key == INPUT_NETWORK:
        sub.set_network(raw)
        await _reply(message, page_crypto(), "شبکه ذخیره شد")
        return

    if key.startswith(INPUT_PRICE):
        _, method, months_s = key.split("|")
        try:
            value = float(raw.replace(",", "").replace("،", ""))
        except ValueError:
            t = ui.Text().title(ui.EMO_STOP, ui.BASE_ARROW, "مقدار نامعتبر")
            t.why("عددی که فرستادی خوانده نشد.")
            t.how("فقط عدد بفرست، بدون واحد.")
            await message.reply_text(t.text, entities=t.entities)
            return
        sub.set_price(method, int(months_s), value)
        await _reply(message, page_price(method), "قیمت ذخیره شد")
        return


async def _reply(message: Message, payload, note: str) -> None:
    text, ents, kb = payload
    t = ui.Text().title(ui.EMO_PLAY, ui.BASE_ARROW, note)
    await message.reply_text(t.text, entities=t.entities)
    await message.reply_text(text, entities=ents, reply_markup=kb)


# ---------------------------------------------------------------- دستور
@Client.on_message(fa_command(["مدیریت", "پنل مدیریت", "مدیریت اشتراک"]))
async def manage_cmd(client: Client, message: Message):
    if not message.from_user or not _is_owner(message.from_user.id):
        return                                  # فقط مالک — بی‌صدا
    text, ents, kb = page_main(len(_subbed_ids()), len(_free_ids()),
                               len(db.orders_pending()))
    await message.reply_text(text, entities=ents, reply_markup=kb)
