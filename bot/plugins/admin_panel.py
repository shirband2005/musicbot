"""پنل «مدیریت پلیر» — فقط برای مالک، داخل گروه.

با دستور «مدیریت پلیر» در گروه باز می‌شود و تنظیمات همان گروه را نشان می‌دهد:
  · روشن/خاموش کردن پلیر برای گروه (فعال رنگی، غیرفعال بی‌رنگ)
  · قفل پلتفرم (آکاردئونی، مثل پنل پخش)
  · میان‌بر مدیریت اشتراک همان گروه

تغییرها نسبت به نسخه‌ی قبلی:
  · دکمه‌ی «انتخاب پلتفرم» که فقط `noop` بود و کاری نمی‌کرد، حذف شد
  · قرمزِ «این حالت نیست» حذف شد؛ فقط حالت فعال رنگ دارد
  · اسم گروه و وضعیت اشتراک اضافه شد (مالک با چند گروه گم نمی‌شود)

دستورهای متنی سریع هم حفظ شده‌اند.
الگوی callback: `mp|<action>|<chat_id>`
"""
from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from bot import group_config as gc
from bot import subscription as sub
from bot import ui
from bot.auth import OWNER_ID
from bot.facmd import fa_command

LOGGER = logging.getLogger("musicbot.adminpanel")

# منوی قفل پلتفرم باز است؟ chat_id → bool
_plat_open: dict = {}

_LOCK_LABEL = {
    gc.LOCK_NONE: "هر دو",
    gc.LOCK_YOUTUBE: "یوتیوب",
    gc.LOCK_SOUNDCLOUD: "ساوندکلاد",
}
_LOCK_ICON = {
    gc.LOCK_NONE: ui.EMO_BOTH,
    gc.LOCK_YOUTUBE: ui.EMO_YOUTUBE,
    gc.LOCK_SOUNDCLOUD: ui.EMO_SOUNDCLOUD,
}
_LOCK_ORDER = (gc.LOCK_SOUNDCLOUD, gc.LOCK_YOUTUBE, gc.LOCK_NONE)


def _is_owner(message: Message) -> bool:
    return bool(message.from_user) and message.from_user.id == OWNER_ID


def panel(chat_id: int, group_name: str = ""):
    """متن + کیبورد پنل مدیریت پلیر. برمی‌گرداند (text, entities, kb)."""
    enabled = gc.is_enabled(chat_id)
    lock = gc.get_lock(chat_id)
    menu_open = _plat_open.get(chat_id, False)

    t = ui.Text().title(ui.EMO_GEAR, ui.BASE_ARROW, "مدیریت پلیر")
    if group_name:
        t.field(0, "گروه", ui.trunc(group_name, 30))
    t.field(1 if group_name else 0, "وضعیت پلیر", "روشن" if enabled else "خاموش")
    t.field(2 if group_name else 1, "پلتفرم مجاز",
            _LOCK_LABEL[lock] + ("" if lock == gc.LOCK_NONE else " (قفل)"))
    t.field(3 if group_name else 2, "اشتراک", ui.fa(sub.status_text(chat_id)))

    def cb(a: str) -> str:
        return f"mp|{a}|{chat_id}"

    rows = [[
        ui.btn("روشن", cb("on"), ui.GREEN if enabled else ui.PLAIN, ui.EMO_PLAY),
        ui.btn("خاموش", cb("off"), ui.RED if not enabled else ui.PLAIN,
               ui.EMO_STOP),
    ]]

    if menu_open:
        rows.append([ui.btn(f"پلتفرم مجاز: {_LOCK_LABEL[lock]} ▾",
                            cb("plat_close"), ui.BLUE, _LOCK_ICON[lock])])
        rows.append([ui.btn(_LOCK_LABEL[lk], cb(f"lock_{lk}"),
                            ui.GREEN if lk == lock else ui.PLAIN, _LOCK_ICON[lk])
                     for lk in _LOCK_ORDER])
    else:
        rows.append([ui.btn(f"پلتفرم مجاز: {_LOCK_LABEL[lock]}",
                            cb("plat_open"), ui.PLAIN, _LOCK_ICON[lock])])

    rows.append([ui.btn("مدیریت اشتراک این گروه", cb("sub"), ui.BLUE,
                        ui.EMO_LIST)])
    rows.append([ui.btn("بستن پنل", cb("close"), ui.RED, ui.EMO_CLOSE)])
    return t.text, t.entities, ui.kb(rows)


# ---------- دستور اصلی: «مدیریت پلیر» ----------
@Client.on_message(fa_command(["مدیریت پلیر", "پنل مدیریت پلیر"]))
async def admin_panel_cmd(client: Client, message: Message):
    if not _is_owner(message):
        return                                  # فقط مالک — بی‌صدا
    if message.chat.type.name == "PRIVATE":
        t = ui.Text().title(ui.EMO_GEAR, ui.BASE_ARROW, "پنل مدیریت پلیر")
        t.why("این پنل تنظیمات یک گروه مشخص را ذخیره می‌کند.")
        t.how("داخل همان گروه بنویس «مدیریت پلیر».")
        await message.reply_text(t.text, entities=t.entities)
        return
    _plat_open.pop(message.chat.id, None)
    text, ents, kb = panel(message.chat.id, message.chat.title or "")
    await message.reply_text(text, entities=ents, reply_markup=kb)


