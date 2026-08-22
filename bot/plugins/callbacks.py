"""روتر دکمه‌های پنل‌ها: پنل موزیک (`p|*`)، لیست پخش (`q|*`)،
پنل فیلم (`v|*`) و ناوبری راهنما (`h|*`).

الگوی callback جدید:
    p|refresh                 تازه‌سازی دستی نوار زمان
    p|playpause | p|stop
    p|prev | p|skip
    p|vol_up | p|vol_down | p|mute
    p|playlist                صفحه‌ی لیست پخش (نمای دیگر همان پیام)
    p|mode_open | p|mode_close | p|mode_set|<queue|repeat|random>
    p|sleep_open | p|sleep_set|<minutes> | p|sleep_off
    p|plat_open | p|plat_close | p|plat_set|<both|youtube|soundcloud>
    p|plat_locked             پلتفرم قفل مالک — فقط هشدار
    p|getmedia | p|close | p|noop

کالبک‌های نسخه‌ی قبلی (`p|mode_repeat|<chat>`, `p|platform|<chat>`, …) هم
پذیرفته می‌شوند: پنل‌هایی که از قبل در گروه‌ها مانده‌اند نباید بشکنند.
"""
import logging
import os

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from bot import auth
from bot import call
from bot import database as db
from bot import group_config as gc
from bot import panel as panel_mod
from bot import platform_pref
from bot import player
from bot import queue as q
from bot import ui
from bot import youtube
from bot.plugins.start import HELP_NODES, help_markup, help_text

LOGGER = logging.getLogger("musicbot.callbacks")

# نگاشت کالبک‌های نسخه‌ی قدیم → کنش جدید (سازگاری با پنل‌های مانده در گروه‌ها)
_LEGACY = {
    "mode_repeat": ("mode_set", gc.MODE_REPEAT),
    "mode_queue": ("mode_set", gc.MODE_QUEUE),
    "mode_random": ("mode_set", gc.MODE_RANDOM),
    "platform": ("plat_cycle", None),
}

_MODE_TOAST = {
    gc.MODE_QUEUE: "حالت: پخش صف",
    gc.MODE_REPEAT: "حالت: پخش تکرار",
    gc.MODE_RANDOM: "حالت: پخش رندوم",
}


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


def _parse(data: str):
    """`p|action` یا `p|action|arg` → (action, arg).

    نسخه‌ی قدیم chat_id را در کالبک می‌گذاشت؛ حالا از `cq.message.chat.id`
    خوانده می‌شود (کوتاه‌تر و مقاوم‌تر). آرگومان عددیِ قدیمی به‌عنوان arg
    می‌آید و در کنش‌های legacy نادیده گرفته می‌شود.
    """
    parts = data.split("|")
    action = parts[1] if len(parts) > 1 else ""
    arg = parts[2] if len(parts) > 2 else None
    if action in _LEGACY:
        new_action, forced = _LEGACY[action]
        return new_action, (forced if forced is not None else arg)
    return action, arg


