"""کانال‌ها: لاگ رویدادها + کانال دیتابیس (آرشیو آهنگ) + بکاپ دیتابیس.

- LOG_CHANNEL: پیام‌های لاگ (روشن/خاموش، گروه جدید، رویدادهای اشتراک).
- ARCHIVE_CHANNEL: «کانال دیتابیس» — هر آهنگ یک‌بار آپلود می‌شود، با کپشن
  کامل (خواننده، مدت، حجم، منبع، لینک) و **دکمه‌ی حذف** زیرش. file_id و
  message_id در جدول channel_songs ذخیره می‌شود تا دفعه بعد به‌جای دانلود از
  یوتیوب، فایل از تلگرام بازیابی شود.
- بکاپ دیتابیس: فایل musicbot.db شبانه به کانال لاگ فرستاده می‌شود.

نکته مهم: py-tgcalls نمی‌تواند از file_id مستقیم در کال پخش کند؛ برای پخش،
فایل باید مسیر محلی باشد. پس بازیابی از کانال = دانلود از CDN تلگرام (سریع)
سپس پخش از فایل محلی.

همه‌ی متن‌ها با `bot/channel_ui.py` ساخته می‌شوند (entities، بدون parse_mode).
"""
import logging
import os
import time
from typing import Optional

import config
from bot import app
from bot import channel_ui as cui
from bot import database as db

LOGGER = logging.getLogger("musicbot.channel")

DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/tmp/musicbot").strip() or "/tmp/musicbot"


def _norm_key(video_id: str, query: str) -> str:
    """کلید یکتا برای آرشیو: ترجیحاً video_id، وگرنه کوئری نرمال‌شده."""
    if video_id:
        return video_id
    from bot.facmd import normalize
    return "q:" + normalize(query or "").lower()


def media_title(media) -> tuple:
    """(عنوان، خواننده) را از آبجکت رسانه‌ی تلگرام بیرون می‌کشد."""
    performer = getattr(media, "performer", "") or ""
    title = getattr(media, "title", "") or getattr(media, "file_name", "") or ""
    if not title:
        title = "نامشخص"
    # پسوند فایل را از عنوان بردار
    for ext in (".mp3", ".m4a", ".opus", ".ogg", ".flac", ".wav", ".mp4", ".mkv"):
        if title.lower().endswith(ext):
            title = title[: -len(ext)]
            break
    return title.strip(), performer.strip()


def full_title(title: str, performer: str) -> str:
    """عنوان نمایشی: «خواننده - آهنگ» اگر خواننده معلوم باشد."""
    if performer and performer.lower() not in title.lower():
        return f"{performer} - {title}"
    return title


# ---------------- لاگ ----------------
async def log(text: str, entities=None) -> None:
    """ارسال یک پیام لاگ به کانال لاگ (اگر تنظیم شده باشد).

    `text, entities` را می‌پذیرد تا خروجی channel_ui با `*` قابل پاس دادن باشد.
    """
    if not config.LOG_CHANNEL:
        return
    try:
        await app.send_message(config.LOG_CHANNEL, text, entities=entities)
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("log channel send: %s", e)


# ---------------- کانال دیتابیس: خواندن ----------------
def archive_lookup(video_id: str = "", query: str = "") -> dict | None:
    """اگر آهنگ در کانال دیتابیس باشد، رکوردش را برمی‌گرداند."""
    if not config.ARCHIVE_CHANNEL:
        return None
    key = _norm_key(video_id, query)
    return db.archive_get(key)


