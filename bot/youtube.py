"""جست‌وجو و استخراج اطلاعات از یوتیوب با استفاده از yt-dlp.

استراتژی دور زدن بلاک IP ابری:
  1. اول بدون پروکسی (اگر IP سرور تمیز باشد سریع‌ترین است).
  2. اگر خطای بات/بلاک خوردیم و پروکسی فعال است، روی چند پروکسی از استخر
     چرخشی تلاش می‌کنیم تا یکی جواب دهد.
  3. برای هر تلاش، چند player_client هم امتحان می‌شود.
سیستم لاگ‌گیری دقیق: هر تلاش با وضعیت شفاف (کلاینت + پروکسی + زمان) ثبت می‌شود.
"""
import asyncio
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FTimeout
from typing import Optional
from urllib.parse import urlparse

import yt_dlp

import config
from bot import logs
from bot import proxies

_YDL_COMMON = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "geo_bypass": True,
    "socket_timeout": 20,
    "retries": 2,
}

_AUDIO_FMT = "bestaudio[ext=webm][acodec=opus]/bestaudio[ext=m4a]/bestaudio/best"
_VIDEO_FMT = (
    "(bestvideo[height<=?720][ext=mp4])+(bestaudio[ext=m4a])/"
    "best[height<=?720]/best"
)

# آدرس سرویس PO Token محلی (bgutil) — در همان کانتینر اجرا می‌شود.
_POT_BASE_URL = os.environ.get("POT_BASE_URL", "http://127.0.0.1:4416").strip()


def _pot_available() -> bool:
    """آیا سرویس PO Token در دسترس است؟ (فعال بودن پلاگین)"""
    return os.environ.get("DISABLE_POT", "").strip().lower() not in ("1", "true", "yes")


# کلاینت‌هایی که بدون پروکسی امتحان می‌شوند.
# با کوکی + PO Token + JS runtime، کلاینت پیش‌فرض (None=web/tv) بهترین نتیجه را می‌دهد.
_CLIENTS_DIRECT = [None, ["web_safari"], ["mweb"], ["tv"], ["ios"]]
# با پروکسی، کلاینت سبک‌تر (تلاش کمتر برای سرعت)
_CLIENTS_PROXY = [None, ["web_safari"], ["ios"]]

# نشانه‌های خطای بلاک IP که باید روی پروکسی سوییچ کنیم
_BLOCK_SIGNS = (
    "sign in to confirm",
    "not a bot",
    "http error 403",
    "unable to download",
    "failed to extract",
    "login_required",
)


def has_cookies() -> bool:
    return bool(config.COOKIES_FILE and os.path.isfile(config.COOKIES_FILE))


def _cookie_opts() -> dict:
    return {"cookiefile": config.COOKIES_FILE} if has_cookies() else {}


def _format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "زنده / نامشخص"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _pack(info: dict) -> dict:
    return {
        "id": info.get("id"),
        "title": info.get("title", "نامشخص"),
        "duration": info.get("duration"),
        "duration_text": _format_duration(info.get("duration")),
        "stream_url": info.get("url"),
        "webpage_url": info.get("webpage_url", ""),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader", ""),
    }


def _is_block_error(msg: str) -> bool:
    low = msg.lower()
    return any(sign in low for sign in _BLOCK_SIGNS)


def _run(search: str, fmt: str, client: Optional[list], proxy: Optional[str],
         download: bool, out_dir: str) -> dict:
    opts = {**_YDL_COMMON, **_cookie_opts(), "format": fmt}

    # فعال‌کردن node به‌عنوان JS runtime برای حل چالش رمز/n یوتیوب.
    # بدون این، yt-dlp می‌گوید "The page needs to be reloaded" یا فرمت‌ها ناقص‌اند.
    # قالب صحیح: dict از {نام‌رانتایم: {تنظیمات}}
    js_rt = os.environ.get("JS_RUNTIME", "node").strip()
    if js_rt:
        opts["js_runtimes"] = {js_rt: {}}

    extractor_args = {}
    if client:
        extractor_args["youtube"] = {"player_client": client}
    # اتصال به سرویس PO Token محلی (bgutil) برای تولید خودکار توکن
    if _pot_available():
        extractor_args["youtubepot-bgutilhttp"] = {"base_url": [_POT_BASE_URL]}
    if extractor_args:
        opts["extractor_args"] = extractor_args

    if proxy:
        opts["proxy"] = proxy
        # با پروکسی، تایم‌اوت کوتاه تا پروکسی خراب سریع رد شود.
        # نکته: socket_timeout به‌تنهایی کل درخواست را محدود نمی‌کند؛
        # اجرای واقعی زیر یک مهلت سخت (hard timeout) قرار می‌گیرد.
        opts["socket_timeout"] = int(os.environ.get("PROXY_TIMEOUT", "8"))
        opts["retries"] = 0
    if download:
        opts["outtmpl"] = os.path.join(out_dir, "%(id)s.%(ext)s")
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(search, download=download)
        if "entries" in info:
            if not info["entries"]:
                raise ValueError("چیزی پیدا نشد")
            info = info["entries"][0]
    return info


