"""مدیریت دکمه‌های پنل پخش (callback query) و دکمه راهنما."""
import logging
import os

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from bot import auth
from bot import call
from bot import database as db
from bot import player
from bot import platform_pref
from bot import queue as q
from bot import youtube
from bot.plugins.start import HELP_NODES, help_markup, help_text

LOGGER = logging.getLogger("musicbot.callbacks")


# --- ناوبری پنل راهنما: 'h|<node>' ---
@Client.on_callback_query(filters.regex(r"^h\|"))
async def help_nav_cb(client: Client, cq: CallbackQuery):
    if not await auth.guard_callback(client, cq):
        return
    node = cq.data.split("|", 1)[1]
    if node == "close":
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("بسته شد")
        return
    if node not in HELP_NODES:
        await cq.answer()
        return
    try:
        await cq.message.edit_text(help_text(node), reply_markup=help_markup(node))
    except Exception:  # noqa: BLE001
        pass
    await cq.answer()


async def _apply_volume(chat_id: int):
    """اعمال میزان صدای فعلی روی کال (با در نظر گرفتن حالت بیصدا)."""
    if player.is_muted(chat_id):
        try:
            await call.mute(chat_id)
        except Exception as e:  # noqa: BLE001
            LOGGER.warning("mute: %s", e)
        return
    # بازکردن صدا سپس تنظیم میزان (حداقل ۱ چون ۰ توسط برخی نسخه‌ها رد می‌شود)
    try:
        await call.unmute(chat_id)
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("unmute: %s", e)
    vol = max(1, min(200, player.get_volume(chat_id)))
    try:
        await call.change_volume_call(chat_id, vol)
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("change_volume(%s): %s", vol, e)


@Client.on_callback_query(filters.regex(r"^p\|"))
async def panel_cb(client: Client, cq: CallbackQuery):
    if not await auth.guard_callback(client, cq):
        return
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

    # --- حالت پخش (تکرار/صف/رندوم) — انحصاری متقابل ---
    if action in ("mode_repeat", "mode_queue", "mode_random"):
        from bot import group_config as gc
        m = {"mode_repeat": gc.MODE_REPEAT, "mode_queue": gc.MODE_QUEUE,
             "mode_random": gc.MODE_RANDOM}[action]
        gc.set_mode(chat_id, m)
        await player.refresh_panel(chat_id)
        label = {"repeat": "🔂 پخش تکرار", "queue": "📋 پخش صف",
                 "random": "🔀 پخش رندوم"}[m]
        await cq.answer(f"{label} روشن شد")
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

    # --- تغییر پلتفرم جست‌وجو (چرخش بین سه حالت) ---
    elif action == "platform":
        platform_pref.cycle(chat_id)
        await player.refresh_panel(chat_id)
        await cq.answer(f"🎛 {platform_pref.label(chat_id)}")

    # --- دریافت رسانه: دانلود فایل mp3 و ارسال آن ---
    elif action == "getmedia":
        await cq.answer("📥 در حال دانلود فایل...", show_alert=False)
        status = None
        try:
            status = await client.send_message(chat_id, f"📥 در حال دانلود:\n**{track.title}**")
            # اگر همین آهنگ فایل محلی دارد (پخش فعلی)، دوباره دانلود نکن
            if track.local_path and os.path.isfile(track.local_path):
                path = track.local_path
                info = {"path": path, "title": track.title,
                        "uploader": "", "duration": track.duration}
                tmp = False
            else:
                query = track.query or track.webpage_url or track.title
                info = await youtube.download_audio(query, out_dir=player.DOWNLOAD_DIR)
                path = info["path"]
                tmp = True
            if not path or not os.path.isfile(path):
                raise FileNotFoundError("فایل دانلود پیدا نشد")
            await client.send_audio(
                chat_id,
                audio=path,
                title=info.get("title", track.title),
                performer=info.get("uploader", ""),
                duration=int(info.get("duration") or 0),
                caption=f"🎵 {info.get('title', track.title)}",
            )
            if status:
                await status.delete()
            # فقط فایلِ موقتِ همین کار را پاک کن (نه فایل پخش فعلی/کش)
            if tmp and path not in db.cache_paths():
                try:
                    os.remove(path)
                except OSError:
                    pass
        except Exception as e:  # noqa: BLE001
            LOGGER.warning("getmedia download: %s", e)
            msg = f"❌ خطا در دانلود فایل:\n`{e}`"
            if status:
                try:
                    await status.edit_text(msg)
                except Exception:  # noqa: BLE001
                    pass
            else:
                await client.send_message(chat_id, msg)

    elif action == "refresh":
        await player.refresh_panel(chat_id)
        await cq.answer("🔄 بروزرسانی شد")

    else:
        await cq.answer()
