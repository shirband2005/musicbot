"""استریم مستقیم فایل حجیم تلگرام به کال (بدون دانلود کامل روی دیسک).

معماری (تأییدشده با سورس py-tgcalls 2.3.3):
- یوزربات کمکی فایل را **یک بار** تیکه‌تیکه (۱ مگ) با stream_media می‌خواند و
  به‌صورت broadcast به **همه‌ی** مشترک‌ها (پروسه‌های ffmpeg صدا و تصویر) می‌فرستد.
  این کلید رفع باگ «یکی از صدا/تصویر خالی می‌ماند» است: فایل تلگرام را نمی‌توان
  دو بار موازی خواند، پس یک reader می‌خواند و به دو صف پخش می‌کند.
- ffmpeg (داخل ntgcalls، منبع SHELL) از URL لوکال می‌خواند.
- از `raw.Stream` با `MediaSource.SHELL` استفاده می‌شود که check_stream (ffprobe)
  را دور می‌زند — همان چیزی که با MediaStream معمولی FileNotFoundError می‌داد.

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

# وضعیت هر چت: پیام + reader task + لیست صف مشترک‌ها + شمارش اتصال
_state: dict = {}
_runner = None
_started = False

_QUEUE_MAX = 256  # حداکثر تیکه در صف هر مشترک (بافر ~۲۵۶ مگ برای جلوگیری از قطع)


class _Broadcast:
    """یک reader که فایل تلگرام را یک بار می‌خواند و به چند subscriber می‌دهد.

    نکته‌ی حیاتی: reader تا وقتی **هر دو** مصرف‌کننده (ffmpeg صدا و تصویر) وصل
    نشده‌اند شروع نمی‌شود؛ وگرنه مصرف‌کننده‌ای که دیر وصل شود **هدر کانتینر
    (ابتدای فایل)** را از دست می‌دهد و نمی‌تواند استریم را پارس کند.
    """

    def __init__(self, message, expected: int = 2):
        self.message = message
        self.subscribers: list = []
        self.reader_task = None
        self.started = False
        self.expected = expected
        self._ready = asyncio.Event()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
        self.subscribers.append(q)
        # وقتی همه‌ی مصرف‌کننده‌های مورد انتظار وصل شدند، به reader اجازه‌ی شروع بده
        if len(self.subscribers) >= self.expected:
            self._ready.set()
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self.subscribers:
            self.subscribers.remove(q)

    def start(self) -> None:
        if not self.started:
            self.started = True
            self.reader_task = asyncio.create_task(self._read())

    async def _read(self) -> None:
        # منتظر بمان تا هر دو مصرف‌کننده وصل شوند (حداکثر ۱۰ ثانیه)
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=10)
        except asyncio.TimeoutError:
            LOGGER.warning("tgstream: فقط %d مصرف‌کننده وصل شد، بدون انتظار شروع می‌شود",
                           len(self.subscribers))
        total = 0
        try:
            async for chunk in assistant.stream_media(self.message):
                if not chunk:
                    continue
                total += len(chunk)
                # به همه‌ی مشترک‌های فعلی بده (هر کدام صف خودش)؛ backpressure
                # از طریق await put باعث هماهنگی صدا و تصویر می‌شود.
                for q in list(self.subscribers):
                    try:
                        await q.put(chunk)
                    except Exception:  # noqa: BLE001
                        pass
            LOGGER.info("tgstream broadcast finished (%d bytes)", total)
        except asyncio.CancelledError:
            LOGGER.info("tgstream broadcast cancelled (%d bytes)", total)
        except Exception as e:  # noqa: BLE001
            LOGGER.warning("tgstream broadcast error (%d bytes): %s", total, e)
        finally:
            for q in list(self.subscribers):
                try:
                    q.put_nowait(None)
                except Exception:  # noqa: BLE001
                    pass


async def _handler(request: web.Request) -> web.StreamResponse:
    """بایت‌های فایل تلگرام را به یک پروسه‌ی ffmpeg (صدا یا تصویر) سرو می‌کند.

    از broadcast مشترک استفاده می‌کند تا فایل فقط یک بار از تلگرام خوانده شود.
    """
    chat_id = int(request.match_info["chat_id"])
    st = _state.get(chat_id)
    if not st:
        return web.Response(status=404, text="no active stream")
    bc: _Broadcast = st["broadcast"]

    resp = web.StreamResponse(status=200, headers={"Content-Type": "video/x-matroska"})
    await resp.prepare(request)

    q = bc.subscribe()
    bc.start()  # اولین اتصال reader را استارت می‌کند (بقیه به همان می‌پیوندند)
    written = 0
    try:
        while True:
            chunk = await q.get()
            if chunk is None:  # EOF
                break
            try:
                await resp.write(chunk)
                written += len(chunk)
            except (ConnectionResetError, asyncio.CancelledError):
                break
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("tgstream serve (chat=%s, %d bytes): %s", chat_id, written, e)
    finally:
        bc.unsubscribe(q)
        try:
            await resp.write_eof()
        except Exception:  # noqa: BLE001
            pass
    LOGGER.info("tgstream served one consumer (chat=%s, %d bytes)", chat_id, written)
    return resp


async def _ensure_server() -> None:
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
    """یک raw.Stream (SHELL) می‌سازد که فیلم را از URL لوکال استریم می‌کند.

    صدا و تصویر هر دو از یک broadcast مشترک تغذیه می‌شوند (فایل یک بار خوانده می‌شود).
    """
    await _ensure_server()
    stop_previous(chat_id)
    _state[chat_id] = {"broadcast": _Broadcast(message)}
    url = f"http://{_HOST}:{_PORT}/stream/{chat_id}"

    # کیفیت ثابت ۲۴۰p / ۱۵fps — اولویت با روانی پخش (قابل override با env).
    vparams = os.environ.get("TG_STREAM_VF", "scale=426:240")
    vfps = int(os.environ.get("TG_STREAM_FPS", "15"))
    vw, vh = 426, 240
    try:
        if vparams.startswith("scale="):
            wh = vparams.split("=", 1)[1].split(":")
            vw, vh = int(wh[0]), int(wh[1])
    except Exception:  # noqa: BLE001
        pass

    # فلگ‌های reconnect برای HTTP لوکال (جلوگیری از قطع وسط پخش) + بافر ورودی.
    common = (
        "-reconnect 1 -reconnect_streamed 1 -reconnect_at_eof 0 "
        "-reconnect_delay_max 5 -rw_timeout 30000000 -threads 0"
    )
    vlog = f"/tmp/tgv_{chat_id}.log"
    alog = f"/tmp/tga_{chat_id}.log"
    vsh = f"/tmp/tgv_{chat_id}.sh"
    ash = f"/tmp/tga_{chat_id}.sh"
    # منبع SHELL کاراکترهای شل (2>, |) را نمی‌پذیرد → دستور را در wrapper می‌گذاریم.
    with open(vsh, "w") as fh:
        fh.write(
            f"#!/bin/bash\nexec ffmpeg {common} -i '{url}' -an -v error "
            f"-map 0:v:0? -f rawvideo -r {vfps} -pix_fmt yuv420p -vf {vparams} pipe:1 2>{vlog}\n"
        )
    with open(ash, "w") as fh:
        fh.write(
            f"#!/bin/bash\nexec ffmpeg {common} -i '{url}' -vn -v error "
            f"-map 0:a:0? -f s16le -ac 2 -ar 48000 pipe:1 2>{alog}\n"
        )
    os.chmod(vsh, 0o755)
    os.chmod(ash, 0o755)
    audio = AudioStream(MediaSource.SHELL, f"bash {ash}", AudioParameters(48000, 2))
    video = VideoStream(MediaSource.SHELL, f"bash {vsh}", VideoParameters(vw, vh, vfps))
    asyncio.create_task(_report_logs(chat_id, alog, vlog))
    return Stream(microphone=audio, camera=video)


async def _report_logs(chat_id: int, alog: str, vlog: str) -> None:
    """چند ثانیه پس از شروع، خطاهای ffmpeg را در لاگ اصلی چاپ می‌کند."""
    await asyncio.sleep(8)
    for name, path in (("AUDIO", alog), ("VIDEO", vlog)):
        try:
            if os.path.isfile(path):
                with open(path, "r", errors="ignore") as fh:
                    txt = fh.read().strip()
                if txt:
                    LOGGER.warning("ffmpeg %s (chat=%s):\n%s", name, chat_id, txt[:800])
                else:
                    LOGGER.info("ffmpeg %s (chat=%s): بدون خطا", name, chat_id)
        except Exception:  # noqa: BLE001
            pass


def stop_previous(chat_id: int) -> None:
    """reader و وضعیت استریم فعال این چت را پاک می‌کند."""
    st = _state.pop(chat_id, None)
    if not st:
        return
    bc = st.get("broadcast")
    if bc and bc.reader_task and not bc.reader_task.done():
        bc.reader_task.cancel()