def _proxy_alive(proxy: str, timeout: float = 3.0) -> bool:
    """پیش‌بررسی سریع TCP: آیا پروکسی اصلاً پاسخ می‌دهد؟ (رد سریع مرده‌ها)"""
    try:
        u = urlparse(proxy)
        host, port = u.hostname, u.port or 8080
        if not host:
            return False
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:  # noqa: BLE001
        return False


def _try_clients(search: str, fmt: str, clients: list, proxy: Optional[str],
                 download: bool, out_dir: str):
    """روی چند کلاینت با یک پروکسی مشخص تلاش می‌کند. (info, None) یا (None, last_err).

    هر تلاش زیر یک مهلت سخت (hard timeout) قرار دارد تا پروکسی/شبکه‌ی کند
    هرگز کل سیستم را قفل نکند.
    """
    hard = float(os.environ.get("ATTEMPT_HARD_TIMEOUT", "20" if proxy else "60"))
    last_err = None
    for client in clients:
        label = ",".join(client) if client else "auto"
        pxy = proxy.split("@")[-1] if proxy else "direct"
        t0 = time.monotonic()
        logs.stage_start("YT_TRY", client=label, proxy=pxy)
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_run, search, fmt, client, proxy, download, out_dir)
                try:
                    info = fut.result(timeout=hard)
                except FTimeout:
                    logs.stage_fail("YT_TRY", err=f"مهلت {hard:.0f}s تمام شد",
                                    took=time.monotonic() - t0, client=label, proxy=pxy)
                    last_err = TimeoutError(f"hard timeout {hard}s")
                    # با پروکسیِ کند، کل پروکسی را رها کن؛ در حالت مستقیم سراغ کلاینت بعدی
                    if proxy:
                        return None, last_err
                    continue
            logs.stage_ok("YT_TRY", took=time.monotonic() - t0, client=label,
                          proxy=pxy, title=info.get("title", "?"))
            return info, None
        except Exception as e:  # noqa: BLE001
            last_err = e
            msg = str(e)
            logs.stage_fail("YT_TRY", err=f"{type(e).__name__}: {msg[:120]}",
                            took=time.monotonic() - t0, client=label, proxy=pxy)
            low = msg.lower()
            if any(k in low for k in ("video unavailable", "private video", "removed")):
                return None, e  # خطای محتوایی — ادامه بی‌فایده است
    return None, last_err


def _extract_with_fallback(query: str, video: bool, download: bool = False, out_dir: str = "") -> dict:
    is_url = query.startswith(("http://", "https://"))
    search = query if is_url else f"ytsearch1:{query}"
    fmt = _VIDEO_FMT if video else _AUDIO_FMT

    logs.info("YT: کوکی=%s | پروکسی=%s", has_cookies(), proxies.enabled())

    # مرحله ۱: تلاش مستقیم (بدون پروکسی)
    info, err = _try_clients(search, fmt, _CLIENTS_DIRECT, None, download, out_dir)
    if info is not None:
        return info

    # اگر خطا مربوط به بلاک نیست، پروکسی هم کمکی نمی‌کند
    if err and not _is_block_error(str(err)):
        logs.stage_fail("YT_EXTRACT", err=f"خطای غیربلاکی: {str(err)[:120]}")
        raise err

    # مرحله ۲: چرخش روی استخر پروکسی
    if not proxies.enabled():
        logs.stage_fail("YT_EXTRACT", err="بلاک IP و پروکسی غیرفعال است")
        raise err if err else RuntimeError("بلاک IP")

    proxy_list = proxies.candidates(limit=int(os.environ.get("PROXY_MAX_TRY", "40")))
    logs.info("YT: سوییچ به پروکسی — %d کاندید", len(proxy_list))
    if not proxy_list:
        logs.stage_fail("YT_EXTRACT", err="استخر پروکسی خالی است")
        raise err if err else RuntimeError("پروکسی موجود نیست")

    last_err = err
    tried = 0
    for i, proxy in enumerate(proxy_list, 1):
        # پیش‌بررسی سریع: پروکسی مرده را بدون اتلاف وقت رد کن
        if not _proxy_alive(proxy):
            proxies.mark_bad(proxy)
            continue
        tried += 1
        info, e = _try_clients(search, fmt, _CLIENTS_PROXY, proxy, download, out_dir)
        if info is not None:
            proxies.mark_good(proxy)
            logs.stage_ok("YT_EXTRACT", note=f"موفق با پروکسی #{i}")
            return info
        proxies.mark_bad(proxy)
        last_err = e or last_err

    logs.stage_fail("YT_EXTRACT", err=f"همه پروکسی‌ها ناموفق ({tried} پروکسی زنده امتحان شد)")
    raise last_err if last_err else RuntimeError("استخراج ناموفق")


def _extract(query: str, video: bool) -> dict:
    return _pack(_extract_with_fallback(query, video, download=False))


def _download(query: str, out_dir: str) -> dict:
    info = _extract_with_fallback(query, video=False, download=True, out_dir=out_dir)
    path = os.path.join(out_dir, f"{info['id']}.mp3")
    return {
        "path": path,
        "title": info.get("title", "audio"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader", ""),
    }


async def get_media(query: str, video: bool = False) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract, query, video)


async def download_audio(query: str, out_dir: str = "downloads") -> dict:
    os.makedirs(out_dir, exist_ok=True)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _download, query, out_dir)