@Client.on_callback_query(filters.regex(r"^p\|"))
async def panel_cb(client: Client, cq: CallbackQuery):
    if not await auth.guard_callback(client, cq):
        return
    if not cq.message or not cq.message.chat:
        await cq.answer()
        return

    chat_id = int(cq.message.chat.id or 0)
    action, arg = _parse(str(cq.data or ""))
    if not chat_id:
        await cq.answer()
        return

    if action == "noop":
        await cq.answer()
        return

    if action == "close":
        panel_mod.reset_menus(chat_id)
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("پنل بسته شد")
        return

    track = q.now_playing(chat_id)
    if track is None:
        await cq.answer("چیزی در حال پخش نیست.", show_alert=True)
        return

    # ================= منوی حالت پخش (آکاردئونی) =================
    if action == "mode_open":
        panel_mod.set_menu(chat_id, panel_mod.MENU_MODE)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer()
        return

    if action == "mode_close":
        panel_mod.set_menu(chat_id, None)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer()
        return

    if action == "mode_set":
        mode = arg if arg in (gc.MODE_QUEUE, gc.MODE_REPEAT, gc.MODE_RANDOM) else None
        if mode is None:
            await cq.answer("حالت نامعتبر", show_alert=True)
            return
        gc.set_mode(chat_id, mode)
        panel_mod.set_menu(chat_id, None)       # انتخاب شد → منو بسته می‌شود
        await player.refresh_panel(chat_id, force=True)
        await cq.answer(_MODE_TOAST[mode])
        return

    # ================= تایمر خواب =================
    if action == "sleep_open":
        panel_mod.set_menu(chat_id, panel_mod.MENU_SLEEP)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer()
        return

    if action == "sleep_set":
        try:
            minutes = int(arg or 0)
        except ValueError:
            minutes = 0
        if minutes <= 0:
            await cq.answer("زمان نامعتبر", show_alert=True)
            return
        player.sleep_start(chat_id, minutes)
        panel_mod.set_menu(chat_id, None)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer(f"تایمر خواب روی {ui.fa(minutes)} دقیقه تنظیم شد")
        return

    if action == "sleep_off":
        player.sleep_cancel(chat_id)
        panel_mod.set_menu(chat_id, None)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer("تایمر خواب خاموش شد")
        return

    # ================= پلتفرم =================
    if action == "plat_locked":
        await cq.answer("پلتفرم این گروه توسط مالک قفل شده است.", show_alert=True)
        return

    if action == "plat_open":
        if gc.is_locked(chat_id):
            await cq.answer("پلتفرم این گروه توسط مالک قفل شده است.", show_alert=True)
            return
        panel_mod.set_menu(chat_id, panel_mod.MENU_PLAT)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer()
        return

    if action == "plat_close":
        panel_mod.set_menu(chat_id, None)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer()
        return

    if action == "plat_set":
        if gc.is_locked(chat_id):
            await cq.answer("پلتفرم این گروه توسط مالک قفل شده است.", show_alert=True)
            return
        valid = (platform_pref.BOTH, platform_pref.YOUTUBE, platform_pref.SOUNDCLOUD)
        if arg not in valid:
            await cq.answer("پلتفرم نامعتبر", show_alert=True)
            return
        db.group_set(chat_id, platform=arg)
        panel_mod.set_menu(chat_id, None)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer(f"پلتفرم: {panel_mod.platform_label(chat_id)}")
        return

    if action == "plat_cycle":            # فقط از کالبک قدیمی می‌آید
        if gc.is_locked(chat_id):
            await cq.answer("پلتفرم این گروه توسط مالک قفل شده است.", show_alert=True)
            return
        platform_pref.cycle(chat_id)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer(f"پلتفرم: {panel_mod.platform_label(chat_id)}")
        return

    # ================= پخش/مکث =================
    if action == "playpause":
        if track.paused:
            await call.resume(chat_id)
            track.mark_resumed()
            await cq.answer("ادامه یافت")
        else:
            await call.pause(chat_id)
            track.mark_paused()
            await cq.answer("متوقف شد")
        await player.refresh_panel(chat_id, force=True)
        return

    if action == "stop":
        await player.stop(chat_id)
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("پخش متوقف شد")
        return

    # ================= صدا =================
    if action in ("vol_up", "vol_down"):
        vol = player.get_volume(chat_id) + (10 if action == "vol_up" else -10)
        player.set_volume(chat_id, vol)
        if player.get_volume(chat_id) > 0:
            player.set_muted(chat_id, False)
        await _apply_volume(chat_id)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer(f"صدا: {ui.fa(player.get_volume(chat_id))}%")
        return

    if action == "mute":
        new_state = not player.is_muted(chat_id)
        player.set_muted(chat_id, new_state)
        await _apply_volume(chat_id)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer("بیصدا شد" if new_state else "صدادار شد")
        return

    # ================= ناوبری آهنگ (با توجه به حالت پخش) =================
    if action == "skip":
        m = gc.get_mode(chat_id)
        if m == gc.MODE_REPEAT:
            await player.repeat_current(chat_id)
            await cq.answer("تکرار همان آهنگ")
        elif m == gc.MODE_RANDOM:
            await player.play_random(chat_id)
            await cq.answer("آهنگ رندوم بعدی")
        else:
            nxt = await player.skip(chat_id)
            await cq.answer("آهنگ بعدی" if nxt else "صف خالی شد")
        return

    if action == "prev":
        m = gc.get_mode(chat_id)
        if m == gc.MODE_REPEAT:
            await player.repeat_current(chat_id)
            await cq.answer("تکرار همان آهنگ")
        else:
            # در حالت رندوم و صف، «قبلی» همان آهنگ قبلیِ تاریخچه را پخش می‌کند
            prev = await player.previous(chat_id)
            await cq.answer("آهنگ قبلی" if prev else "قبلی‌ای وجود ندارد")
        return

    # ================= لیست پخش (صفحه‌ی جدا در همان پیام) =================
    if action == "playlist":
        panel_mod.set_menu(chat_id, None)     # منوی باز نباید زیر لیست بماند
        panel_mod.set_view(chat_id, panel_mod.VIEW_PLAYLIST, 1)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer()
        return

    # ================= دریافت رسانه =================
    if action == "getmedia":
        await cq.answer("در حال دانلود فایل…")
        await _send_media(client, chat_id, track)
        return

    if action == "refresh":
        await player.refresh_panel(chat_id, force=True)
        await cq.answer("بروزرسانی شد")
        return

    await cq.answer()