# ---------------- کانال دیتابیس: انتشار ----------------
async def publish_song(client, local_path: str, title: str, performer: str = "",
                       duration: int = 0, file_size: int = 0, source: str = "",
                       added_by: int = 0, is_video: bool = False,
                       url: str = "", key: str = ""):
    """آهنگ را در کانال دیتابیس با کپشن کامل و دکمه‌ی حذف منتشر می‌کند.

    پیام ارسال‌شده را برمی‌گرداند (یا None اگر نشد).
    """
    if not config.ARCHIVE_CHANNEL:
        return None
    if not local_path or not os.path.isfile(local_path):
        return None

    disp = full_title(title, performer)
    k = key or _norm_key("", disp)
    if not file_size:
        try:
            file_size = os.path.getsize(local_path)
        except OSError:
            file_size = 0

    n_total = db.archive_count() + 1
    caption, ents = cui.song_caption(disp, performer, duration, file_size,
                                     source, url, n_total, is_video)
    kb = cui.song_keyboard(k)
    try:
        if is_video:
            msg = await client.send_video(
                config.ARCHIVE_CHANNEL, local_path, caption=caption,
                caption_entities=ents, duration=int(duration or 0),
                reply_markup=kb, supports_streaming=True)
            fid = msg.video.file_id if msg.video else None
        else:
            msg = await client.send_audio(
                config.ARCHIVE_CHANNEL, local_path, caption=caption,
                caption_entities=ents, duration=int(duration or 0),
                title=title, performer=performer or None, reply_markup=kb)
            fid = msg.audio.file_id if msg.audio else None
        if not fid:
            return None
        db.archive_put(k, fid, msg.id, disp, int(duration or 0), is_video,
                       performer=performer, file_size=int(file_size or 0),
                       source=source, added_by=added_by, url=url)
        LOGGER.info("ARCHIVE PUBLISH | %s (key=%s)", disp, k)
        await log(*cui.song_added_log(disp, source, db.archive_count()))
        return msg
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("publish song failed: %s", e)
        return None


async def archive_store(local_path: str, video_id: str, query: str,
                        title: str, duration: int, is_video: bool,
                        source: str = "youtube", url: str = "",
                        added_by: int = 0) -> None:
    """فایل دانلودشده را در کانال دیتابیس ثبت می‌کند (اگر تازه باشد)."""
    if not config.ARCHIVE_CHANNEL:
        return
    key = _norm_key(video_id, query)
    if db.archive_get(key):
        return                                  # قبلاً ثبت شده
    await publish_song(app, local_path, title=title, duration=duration,
                       source=source, is_video=is_video, url=url,
                       added_by=added_by, key=key)


async def store_message(message, source: str = "upload") -> bool:
    """رسانه‌ای که در خودِ کانال دیتابیس آپلود شده را ثبت می‌کند.

    برای پیام‌هایی که خودِ ربات نفرستاده و بازارسال هم نمی‌شوند.
    """
    media = getattr(message, "audio", None) or getattr(message, "video", None)
    if not media:
        return False
    title, performer = media_title(media)
    disp = full_title(title, performer)
    key = _norm_key("", disp)
    if db.archive_get(key):
        return False
    db.archive_put(key, media.file_id, message.id, disp,
                   int(getattr(media, "duration", 0) or 0),
                   bool(getattr(message, "video", None)),
                   performer=performer,
                   file_size=int(getattr(media, "file_size", 0) or 0),
                   source=source)
    LOGGER.info("ARCHIVE STORE MSG | %s (key=%s)", disp, key)
    # دکمه‌ی حذف را به پیام موجود اضافه کن
    try:
        await message.edit_reply_markup(cui.song_keyboard(key))
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("attach delete button: %s", e)
    await log(*cui.song_added_log(disp, source, db.archive_count()))
    return True


# سازگاری با نام قدیمی
async def store_forwarded(message) -> bool:
    return await store_message(message, source="forward")


async def archive_download(rec: dict, out_dir: str) -> str:
    """فایل آرشیوشده را از تلگرام دانلود می‌کند و مسیر محلی را برمی‌گرداند."""
    os.makedirs(out_dir, exist_ok=True)
    safe = rec["key"].replace(":", "_").replace("/", "_")
    try:
        path = await app.download_media(
            rec["file_id"], file_name=os.path.join(out_dir, f"arch_{safe}"))
        if path and os.path.isfile(path):
            return path
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("archive download by file_id failed: %s", e)
        try:
            if rec.get("message_id"):
                m = await app.get_messages(config.ARCHIVE_CHANNEL,
                                          rec["message_id"])
                path = await m.download(
                    file_name=os.path.join(out_dir, f"arch_{safe}"))
                if path and os.path.isfile(path):
                    return path
        except Exception as e2:  # noqa: BLE001
            LOGGER.warning("archive download by message_id failed: %s", e2)
    return ""


async def delete_from_archive(message) -> Optional[dict]:
    """آهنگی که رویش ریپلای شده را از دیتابیس حذف می‌کند."""
    rec = db.archive_delete(message_id=message.id)
    if rec:
        LOGGER.info("ARCHIVE DELETE | %s (msg=%s)", rec.get("title"), message.id)
        await log(*cui.song_deleted(rec.get("title", ""), db.archive_count()))
    return rec


# ---------------- بکاپ دیتابیس ----------------
_last_backup = 0.0


