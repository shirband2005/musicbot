"""منطق اصلی پخش: پیوستن به کال، مدیریت پنل و بروزرسانی خودکار نوار پیشرفت."""
import asyncio
import logging
import os
from typing import Dict, Optional

from pyrogram.errors import MessageNotModified
from pyrogram.types import InputMediaAnimation, InputMediaPhoto
from pytgcalls.types import AudioQuality, MediaStream, VideoQuality

from bot import app, call
from bot import database as db
from bot import logs
from bot import queue as q
from bot import youtube
from bot.panel import (
    cover_file,
    cover_is_animation,
    cover_static_file,
    has_cover,
    panel_keyboard,
    panel_text,
)
from bot.queue import Track

LOGGER = logging.getLogger("musicbot.player")

# فاصله‌ی بروزرسانی خودکار نوار پیشرفت (ثانیه) — طبق درخواست کاربر ۶ ثانیه
PROGRESS_INTERVAL = 6

# پوشه‌ی فایل‌های دانلودشده (روی Volume تا با ری‌استارت پاک نشود)
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/data/downloads").strip() or "/data/downloads"

_panel_msg: Dict[int, int] = {}
_panel_media: Dict[int, str] = {}  # نوع رسانه فعلی پنل: anim/static/photo/text
_updater: Dict[int, asyncio.Task] = {}
_volume: Dict[int, int] = {}
_muted: Dict[int, bool] = {}


def get_volume(chat_id: int) -> int:
    return _volume.get(chat_id, 100)


def set_volume(chat_id: int, vol: int) -> None:
    _volume[chat_id] = max(0, min(200, vol))


def is_muted(chat_id: int) -> bool:
    return _muted.get(chat_id, False)


def set_muted(chat_id: int, val: bool) -> None:
    _muted[chat_id] = val


def _stream(track: Track) -> MediaStream:
    # همیشه از فایل محلی پخش کن (لینک استریم یوتیوب به IP پروکسی قفل است
    # و ffmpeg از IP سرور نمی‌تواند آن را بگیرد → سکوت در کال).
    src = track.local_path or track.stream_url
    if track.is_video:
        return MediaStream(
            src,
            audio_parameters=AudioQuality.HIGH,
            video_parameters=VideoQuality.HD_720p,
        )
    return MediaStream(
        src,
        audio_parameters=AudioQuality.HIGH,
        video_flags=MediaStream.Flags.IGNORE,  # فقط صدا
    )


async def _ensure_local_file(track: Track) -> bool:
    """اگر فایل محلی نداریم، اول کش دیتابیس را چک کن، بعد دانلود کن.

    - اگر همین آهنگ قبلاً دانلود شده و فایلش هست → بدون دانلود دوباره پخش.
    - پس از دانلود جدید، در کش ثبت و فقط ۱۰ فایل اخیر نگه داشته می‌شود.
    """
    if track.local_path and os.path.isfile(track.local_path):
        return True

    # ۱) بررسی کش با video_id (اگر می‌دانیم کدام ویدیوست)
    vid = getattr(track, "video_id", "") or ""
    if vid:
        cached = db.cache_get(vid)
        if cached and os.path.isfile(cached["path"]):
            track.local_path = cached["path"]
            logs.info("CACHE HIT | %s (بدون دانلود دوباره)", track.title)
            return True

    # ۲) دانلود جدید (از طریق پروکسی)
    query = track.query or track.webpage_url or track.title
    try:
        with logs.stage("DOWNLOAD", title=track.title, video=track.is_video):
            info = await youtube.download_media(query, video=track.is_video, out_dir=DOWNLOAD_DIR)
        path = info.get("path", "")
        if path and os.path.isfile(path):
            track.local_path = path
            vid = info.get("id") or vid
            if vid:
                track.video_id = vid
                db.cache_put(vid, path, info.get("title", track.title),
                             int(info.get("duration") or 0), track.is_video)
                _prune_cache()
            return True
        logs.warn("DOWNLOAD: فایل ساخته نشد | %s", track.title)
        return False
    except Exception as e:  # noqa: BLE001
        logs.warn("DOWNLOAD error | %s: %s", track.title, e)
        return False


def _prune_cache() -> None:
    """فقط ۱۰ فایل اخیر را نگه دار؛ بقیه را از دیسک پاک کن."""
    keep = int(os.environ.get("CACHE_KEEP", "10"))
    try:
        for path in db.cache_prune(keep=keep):
            try:
                if path and os.path.isfile(path):
                    os.remove(path)
                    logs.info("CACHE PRUNE | حذف %s", os.path.basename(path))
            except OSError:
                pass
    except Exception as e:  # noqa: BLE001
        logs.debug("prune cache: %s", e) if hasattr(logs, "debug") else None


async def start_playback(chat_id: int, track: Track) -> None:
    await _ensure_local_file(track)
    q.set_now_playing(chat_id, track)
    await call.play(chat_id, _stream(track))
    await _send_panel(chat_id, new=True)


async def play_or_queue(chat_id: int, track: Track) -> int:
    if q.now_playing(chat_id) is None:
        await start_playback(chat_id, track)
        return 0
    return q.add(chat_id, track)


