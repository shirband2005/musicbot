"""کانال‌ها: لاگ رویدادها + آرشیو آهنگ + بکاپ دیتابیس.

- LOG_CHANNEL: پیام‌های لاگ (روشن/خاموش، گروه جدید، خطا، ...).
- ARCHIVE_CHANNEL: هر آهنگ دانلودشده یک‌بار آپلود می‌شود و file_id + message_id
  در جدول channel_songs ذخیره می‌شود. دفعه بعد به‌جای دانلود از یوتیوب، فایل از
  تلگرام (کانال) بازیابی می‌شود — سریع، بدون پروکسی/کوکی.
- بکاپ دیتابیس: فایل musicbot.db دوره‌ای به کانال لاگ فرستاده می‌شود.

نکته مهم: py-tgcalls نمی‌تواند از file_id مستقیم در کال پخش کند؛ برای پخش،
فایل باید مسیر محلی باشد. پس بازیابی از کانال = دانلود از CDN تلگرام (سریع)
سپس پخش از فایل محلی.
"""
import logging
import os
import time

import config
from bot import app
from bot import database as db

LOGGER = logging.getLogger("musicbot.channel")


def _norm_key(video_id: str, query: str) -> str:
    """کلید یکتا برای آرشیو: ترجیحاً video_id، وگرنه کوئری نرمال‌شده."""
    if video_id:
        return video_id
    from bot.facmd import normalize
    return "q:" + normalize(query or "").lower()


# ---------------- لاگ ----------------
async def log(text: str) -> None:
    """ارسال یک پیام لاگ به کانال لاگ (اگر تنظیم شده باشد)."""
    if not config.LOG_CHANNEL:
        return
    try:
        await app.send_message(config.LOG_CHANNEL, text, disable_web_page_preview=True)
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("log channel send: %s", e)


# ---------------- آرشیو آهنگ ----------------
def archive_lookup(video_id: str = "", query: str = "") -> dict | None:
    """اگر آهنگ در آرشیو کانال باشد، رکوردش را برمی‌گرداند (file_id/message_id)."""
    if not config.ARCHIVE_CHANNEL:
        return None
    key = _norm_key(video_id, query)
    return db.archive_get(key)


async def archive_store(local_path: str, video_id: str, query: str,
                        title: str, duration: int, is_video: bool) -> None:
    """فایل دانلودشده را در کانال آرشیو آپلود و در دیتابیس ثبت می‌کند.

    اگر قبلاً همین کلید ثبت شده باشد، دوباره آپلود نمی‌کند.
    """
    if not config.ARCHIVE_CHANNEL:
        return
    if not local_path or not os.path.isfile(local_path):
        return
    key = _norm_key(video_id, query)
    if db.archive_get(key):
        return  # قبلاً آرشیو شده
    try:
        cap = f"🎵 {title}"
        if is_video:
            msg = await app.send_video(config.ARCHIVE_CHANNEL, local_path,
                                       caption=cap, duration=int(duration or 0))
            fid = msg.video.file_id if msg.video else None
        else:
            msg = await app.send_audio(config.ARCHIVE_CHANNEL, local_path,
                                       caption=cap, duration=int(duration or 0),
                                       title=title)
            fid = msg.audio.file_id if msg.audio else None
        if fid:
            db.archive_put(key, fid, msg.id, title, int(duration or 0), is_video)
            LOGGER.info("ARCHIVE STORE | %s (key=%s)", title, key)
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("archive store failed: %s", e)


async def archive_download(rec: dict, out_dir: str) -> str:
    """فایل آرشیوشده را از تلگرام (کانال) دانلود می‌کند و مسیر محلی را برمی‌گرداند.

    سریع (CDN تلگرام) و بدون نیاز به پروکسی/کوکی یوتیوب.
    """
    os.makedirs(out_dir, exist_ok=True)
    try:
        # دانلود با file_id مستقیم
        path = await app.download_media(
            rec["file_id"],
            file_name=os.path.join(out_dir, f"arch_{rec['key'].replace(':', '_')}"),
        )
        if path and os.path.isfile(path):
            return path
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("archive download by file_id failed: %s", e)
        # تلاش دوم: از روی message_id کانال
        try:
            if rec.get("message_id"):
                m = await app.get_messages(config.ARCHIVE_CHANNEL, rec["message_id"])
                path = await m.download(
                    file_name=os.path.join(out_dir, f"arch_{rec['key'].replace(':', '_')}")
                )
                if path and os.path.isfile(path):
                    return path
        except Exception as e2:  # noqa: BLE001
            LOGGER.warning("archive download by message_id failed: %s", e2)
    return ""


# ---------------- بکاپ دیتابیس ----------------
_last_backup = 0.0


async def backup_db(force: bool = False) -> None:
    """فایل دیتابیس را به کانال لاگ می‌فرستد (حداکثر هر BACKUP_INTERVAL ثانیه)."""
    global _last_backup
    if not config.LOG_CHANNEL:
        return
    interval = int(os.environ.get("BACKUP_INTERVAL", str(6 * 3600)))  # پیش‌فرض ۶ ساعت
    now = time.time()
    if not force and now - _last_backup < interval:
        return
    if not os.path.isfile(config.DB_PATH):
        return
    try:
        await app.send_document(
            config.LOG_CHANNEL,
            config.DB_PATH,
            caption=f"💾 بکاپ دیتابیس — {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(now))}\n"
                    f"آرشیو: {db.archive_count()} آهنگ",
            file_name="musicbot.db",
        )
        _last_backup = now
        LOGGER.info("DB BACKUP sent to log channel")
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("db backup failed: %s", e)