# ---------- دستورهای متنی سریع ----------
async def _quick(message: Message, enabled: bool, lock: str | None,
                 note: str) -> None:
    gc.set_enabled(message.chat.id, enabled)
    if lock is not None:
        gc.set_lock(message.chat.id, lock)
    t = ui.Text().title(ui.EMO_GEAR, ui.BASE_ARROW, note)
    t.field(0, "وضعیت پلیر", "روشن" if enabled else "خاموش")
    t.field(1, "پلتفرم مجاز", _LOCK_LABEL[gc.get_lock(message.chat.id)])
    await message.reply_text(t.text, entities=t.entities)


@Client.on_message(fa_command(["موزیک پلیر روشن"]))
async def mp_on(client: Client, message: Message):
    if not _is_owner(message) or message.chat.type.name == "PRIVATE":
        return
    await _quick(message, True, None, "پلیر روشن شد")


@Client.on_message(fa_command(["موزیک پلیر خاموش"]))
async def mp_off(client: Client, message: Message):
    if not _is_owner(message) or message.chat.type.name == "PRIVATE":
        return
    await _quick(message, False, None, "پلیر خاموش شد")


@Client.on_message(fa_command(["موزیک پلیر یوتیوب روشن", "موزیک پلیر فقط یوتیوب"]))
async def mp_yt(client: Client, message: Message):
    if not _is_owner(message) or message.chat.type.name == "PRIVATE":
        return
    await _quick(message, True, gc.LOCK_YOUTUBE, "پلتفرم قفل شد: یوتیوب")


@Client.on_message(fa_command(["موزیک پلیر ساوندکلاد روشن",
                              "موزیک پلیر فقط ساوندکلاد"]))
async def mp_sc(client: Client, message: Message):
    if not _is_owner(message) or message.chat.type.name == "PRIVATE":
        return
    await _quick(message, True, gc.LOCK_SOUNDCLOUD, "پلتفرم قفل شد: ساوندکلاد")


@Client.on_message(fa_command(["موزیک پلیر هردو", "موزیک پلیر هر دو"]))
async def mp_both(client: Client, message: Message):
    if not _is_owner(message) or message.chat.type.name == "PRIVATE":
        return
    await _quick(message, True, gc.LOCK_NONE, "قفل پلتفرم برداشته شد")


# ---------- callback پنل مدیریت ----------
@Client.on_callback_query(filters.regex(r"^mp\|"))
async def admin_panel_cb(client: Client, cq: CallbackQuery):
    if not cq.from_user or cq.from_user.id != OWNER_ID:
        await cq.answer("فقط مالک ربات به این پنل دسترسی دارد.", show_alert=True)
        return
    parts = str(cq.data or "").split("|")
    action = parts[1] if len(parts) > 1 else ""
    try:
        chat_id = int(parts[2])
    except (IndexError, ValueError):
        await cq.answer("داده نامعتبر", show_alert=True)
        return

    if action == "close":
        _plat_open.pop(chat_id, None)
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("بسته شد")
        return

    toast = ""
    if action == "on":
        gc.set_enabled(chat_id, True)
        toast = "پلیر روشن شد"
    elif action == "off":
        gc.set_enabled(chat_id, False)
        toast = "پلیر خاموش شد"
    elif action == "plat_open":
        _plat_open[chat_id] = True
    elif action == "plat_close":
        _plat_open.pop(chat_id, None)
    elif action.startswith("lock_"):
        lock = action[5:]
        if lock in (gc.LOCK_NONE, gc.LOCK_YOUTUBE, gc.LOCK_SOUNDCLOUD):
            gc.set_lock(chat_id, lock)
            _plat_open.pop(chat_id, None)
            toast = f"پلتفرم: {_LOCK_LABEL[lock]}"
    elif action == "sub":
        # میان‌بر: وضعیت اشتراک همین گروه را در همین پنل نشان بده
        t = ui.Text().title(ui.EMO_LIST, ui.BASE_ARROW, "اشتراک این گروه")
        t.field(0, "وضعیت", ui.fa(sub.status_text(chat_id)))
        t.field(1, "شناسه گروه", code=str(chat_id))
        t.add("\n")
        t.italic("برای تغییر روز/مکث/لغو، در پیوی ربات «مدیریت» را بزن.")
        kb = ui.kb([[ui.btn("بازگشت", f"mp|back|{chat_id}", ui.BLUE,
                            ui.EMO_BACK)]])
        try:
            await cq.message.edit_text(t.text, entities=t.entities,
                                       reply_markup=kb)
        except Exception:  # noqa: BLE001
            pass
        await cq.answer()
        return

    chat_name = cq.message.chat.title if cq.message and cq.message.chat else ""
    text, ents, kb = panel(chat_id, chat_name or "")
    try:
        await cq.message.edit_text(text, entities=ents, reply_markup=kb)
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("admin panel edit: %s", e)
    await cq.answer(toast)