async def _send_media(client: Client, chat_id: int, track) -> None:
    """فایل آهنگ در حال پخش را در گروه می‌فرستد."""
    status = None
    try:
        t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "در حال دانلود")
        t.line(0, ui.trunc(track.title, 46))
        status = await client.send_message(chat_id, t.text, entities=t.entities)

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
            caption=info.get("title", track.title),
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
        # متن خام خطا فقط به لاگ می‌رود؛ کاربر پیام فارسی با راه‌حل می‌بیند.
        LOGGER.warning("getmedia download: %s", e)
        t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "دانلود ناموفق بود")
        t.why("منبع پاسخ نداد یا فایل قابل دریافت نبود.")
        t.how("چند لحظه بعد دوباره امتحان کن.")
        try:
            if status:
                await status.edit_text(t.text, entities=t.entities)
            else:
                await client.send_message(chat_id, t.text, entities=t.entities)
        except Exception:  # noqa: BLE001
            pass


# ==================================================================
#                    صفحه‌ی لیست پخش: `q|*`
# ==================================================================
@Client.on_callback_query(filters.regex(r"^q\|"))
async def playlist_cb(client: Client, cq: CallbackQuery):
    if not await auth.guard_callback(client, cq):
        return
    if not cq.message or not cq.message.chat:
        await cq.answer()
        return

    chat_id = int(cq.message.chat.id or 0)
    parts = str(cq.data or "").split("|")
    action = parts[1] if len(parts) > 1 else ""
    arg = parts[2] if len(parts) > 2 else None
    if not chat_id:
        await cq.answer()
        return

    if action == "noop":                       # شمارنده‌ی صفحه (برچسب، نه دکمه)
        await cq.answer()
        return

    if q.now_playing(chat_id) is None:
        await cq.answer("چیزی در حال پخش نیست.", show_alert=True)
        return

    # --- بازگشت به پنل پخش ---
    if action == "back":
        panel_mod.set_view(chat_id, panel_mod.VIEW_PANEL)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer()
        return

    # --- تغییر صفحه ---
    if action == "page":
        try:
            page = int(arg or 1)
        except ValueError:
            page = 1
        panel_mod.set_view(chat_id, panel_mod.VIEW_PLAYLIST, page)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer()
        return

    # --- پخش فوری یک آهنگ از صف ---
    if action == "jump":
        track = q.find(chat_id, arg or "")
        if track is None:
            # آهنگ در این فاصله پخش یا حذف شده — لیست را تازه کن
            await player.refresh_panel(chat_id, force=True)
            await cq.answer("این آهنگ دیگر در صف نیست.", show_alert=True)
            return
        q.move_to_front(chat_id, track.uid)
        nxt = await player.skip(chat_id)
        panel_mod.set_view(chat_id, panel_mod.VIEW_PANEL)
        await cq.answer(f"پخش: {ui.trunc(track.title, 28)}"
                        if nxt else "پخش نشد")
        return

    # --- حذف از صف ---
    if action == "del":
        track = q.remove(chat_id, arg or "")
        if track is None:
            await player.refresh_panel(chat_id, force=True)
            await cq.answer("این آهنگ دیگر در صف نیست.", show_alert=True)
            return
        # اگر آخرین آهنگِ صفحه‌ی جاری حذف شد، refresh خودش صفحه را عقب می‌برد
        await player.refresh_panel(chat_id, force=True)
        await cq.answer(f"حذف شد: {ui.trunc(track.title, 26)}")
        return

    await cq.answer()


