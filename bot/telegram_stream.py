"""استریم مستقیم فایل حجیم تلگرام به کال (بدون دانلود کامل روی دیسک).

معماری (تأییدشده با سورس py-tgcalls 2.3.3):
- یوزربات کمکی فایل را تیکه‌تیکه (۱ مگ، سقف پروتکل) با stream_media می‌خواند و
  روی یک سرور HTTP لوکال (127.0.0.1) سرو می‌کند.
- ffmpeg (داخل ntgcalls، منبع SHELL) از این URL می‌خواند، به ۳۶۰p تبدیل می‌کند.
- از `raw.Stream` با `MediaSource.SHELL` استفاده می‌شود که **check_stream (ffprobe)
  را دور می‌زند** — همان چیزی که با MediaStream معمولی FileNotFoundError می‌داد.

مزیت: فایل ۱ گیگی هرگز کامل روی Volume ذخیره نمی‌شود؛ همه ترافیک روی سرور.
"""
import asyncio
import logging
import os

from aiohttp import web
from ntgcalls import MediaSource
from pytgcalls.types.raw import (
    AudioParameters,
    AudioStream,
    Stream,
    VideoParameters,
    VideoStream,
)

from bot import assistant

LOGGER = logging.getLogger("musicbot.tgstream")

_HOST = "127.0.0.1"
_PORT = int(os.environ.get("TG_STREAM_PORT", "8799"))

# نگهداری وضعیت هر چت: message + سرور
_active: dict = {}
_runner = None
_started = False


async def _handler(request: web.Request) -> web.StreamResponse:
    """بایت‌های فایل تلگرام را به‌صورت جریانی سرو می‌کند (برای ffmpeg)."""
    chat_id = int(request.match_info["chat_id"])
    entry = _active.get(chat_id)
    if not entry:
        return web.Response(status=404, text="no active stream")
    message = entry["message"]

    resp = web.StreamResponse(status=200, headers={"Content-Type": "video/x-matroska"})
    await resp.prepare(request)
    written = 0
    try:
        async for chunk in assistant.stream_media(message):
            if not chunk:
                continue
            try:
                await resp.write(chunk)
                written += len(chunk)
            except (ConnectionResetError, asyncio.CancelledError):
                break
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("tgstream serve error (chat=%s, %d bytes): %s", chat_id, written, e)
    finally:
        try:
            await resp.write_eof()
        except Exception:  # noqa: BLE001
            pass
    LOGGER.info("tgstream served (chat=%s, %d bytes)", chat_id, written)
    return resp


async def _ensure_server() -> None:
    """سرور HTTP لوکال را یک‌بار بالا می‌آورد."""
    global _runner, _started
    if _started:
        return
    app = web.Application()
    app.router.add_get("/stream/{chat_id}", _handler)
    _runner = web.AppRunner(app)
    await _runner.setup()
    site = web.TCPSite(_runner, _HOST, _PORT)
    await site.start()
    _started = True
    LOGGER.info("tgstream HTTP server on %s:%d", _HOST, _PORT)


async def build_stream(chat_id: int, message) -> Stream:
    """یک raw.Stream (SHELL) می‌سازد که فیلم را از URL لوکال ۳۶۰p استریم می‌کند.

    این Stream را باید به call.play داد. چون منبع SHELL است، py-tgcalls
    مرحله‌ی probe (check_stream) را اجرا نمی‌کند و FileNotFoundError رخ نمی‌دهد.
    """
    await _ensure_server()
    _active[chat_id] = {"message": message}
    url = f"http://{_HOST}:{_PORT}/stream/{chat_id}"

    # دستورهای ffmpeg که خروجی خام برای ntgcalls تولید می‌کنند (۳۶۰p).
    common = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 2"
    vcmd = (
        f"ffmpeg {common} -i {url} -v quiet "
        f"-f rawvideo -r 20 -pix_fmt yuv420p -vf scale=640:360 pipe:1"
    )
    acmd = (
        f"ffmpeg {common} -i {url} -v quiet "
        f"-f s16le -ac 2 -ar 48000 pipe:1"
    )
    audio = AudioStream(MediaSource.SHELL, acmd, AudioParameters(48000, 2))
    video = VideoStream(MediaSource.SHELL, vcmd, VideoParameters(640, 360, 20))
    return Stream(microphone=audio, camera=video)


def stop_previous(chat_id: int) -> None:
    """وضعیت استریم فعال این چت را پاک می‌کند."""
    _active.pop(chat_id, None)
