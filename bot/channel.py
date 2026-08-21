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


# ---------------- بکاپ رمزنگاری‌شده‌ی env (برای انتقال کامل سرور) ----------------
# متغیرهای حساسی که برای راه‌اندازی ربات روی سرور جدید لازم‌اند
_ENV_KEYS = [
    "API_ID", "API_HASH", "BOT_TOKEN", "STRING_SESSION", "OWNER_ID",
    "LOG_CHANNEL", "ARCHIVE_CHANNEL", "COOKIES_B64", "PROXY_LIST",
    "POT_BASE_URL", "JS_RUNTIME", "DOWNLOAD_DIR", "DL_HARD_TIMEOUT",
    "DB_PATH", "COVER_PATH", "USE_SOUNDCLOUD", "SC_TIMEOUT",
    "DURATION_LIMIT", "CACHE_KEEP", "MP3_QUALITY", "AUDIO_FORMAT",
    "VIDEO_FORMAT", "USE_FREE_PROXIES", "PROXY_MAX_TRY", "PROXY_TIMEOUT",
    "ATTEMPT_HARD_TIMEOUT", "BACKUP_KEY",
]


def _fernet():
    """کلید رمزنگاری از BACKUP_KEY می‌سازد (Fernet). None اگر کتابخانه/کلید نباشد."""
    key = os.environ.get("BACKUP_KEY", "").strip()
    if not key:
        return None
    try:
        import base64
        import hashlib
        from cryptography.fernet import Fernet
        # هر رشته‌ای را به کلید ۳۲بایتی معتبر Fernet تبدیل کن
        digest = hashlib.sha256(key.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("fernet init failed: %s", e)
        return None


async def backup_env() -> None:
    """متغیرهای env حساس را رمزنگاری و به کانال لاگ می‌فرستد.

    نیاز به BACKUP_KEY (رمز دلخواه) دارد؛ بدون آن هیچ چیزی فرستاده نمی‌شود
    (تا توکن‌ها لخت لو نروند). برای بازیابی: فایل .env.bak را با همان کلید
    رمزگشایی کن (اسکریپت restore_env.py).
    """
    if not config.LOG_CHANNEL:
        return
    f = _fernet()
    if f is None:
        LOGGER.info("env backup skipped (BACKUP_KEY تنظیم نشده)")
        return
    try:
        import json
        import tempfile
        data = {k: os.environ.get(k, "") for k in _ENV_KEYS if os.environ.get(k, "")}
        blob = f.encrypt(json.dumps(data, ensure_ascii=False).encode())
        tmp = os.path.join(tempfile.gettempdir(), "env.bak")
        with open(tmp, "wb") as fh:
            fh.write(blob)
        await app.send_document(
            config.LOG_CHANNEL, tmp,
            caption="🔐 بکاپ رمزنگاری‌شده‌ی تنظیمات (env)\n"
                    "برای بازیابی: `python restore_env.py env.bak` با همان BACKUP_KEY.",
            file_name="env.bak",
        )
        try:
            os.remove(tmp)
        except OSError:
            pass
        LOGGER.info("ENV BACKUP sent (encrypted)")
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
