"""«اشتراک من» — کاربر اشتراک گروه‌هایش را می‌بیند و تمدید می‌کند.

طرح تأییدشده:
  اشتراک من
    └─ لیست گروه‌ها (هر گروه یک دکمه با «N روز مانده»)
         └─ جزئیات گروه → [تمدید اشتراک]

اشتراک با اسم گروه ذخیره می‌شود (اسم زمان نمایش از تلگرام گرفته می‌شود، پس
تغییر نام گروه هم خودکار اعمال می‌شود).

الگوی callback: `my|list` · `my|sub|<chat_id>` · `my|renew|<chat_id>`
"""
from __future__ import annotations

import logging
from typing import List, Tuple

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from bot import database as db
from bot import subscription as sub
from bot import ui
from bot.facmd import fa_command
from bot.plugins import buy

LOGGER = logging.getLogger("musicbot.mysub")


async def my_groups(client: Client, user_id: int) -> List[Tuple[int, str]]:
    """گروه‌هایی که این کاربر ادمینشان است **و** رکورد اشتراک دارند."""
    out = []
    for chat_id, name in await buy.admin_groups(client, user_id):
        if sub.has_subscription(chat_id):
            out.append((chat_id, name))
    return out


# ---------------------------------------------------------------- صفحه‌ها
def page_list(groups: List[Tuple[int, str]]):
    t = ui.Text().title(ui.EMO_LIST, ui.BASE_ARROW, "اشتراک من")
    if not groups:
        t.add("هیچ اشتراکی برای گروه‌های تو ثبت نشده.\n")
        t.italic("برای شروع، اشتراک بخر.")
        rows = [[ui.btn("خرید اشتراک", "buy|start", ui.GREEN, ui.EMO_DOWNLOAD)]]
        return t.text, t.entities, ui.kb(rows)

    t.italic("گروهی که می‌خواهی وضعیتش را ببینی انتخاب کن:")
    rows = [[ui.btn(f"{ui.trunc(name, 22)}  ·  {ui.fa(sub.status_text(cid))}",
                    f"my|sub|{cid}")]
            for cid, name in groups]
    rows.append([ui.btn("خرید اشتراک جدید", "buy|start", ui.GREEN,
                        ui.EMO_DOWNLOAD)])
    return t.text, t.entities, ui.kb(rows)


def page_detail(chat_id: int, name: str):
    active = sub.is_active(chat_id)
    paused = sub.is_paused(chat_id)
    expired = sub.is_expired(chat_id)

    t = ui.Text().title(ui.EMO_HEADPHONE, ui.BASE_HEADPHONE, ui.trunc(name, 34))
    if paused:
        t.field(0, "وضعیت", "مکث‌شده")
        t.field(1, "باقی‌مانده", ui.fa(sub.status_text(chat_id)))
        t.add("\n")
        t.italic("اشتراک این گروه توسط مدیریت موقتاً مکث شده است.")
    elif expired:
        t.field(0, "وضعیت", "منقضی شده")
        t.add("\n")
        t.italic("ربات در این گروه از کار افتاده است. برای فعال‌سازی تمدید کن.")
    else:
        t.field(0, "وضعیت", "فعال")
        t.field(1, "باقی‌مانده", ui.fa(sub.status_text(chat_id)))
        if sub.days_left(chat_id) == -1:
            t.add("\n")
            t.italic("این اشتراک دائمی است.")

    rows = []
    if sub.days_left(chat_id) != -1:
        rows.append([ui.btn("تمدید اشتراک", f"my|renew|{chat_id}", ui.GREEN,
                            ui.EMO_DOWNLOAD)])
    rows.append([ui.btn("بازگشت", "my|list", ui.BLUE, ui.EMO_BACK)])
    return t.text, t.entities, ui.kb(rows)


# ---------------------------------------------------------------- روتر
async def _edit(cq: CallbackQuery, payload) -> None:
    text, ents, kb = payload
    try:
        await cq.message.edit_text(text, entities=ents, reply_markup=kb)
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("mysub edit: %s", e)


@Client.on_callback_query(filters.regex(r"^my\|"))
async def mysub_cb(client: Client, cq: CallbackQuery):
    if not cq.from_user:
        await cq.answer()
        return
    parts = str(cq.data or "").split("|")
    action = parts[1] if len(parts) > 1 else ""
    uid = cq.from_user.id

    if action == "list":
        await _edit(cq, page_list(await my_groups(client, uid)))
        await cq.answer()
        return

    if action == "sub":
        try:
            chat_id = int(parts[2])
        except (IndexError, ValueError):
            await cq.answer("گروه نامعتبر", show_alert=True)
            return
        name = await buy.chat_title(client, chat_id)
        await _edit(cq, page_detail(chat_id, name))
        await cq.answer()
        return

    if action == "renew":
        try:
            chat_id = int(parts[2])
        except (IndexError, ValueError):
            await cq.answer("گروه نامعتبر", show_alert=True)
            return
        name = await buy.chat_title(client, chat_id)
        # جریان خرید را روی همین گروه تنظیم کن تا کاربر دوباره انتخاب نکند
        buy._flow.setdefault(uid, {}).update({"chat_id": chat_id, "name": name})
        await _edit(cq, buy.page_methods(name, chat_id, renew=True))
        await cq.answer()
        return

    await cq.answer()


@Client.on_message(filters.private & fa_command(["اشتراک من", "اشتراک‌های من",
                                                "اشتراک های من"]))
async def mysub_cmd(client: Client, message: Message):
    if not message.from_user:
        return
    text, ents, kb = page_list(await my_groups(client, message.from_user.id))
    await message.reply_text(text, entities=ents, reply_markup=kb)
