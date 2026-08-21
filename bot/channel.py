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


# ---------------- بکاپ خودکفای env (برای انتقال کامل سرور) ----------------
# متغیرهای حساسی که برای راه‌اندازی ربات روی سرور جدید لازم‌اند
_ENV_KEYS = [
    "API_ID", "API_HASH", "BOT_TOKEN", "STRING_SESSION", "OWNER_ID",
    "LOG_CHANNEL", "ARCHIVE_CHANNEL", "COOKIES_B64", "PROXY_LIST",
    "POT_BASE_URL", "JS_RUNTIME", "DOWNLOAD_DIR", "DL_HARD_TIMEOUT",
    "DB_PATH", "COVER_PATH", "USE_SOUNDCLOUD", "SC_TIMEOUT",
    "DURATION_LIMIT", "CACHE_KEEP", "MP3_QUALITY", "AUDIO_FORMAT",
    "VIDEO_FORMAT", "USE_FREE_PROXIES", "PROXY_MAX_TRY", "PROXY_TIMEOUT",
    "ATTEMPT_HARD_TIMEOUT",
]


async def backup_env() -> None:
    """رشته‌ی خودکفای رمزنگاری‌شده‌ی همه‌ی env را به کانال لاگ می‌فرستد.

    این تک‌رشته (RESTORE_BLOB) شامل کلید رمز + داده است، پس برای بازیابی کامل
    روی سرور جدید فقط همین یک رشته کافی است: آن را در فیلد RESTORE_BLOB بگذار.
    """
    if not config.LOG_CHANNEL:
        return
    try:
        import bootstrap
        data = {k: os.environ.get(k, "") for k in _ENV_KEYS
                if os.environ.get(k, "") and k != "RESTORE_BLOB"}
        blob = bootstrap._make_blob(data)
        # به‌صورت فایل متنی (چون ممکن است طولانی باشد و در پیام معمولی جا نشود)
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), "restore_blob.txt")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(blob)
        await app.send_document(
            config.LOG_CHANNEL, tmp,
            caption="🔐 **رشته‌ی بازیابی کامل (RESTORE_BLOB)**\n"
                    "برای انتقال به سرور جدید: محتوای این فایل را در فیلد "
                    "`RESTORE_BLOB` هنگام دیپلوی بگذار. همه‌ی توکن‌ها و تنظیمات "
                    "خودکار ساخته می‌شوند. (این رشته را محرمانه نگه دار.)",
            file_name="restore_blob.txt",
        )
        try:
            os.remove(tmp)
        except OSError:
            pass
        LOGGER.info("ENV BACKUP sent (self-contained blob)")
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("env backup failed: %s", e)


async def nightly_backup_loop() -> None:
    """هر شب ساعت مشخص (پیش‌فرض ۰۰:۰۰ به وقت تهران) بکاپ کامل می‌فرستد.

    BACKUP_HOUR (ساعت محلی، پیش‌فرض 0) و BACKUP_TZ_OFFSET (دقیقه، پیش‌فرض 210=+3:30).
    """
    import asyncio
    hour = int(os.environ.get("BACKUP_HOUR", "0"))
    tz_off = int(os.environ.get("BACKUP_TZ_OFFSET", "210"))  # تهران +3:30
    while True:
        now = time.time() + tz_off * 60  # زمان محلی
        lt = time.gmtime(now)
        # ثانیه تا ساعت هدف بعدی
        secs_today = lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec
        target = hour * 3600
        wait = target - secs_today
        if wait <= 0:
            wait += 24 * 3600
        await asyncio.sleep(wait)
        try:
            await backup_db(force=True)
            await backup_env()
        except Exception as e:  # noqa: BLE001
            LOGGER.warning("nightly backup: %s", e)


async def restore_db_from_channel() -> bool:
    """اگر دیتابیس محلی خالی/تازه باشد، آخرین بکاپ را از کانال لاگ بازیابی می‌کند.

    برای سرور جدید: پس از دیپلوی، ربات با BOT_TOKEN وصل می‌شود، آخرین فایل
    musicbot.db را در کانال لاگ می‌یابد، دانلود و جایگزین می‌کند.
    خروجی: True اگر بازیابی انجام شد.
    """
    if not config.LOG_CHANNEL:
        return False
    # فقط وقتی دیتابیس واقعاً خالی است (سرور تازه) — از بازنویسی داده‌ی موجود جلوگیری کن
    try:
        if db.get_chats() or db.archive_count() > 0 or db.list_special():
            return False
    except Exception:  # noqa: BLE001
        return False
    try:
        # جدیدترین سند musicbot.db را در تاریخچه کانال پیدا کن
        async for msg in app.get_chat_history(config.LOG_CHANNEL, limit=100):
            doc = getattr(msg, "document", None)
            if doc and (doc.file_name or "").endswith(".db"):
                tmp = config.DB_PATH + ".restore"
                await msg.download(file_name=tmp)
                if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                    # اتصال دیتابیس را ببند و فایل را جایگزین کن
                    db.close()
                    os.replace(tmp, config.DB_PATH)
                    LOGGER.info("DB RESTORED from channel (%s)", doc.file_name)
                    return True
        LOGGER.info("no db backup found in channel to restore")
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("restore db from channel: %s", e)
    return False