# ==================================================================
#                    پنل فیلم: `v|*`
# ==================================================================
# فیلم صف ندارد، پس «قبلی/بعدی/لیست/حالت/پلتفرم» وجود ندارند.
# کنش‌های مشترک (مکث، توقف، صدا، تایمر، دریافت) همان منطق پنل موزیک را
# استفاده می‌کنند تا رفتار دو پنل از هم واگرا نشود.
@Client.on_callback_query(filters.regex(r"^v\|"))
async def video_panel_cb(client: Client, cq: CallbackQuery):
    if not await auth.guard_callback(client, cq):
        return
    if not cq.message or not cq.message.chat:
        await cq.answer()
        return

    chat_id = int(cq.message.chat.id or 0)
    parts = str(cq.data or "").split("|")
    action = parts[1] if len(parts) > 1 else ""
    arg = parts[2] if len(parts) > 2 else None
    if not chat_id:
        await cq.answer()
        return

    if action == "close":
        panel_mod.reset_menus(chat_id)
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("پنل بسته شد")
        return

    track = q.now_playing(chat_id)
    if track is None:
        await cq.answer("چیزی در حال پخش نیست.", show_alert=True)
        return

    if action == "playpause":
        if track.paused:
            await call.resume(chat_id)
            track.mark_resumed()
            await cq.answer("ادامه یافت")
        else:
            await call.pause(chat_id)
            track.mark_paused()
            await cq.answer("متوقف شد")
        await player.refresh_panel(chat_id, force=True)
        return

    if action == "stop":
        await player.stop(chat_id)
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        await cq.answer("پخش متوقف شد")
        return

    if action in ("vol_up", "vol_down"):
        vol = player.get_volume(chat_id) + (10 if action == "vol_up" else -10)
        player.set_volume(chat_id, vol)
        if player.get_volume(chat_id) > 0:
            player.set_muted(chat_id, False)
        await _apply_volume(chat_id)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer(f"صدا: {ui.fa(player.get_volume(chat_id))}%")
        return

    if action == "mute":
        new_state = not player.is_muted(chat_id)
        player.set_muted(chat_id, new_state)
        await _apply_volume(chat_id)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer("بیصدا شد" if new_state else "صدادار شد")
        return

    # --- تایمر خواب (همان منطق پنل موزیک) ---
    if action == "sleep_open":
        panel_mod.set_menu(chat_id, panel_mod.MENU_SLEEP)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer()
        return

    if action == "sleep_set":
        try:
            minutes = int(arg or 0)
        except ValueError:
            minutes = 0
        if minutes <= 0:
            await cq.answer("زمان نامعتبر", show_alert=True)
            return
        player.sleep_start(chat_id, minutes)
        panel_mod.set_menu(chat_id, None)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer(f"تایمر خواب روی {ui.fa(minutes)} دقیقه تنظیم شد")
        return

    if action == "sleep_off":
        player.sleep_cancel(chat_id)
        panel_mod.set_menu(chat_id, None)
        await player.refresh_panel(chat_id, force=True)
        await cq.answer("تایمر خواب خاموش شد")
        return

    if action == "getmedia":
        await cq.answer("در حال آماده‌سازی فیلم…")
        await _send_video_file(client, chat_id, track)
        return

    if action == "refresh":
        await player.refresh_panel(chat_id, force=True)
        await cq.answer("بروزرسانی شد")
        return

    await cq.answer()


async def _send_video_file(client: Client, chat_id: int, track) -> None:
    """فایل فیلم در حال پخش را در گروه می‌فرستد."""
    status = None
    try:
        t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "در حال آماده‌سازی فیلم")
        t.line(0, ui.trunc(track.title, 46))
        status = await client.send_message(chat_id, t.text, entities=t.entities)

        if track.local_path and os.path.isfile(track.local_path):
            path = track.local_path
            info = {"path": path, "title": track.title, "duration": track.duration}
            tmp = False
        else:
            query = track.query or track.webpage_url or track.title
            info = await youtube.download_media(query, video=True,
                                                out_dir=player.DOWNLOAD_DIR)
            path = info["path"]
            tmp = True
        if not path or not os.path.isfile(path):
            raise FileNotFoundError("فایل دانلود پیدا نشد")

        await client.send_video(
            chat_id,
            video=path,
            caption=info.get("title", track.title),
            duration=int(info.get("duration") or 0),
            supports_streaming=True,
        )
        if status:
            await status.delete()
        if tmp and path not in db.cache_paths():
            try:
                os.remove(path)
            except OSError:
                pass
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("getmedia video: %s", e)
        t = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "دریافت فیلم ناموفق بود")
        t.why("فایل بیش از حد بزرگ است یا منبع پاسخ نداد.")
        t.how("چند لحظه بعد دوباره امتحان کن.")
        try:
            if status:
                await status.edit_text(t.text, entities=t.entities)
            else:
                await client.send_message(chat_id, t.text, entities=t.entities)
        except Exception:  # noqa: BLE001
            pass