async def skip(chat_id: int) -> Optional[Track]:
    nxt = q.pop_next(chat_id)
    if nxt is None:
        await stop(chat_id)
        return None
    await _ensure_local_file(nxt)
    await call.play(chat_id, _stream(nxt))
    await _send_panel(chat_id, new=True)
    return nxt


async def previous(chat_id: int) -> Optional[Track]:
    prev = q.pop_previous(chat_id)
    if prev is None:
        return None
    await _ensure_local_file(prev)
    await call.play(chat_id, _stream(prev))
    await _send_panel(chat_id, new=True)
    return prev


async def stop(chat_id: int) -> None:
    q.clear(chat_id)
    _cancel_updater(chat_id)
    _muted.pop(chat_id, None)
    try:
        await call.leave_call(chat_id)
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("leave_call: %s", e)


# --- مدیریت پنل و بروزرسانی خودکار ---
async def _send_panel(chat_id: int, new: bool = False) -> None:
    track = q.now_playing(chat_id)
    if track is None:
        return

    # همیشه پنل قبلی این گروه را (هرجا بود) حذف کن تا چت شلوغ نشود.
    await _delete_panel(chat_id)

    vol, muted = get_volume(chat_id), is_muted(chat_id)
    text = panel_text(track, vol, muted)
    kb = panel_keyboard(chat_id, track, vol, muted)
    cover = cover_file()
    static = cover_static_file()
    try:
        if track.paused and static:
            # اگر در حالت مکث پنل می‌سازیم، کاور ثابت را نشان بده
            msg = await app.send_photo(chat_id, static, caption=text, reply_markup=kb)
            _panel_media[chat_id] = "static"
        elif cover and cover_is_animation():
            # گیف/ویدیو → send_animation
            msg = await app.send_animation(chat_id, cover, caption=text, reply_markup=kb)
            _panel_media[chat_id] = "anim"
        elif cover:
            msg = await app.send_photo(chat_id, cover, caption=text, reply_markup=kb)
            _panel_media[chat_id] = "photo"
        else:
            msg = await app.send_message(chat_id, text, reply_markup=kb)
            _panel_media[chat_id] = "text"
        _panel_msg[chat_id] = msg.id
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("ارسال پنل ناموفق، بازگشت به متن: %s", e)
        try:
            msg = await app.send_message(chat_id, text, reply_markup=kb)
            _panel_msg[chat_id] = msg.id
            _panel_media[chat_id] = "text"
        except Exception as e2:  # noqa: BLE001
            LOGGER.error("ارسال پنل کاملاً ناموفق: %s", e2)
            return

    _start_updater(chat_id)


async def _delete_panel(chat_id: int) -> None:
    mid = _panel_msg.pop(chat_id, None)
    _panel_media.pop(chat_id, None)
    if mid:
        try:
            await app.delete_messages(chat_id, mid)
        except Exception:  # noqa: BLE001
            pass


async def refresh_panel(chat_id: int) -> None:
    track = q.now_playing(chat_id)
    mid = _panel_msg.get(chat_id)
    if track is None or mid is None:
        return
    vol, muted = get_volume(chat_id), is_muted(chat_id)
    text = panel_text(track, vol, muted)
    kb = panel_keyboard(chat_id, track, vol, muted)

    # آیا باید نوع کاور عوض شود؟ (پخش=متحرک، مکث=ثابت)
    anim = cover_file()
    static = cover_static_file()
    want_static = track.paused and bool(static)
    desired = "static" if want_static else ("anim" if (anim and cover_is_animation()) else "photo" if anim else "text")
    current = _panel_media.get(chat_id)

    try:
        if desired in ("static", "anim") and desired != current:
            # تعویض خودِ رسانه (فیلم اکولایزر ↔ عکس ثابت)
            if desired == "static":
                media = InputMediaPhoto(static, caption=text)
            else:
                media = InputMediaAnimation(anim, caption=text)
            await app.edit_message_media(chat_id, mid, media=media, reply_markup=kb)
            _panel_media[chat_id] = desired
        elif desired in ("anim", "static", "photo"):
            # فقط متن/کیبورد بروزرسانی شود (رسانه ثابت)
            await app.edit_message_caption(chat_id, mid, caption=text, reply_markup=kb)
        else:
            await app.edit_message_text(chat_id, mid, text, reply_markup=kb)
    except MessageNotModified:
        pass
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("refresh_panel: %s", e)


def _start_updater(chat_id: int) -> None:
    _cancel_updater(chat_id)
    _updater[chat_id] = asyncio.create_task(_progress_loop(chat_id))


def _cancel_updater(chat_id: int) -> None:
    task = _updater.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


async def _progress_loop(chat_id: int) -> None:
    """هر PROGRESS_INTERVAL ثانیه نوار پیشرفت را بروز می‌کند تا پایان آهنگ."""
    try:
        while True:
            await asyncio.sleep(PROGRESS_INTERVAL)
            track = q.now_playing(chat_id)
            if track is None:
                break
            if track.paused:
                continue
            await refresh_panel(chat_id)
            if track.duration and track.position() >= track.duration:
                break
    except asyncio.CancelledError:
        pass
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("progress_loop: %s", e)


def panel_message_id(chat_id: int) -> Optional[int]:
    return _panel_msg.get(chat_id)
