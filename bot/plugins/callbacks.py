"""مدیریت دکمه‌های پنل پخش (callback query) و دکمه راهنما."""
import logging

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from bot import call
from bot import player
from bot import queue as q
from bot.plugins.start import HELP_TEXT

LOGGER = logging.getLogger("musicbot.callbacks")

# مقدار پرش زمانی (ثانیه) هنوز به‌صورت seek واقعی پیاده نشده؛
# py-tgcalls برای seek نیاز به بازپخش استریم از offset دارد.


@Client.on_callback_query(filters.regex(r"^help$"))
async def help_cb(client: Client, cq: CallbackQuery):
    await cq.message.edit_text(HELP_TEXT)
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^p\|"))
async def panel_cb(client: Client, cq: CallbackQuery):
    try:
        _, action, chat_id_s = cq.data.split("|", 2)
        chat_id = int(chat_id_s)
    except (ValueError, IndexError):
        await cq.answer("داده نامعتبر", show_alert=True)
        return

    track = q.now_playing(chat_id)

    if action == "noop":
        await cq.answer()
        return

    if action == "close":
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("پنل بسته شد")
        return

    if track is None and action not in ("close",):
        await cq.answer("چیزی در حال پخش نیست.", show_alert=True)
        return

    if action == "pause":
        await call.pause(chat_id)
        track.mark_paused()
        await player.refresh_panel(chat_id)
        await cq.answer("⏸ متوقف شد")

    elif action == "resume":
        await call.resume(chat_id)
        track.mark_resumed()
        await player.refresh_panel(chat_id)
        await cq.answer("▶️ ادامه یافت")

    elif action == "skip":
        nxt = await player.skip(chat_id)
        await cq.answer("⏭ رد شد" if nxt else "⏹ صف خالی شد")

    elif action == "stop":
        await player.stop(chat_id)
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("⏹ متوقف شد")

    elif action in ("vol_up", "vol_down"):
        vol = player.get_volume(chat_id)
        vol += 10 if action == "vol_up" else -10
        player.set_volume(chat_id, vol)
        try:
            await call.change_volume_call(chat_id, player.get_volume(chat_id))
        except Exception as e:  # noqa: BLE001
            LOGGER.debug("volume: %s", e)
        await player.refresh_panel(chat_id)
        await cq.answer(f"🔊 صدا: {player.get_volume(chat_id)}%")

    elif action == "mute":
        try:
            await call.change_volume_call(chat_id, 0)
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("🔇 بیصدا شد")

    elif action == "unmute":
        try:
            await call.change_volume_call(chat_id, player.get_volume(chat_id))
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("🔈 صدادار شد")

    elif action == "refresh":
        await player.refresh_panel(chat_id)
        await cq.answer("🔄 بروزرسانی شد")

    elif action in ("fwd30", "fwd60", "back30", "back60"):
        # پرش زمانی: نیاز به بازپخش استریم از offset دارد (فعلاً اطلاع‌رسانی)
        await cq.answer("⏩ پرش زمانی در نسخه بعدی فعال می‌شود", show_alert=False)

    else:
        await cq.answer()
