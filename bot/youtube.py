"""جست‌وجو و استخراج اطلاعات از یوتیوب با استفاده از yt-dlp.

سیستم لاگ‌گیری دقیق: هر مرحله (جست‌وجو/استخراج/دانلود) با وضعیت شفاف
در لاگ ثبت می‌شود و زمان اجرا و نتیجه مشخص است.
"""
import asyncio
import os
import time
from typing import Optional

import yt_dlp

import config
from bot import logs

# --- گزینه‌های پایه yt-dlp ---
# نکته: player_client را دیگر به‌صورت ثابت مجبور نمی‌کنیم؛ اجازه می‌دهیم
# yt-dlp بر اساس کوکی/محیط بهترین کلاینت را انتخاب کند. اگر کوکی نبود،
# روی زنجیره‌ای از کلاینت‌ها تلاش می‌کنیم.
_YDL_COMMON = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "geo_bypass": True,
    "socket_timeout": 20,
    "retries": 3,
}

# زنجیره فرمت انعطاف‌پذیر (هر چه کلاینت فعال برگرداند پذیرفته شود)
_AUDIO_FMT = "bestaudio[ext=webm][acodec=opus]/bestaudio[ext=m4a]/bestaudio/best"
_VIDEO_FMT = (
    "(bestvideo[height<=?720][ext=mp4])+(bestaudio[ext=m4a])/"
    "best[height<=?720]/best"
)

# کلاینت‌هایی که وقتی کوکی نداریم امتحان می‌شوند (به ترتیب اولویت)
_CLIENT_FALLBACKS = [
    ["android"],
    ["ios"],
    ["tv"],
    ["mweb"],
    ["web"],
]


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


def _run_extract(search: str, fmt: str, client: Optional[list], download: bool, out_dir: str = "") -> dict:
    """یک تلاش استخراج با کلاینت مشخص."""
    opts = {**_YDL_COMMON, **_cookie_opts(), "format": fmt}
    if client:
        opts["extractor_args"] = {"youtube": {"player_client": client}}
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


def _extract_with_fallback(query: str, video: bool, download: bool = False, out_dir: str = "") -> dict:
    """استخراج با تلاش روی چند کلاینت تا موفقیت. لاگ دقیق هر تلاش."""
    is_url = query.startswith(("http://", "https://"))
    search = query if is_url else f"ytsearch1:{query}"
    fmt = _VIDEO_FMT if video else _AUDIO_FMT

    # اگر کوکی داریم، اول بدون اجبار کلاینت (اجازه انتخاب خودکار) تلاش کن
    attempts: list[Optional[list]] = []
    if has_cookies():
        logs.info("YT: کوکی موجود است — تلاش با انتخاب خودکار کلاینت")
        attempts.append(None)
    attempts += _CLIENT_FALLBACKS

    last_err: Optional[Exception] = None
    for client in attempts:
        label = "auto" if client is None else ",".join(client)
        t0 = time.monotonic()
        logs.stage_start("YT_TRY", query=query, client=label, video=video)
        try:
            info = _run_extract(search, fmt, client, download, out_dir)
            took = time.monotonic() - t0
            logs.stage_ok("YT_TRY", took=took, client=label, title=info.get("title", "?"))
            return info
        except Exception as e:  # noqa: BLE001
            took = time.monotonic() - t0
            last_err = e
            msg = str(e)
            logs.stage_fail("YT_TRY", err=f"{type(e).__name__}: {msg[:160]}", took=took, client=label)
            # اگر خطا ربطی به دسترسی/بلاک ندارد (مثلاً ویدیو حذف‌شده)، دیگر تلاش نکن
            low = msg.lower()
            if any(k in low for k in ("video unavailable", "private video", "removed")):
                break
            continue

    # همه تلاش‌ها شکست خورد
    logs.stage_fail("YT_EXTRACT", err=f"همه کلاینت‌ها ناموفق — {last_err}")
    raise last_err if last_err else RuntimeError("استخراج ناموفق")


def _extract(query: str, video: bool) -> dict:
    info = _extract_with_fallback(query, video, download=False)
    return _pack(info)


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
    """جست‌وجوی آهنگ/ویدیو و برگرداندن لینک استریم قابل‌پخش."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract, query, video)


async def download_audio(query: str, out_dir: str = "downloads") -> dict:
    """دانلود آهنگ به‌صورت فایل mp3 (اجرای همزمان در ترد جدا)."""
    os.makedirs(out_dir, exist_ok=True)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _download, query, out_dir)
