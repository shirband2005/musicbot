"""استریم مستقیم فایل حجیم تلگرام به کال (بدون دانلود کامل روی دیسک).

روش: یوزربات کمکی فایل را تیکه‌تیکه (۱ مگ، سقف پروتکل تلگرام) با stream_media
می‌خواند و در یک FIFO (لوله‌ی نامدار) می‌ریزد؛ ffmpeg داخل py-tgcalls از همان
FIFO می‌خواند، به ۳۶۰p تبدیل و در کال پخش می‌کند.

مزیت: فایل ۱ گیگی هرگز کامل روی Volume ذخیره نمی‌شود (فقط چند مگ بافر در لحظه).
همه‌ی ترافیک روی سرور است (اینترنت کاربر مصرف نمی‌شود).
"""
import asyncio
import logging
import os
import tempfile

from bot import assistant

LOGGER = logging.getLogger("musicbot.tgstream")

# اندازه‌ی بافر پیش‌نگر: چند تیکه‌ی ۱ مگی که همزمان نگه داشته می‌شوند تا پخش
# روان بماند (خواندن از تلگرام از پخش جلوتر باشد).
_BUFFER_CHUNKS = int(os.environ.get("TG_STREAM_BUFFER_MB", "8"))  # مگابایت

# نگهداری تسک‌های فعال feeder برای هر چت (تا هنگام توقف کنسل شوند)
_feeders: dict = {}


def make_fifo(chat_id: int) -> str:
    """یک FIFO یکتا برای این چت می‌سازد و مسیرش را برمی‌گرداند."""
    d = tempfile.gettempdir()
    path = os.path.join(d, f"tgstream_{chat_id}_{os.getpid()}.pipe")
    # اگر از قبل مانده، پاک کن
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
    os.mkfifo(path)
    return path


async def start_feeder(chat_id: int, message) -> str:
    """خواندن تیکه‌ای فایل از تلگرام و نوشتن در FIFO را در پس‌زمینه آغاز می‌کند.

    message: پیام تلگرامی که حاوی ویدیو/فایل است (از دید یوزربات کمکی).
    برمی‌گرداند: مسیر FIFO که به ffmpeg داده می‌شود.
    """
    fifo = make_fifo(chat_id)
    stop_previous(chat_id)

    async def _feed():
        # باز کردن FIFO برای نوشتن (بلاک می‌شود تا ffmpeg سمت خواندن را باز کند)
        fd = None
        try:
            # open در حالت نوشتن تا وقتی خواننده وصل نشود بلاک است؛
            # پس در یک thread جدا باز می‌کنیم تا event loop بلاک نشود.
            loop = asyncio.get_event_loop()
            fd = await loop.run_in_executor(None, lambda: open(fifo, "wb"))
            written = 0
            async for chunk in assistant.stream_media(message):
                if not chunk:
                    continue
                try:
                    await loop.run_in_executor(None, fd.write, chunk)
                    written += len(chunk)
                except BrokenPipeError:
                    # ffmpeg بسته شد (پخش تمام/متوقف) → پایان
                    LOGGER.info("tgstream feeder: pipe closed (chat=%s, %d bytes)", chat_id, written)
                    break
            LOGGER.info("tgstream feeder finished (chat=%s, %d bytes)", chat_id, written)
        except asyncio.CancelledError:
            LOGGER.info("tgstream feeder cancelled (chat=%s)", chat_id)
        except Exception as e:  # noqa: BLE001
            LOGGER.warning("tgstream feeder error (chat=%s): %s", chat_id, e)
        finally:
            if fd is not None:
                try:
                    fd.close()
                except Exception:  # noqa: BLE001
                    pass
            try:
                if os.path.exists(fifo):
                    os.remove(fifo)
            except OSError:
                pass

    task = asyncio.create_task(_feed())
    _feeders[chat_id] = (task, fifo)
    return fifo


def stop_previous(chat_id: int) -> None:
    """اگر feeder فعالی برای این چت هست، کنسلش کن و FIFO را پاک کن."""
    entry = _feeders.pop(chat_id, None)
    if not entry:
        return
    task, fifo = entry
    if task and not task.done():
        task.cancel()
    try:
        if fifo and os.path.exists(fifo):
            os.remove(fifo)
    except OSError:
        pass
