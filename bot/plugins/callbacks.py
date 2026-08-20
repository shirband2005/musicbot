"""مدیریت دکمه‌های پنل پخش (callback query) و دکمه راهنما."""
import logging

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from bot import call
from bot import player
from bot import queue as q
from bot.plugins.start import HELP_TEXT

LOGGER = logging.getLogger("musicbot.callbacks")


@Client.on_callback_query(filters.regex(r"^help$"))
async def help_cb(client: Client, cq: CallbackQuery):
    await cq.message.edit_text(HELP_TEXT)
    await cq.answer()


async def _apply_volume(chat_id: int):
    """اعمال میزان صدای فعلی روی کال (با در نظر گرفتن حالت بیصدا)."""
    vol = 0 if player.is_muted(chat_id) else player.get_volume(chat_id)
    try:
        await call.change_volume_call(chat_id, vol)
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("volume apply: %s", e)


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

    if track is None:
        await cq.answer("چیزی در حال پخش نیست.", show_alert=True)
        return

    # --- پخش/توقف موقت (یک دکمه) ---
    if action == "playpause":
        if track.paused:
            await call.resume(chat_id)
            track.mark_resumed()
            await cq.answer("▶️ ادامه یافت")
        else:
            await call.pause(chat_id)
            track.mark_paused()
            await cq.answer("⏸ متوقف شد")
        await player.refresh_panel(chat_id)

    elif action == "stop":
        await player.stop(chat_id)
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("⏹ متوقف شد")

    # --- صدا ---
    elif action in ("vol_up", "vol_down"):
        vol = player.get_volume(chat_id) + (10 if action == "vol_up" else -10)
        player.set_volume(chat_id, vol)
        if player.get_volume(chat_id) > 0:
            player.set_muted(chat_id, False)
        await _apply_volume(chat_id)
        await player.refresh_panel(chat_id)
        await cq.answer(f"🔊 صدا: {player.get_volume(chat_id)}%")

    elif action == "mute":
        new_state = not player.is_muted(chat_id)
        player.set_muted(chat_id, new_state)
        await _apply_volume(chat_id)
        await player.refresh_panel(chat_id)
        await cq.answer("🔇 بیصدا شد" if new_state else "🔈 صدادار شد")

    # --- ناوبری آهنگ ---
    elif action == "skip":
        nxt = await player.skip(chat_id)
        await cq.answer("⏭ آهنگ بعدی" if nxt else "⏹ صف خالی شد")

    elif action == "prev":
        prev = await player.previous(chat_id)
        await cq.answer("⏮ آهنگ قبلی" if prev else "قبلی‌ای وجود ندارد")

    elif action == "playlist":
        items = list(q.get_queue(chat_id))
        cur = q.now_playing(chat_id)
        lines = [f"🎧 در حال پخش: {cur.title}"] if cur else []
        if items:
            lines.append("")
            lines += [f"{i}. {t.title}" for i, t in enumerate(items[:15], 1)]
        else:
            lines.append("\nصف بعدی خالی است.")
        await cq.answer("\n".join(lines)[:200], show_alert=True)

    # --- دریافت رسانه: لینک منبع را می‌فرستد ---
    elif action == "getmedia":
        await cq.answer("لینک منبع ارسال شد", show_alert=False)
        try:
            await client.send_message(
                chat_id,
                f"📥 **{track.title}**\n{track.webpage_url}",
                disable_web_page_preview=False,
            )
        except Exception as e:  # noqa: BLE001
            LOGGER.debug("getmedia: %s", e)

    elif action == "refresh":
        await player.refresh_panel(chat_id)
        await cq.answer("🔄 بروزرسانی شد")

    else:
        await cq.answer()