async def backup_db(force: bool = False) -> None:
    """فایل دیتابیس را به کانال لاگ می‌فرستد (حداکثر هر BACKUP_INTERVAL ثانیه)."""
    global _last_backup
    if not config.LOG_CHANNEL:
        return
    interval = int(os.environ.get("BACKUP_INTERVAL", str(6 * 3600)))
    now = time.time()
    if not force and now - _last_backup < interval:
        return
    if not os.path.isfile(config.DB_PATH):
        return
    try:
        cap, ents = cui.backup_caption(db.archive_count(), len(db.get_chats()))
        await app.send_document(
            config.LOG_CHANNEL, config.DB_PATH, caption=cap,
            caption_entities=ents, file_name="musicbot.db")
        _last_backup = now
        LOGGER.info("DB BACKUP sent to log channel")
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("db backup failed: %s", e)


# ---------------- بکاپ خودکفای env (برای انتقال کامل سرور) ----------------
_ENV_KEYS = [
    "API_ID", "API_HASH", "BOT_TOKEN", "STRING_SESSION", "OWNER_ID",
    "LOG_CHANNEL", "ARCHIVE_CHANNEL", "PAYMENT_CHANNEL", "COOKIES_B64",
    "PROXY_LIST", "POT_BASE_URL", "JS_RUNTIME", "DOWNLOAD_DIR",
    "DL_HARD_TIMEOUT", "DB_PATH", "COVER_PATH", "USE_SOUNDCLOUD", "SC_TIMEOUT",
    "DURATION_LIMIT", "CACHE_KEEP", "MP3_QUALITY", "AUDIO_FORMAT",
    "VIDEO_FORMAT", "USE_FREE_PROXIES", "PROXY_MAX_TRY", "PROXY_TIMEOUT",
    "ATTEMPT_HARD_TIMEOUT",
]


async def backup_env() -> None:
    """رشته‌ی خودکفای رمزنگاری‌شده‌ی همه‌ی env را به کانال لاگ می‌فرستد."""
    if not config.LOG_CHANNEL:
        return
    try:
        import bootstrap
        data = {k: os.environ.get(k, "") for k in _ENV_KEYS
                if os.environ.get(k, "") and k != "RESTORE_BLOB"}
        blob = bootstrap._make_blob(data)
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), "restore_blob.txt")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(blob)
        cap, ents = cui.restore_blob_caption()
        await app.send_document(config.LOG_CHANNEL, tmp, caption=cap,
                                caption_entities=ents,
                                file_name="restore_blob.txt")
        try:
            os.remove(tmp)
        except OSError:
            pass
        LOGGER.info("ENV BACKUP sent (self-contained blob)")
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("env backup failed: %s", e)


async def nightly_backup_loop() -> None:
    """هر شب ساعت مشخص (پیش‌فرض ۰۰:۰۰ تهران) بکاپ کامل می‌فرستد."""
    import asyncio
    hour = int(os.environ.get("BACKUP_HOUR", "0"))
    tz_off = int(os.environ.get("BACKUP_TZ_OFFSET", "210"))     # تهران +3:30
    while True:
        now = time.time() + tz_off * 60
        lt = time.gmtime(now)
        secs_today = lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec
        wait = hour * 3600 - secs_today
        if wait <= 0:
            wait += 24 * 3600
        await asyncio.sleep(wait)
        try:
            await backup_db(force=True)
            await backup_env()
        except Exception as e:  # noqa: BLE001
            LOGGER.warning("nightly backup: %s", e)


async def restore_db_from_channel() -> bool:
    """اگر دیتابیس محلی خالی باشد، آخرین بکاپ را از کانال لاگ بازیابی می‌کند."""
    if not config.LOG_CHANNEL:
        return False
    try:
        if db.get_chats() or db.archive_count() > 0 or db.list_special():
            return False
    except Exception:  # noqa: BLE001
        return False
    try:
        async for msg in app.get_chat_history(config.LOG_CHANNEL, limit=100):
            doc = getattr(msg, "document", None)
            if doc and (doc.file_name or "").endswith(".db"):
                tmp = config.DB_PATH + ".restore"
                await msg.download(file_name=tmp)
                if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                    db.close()
                    os.replace(tmp, config.DB_PATH)
                    LOGGER.info("DB RESTORED from channel (%s)", doc.file_name)
                    return True
        LOGGER.info("no db backup found in channel to restore")
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("restore db from channel: %s", e)
    return False
