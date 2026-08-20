"""جست‌وجو و استریم مستقیم از ساوندکلاد (بدون پروکسی — سریع).

ساوندکلاد روی IP دیتاسنتر معمولاً بلاک نمی‌شود، پس اولین منبع است.
اگر نتیجه‌ای نداشت، فراخواننده به یوتیوب برمی‌گردد.
"""
import asyncio
import os
import time
from typing import Optional

import yt_dlp

from bot import logs

_YDL = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "socket_timeout": 15,
    "retries": 1,
}

_AUDIO_FMT = "http_mp3_0_1/http_mp3/bestaudio[protocol=http]/bestaudio/best"


def _format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "نامشخص"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _extract(query: str) -> Optional[dict]:
    is_url = query.startswith(("http://", "https://")) and "soundcloud.com" in query
    search = query if is_url else f"scsearch1:{query}"
    opts = {**_YDL, "format": _AUDIO_FMT}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(search, download=False)
        if "entries" in info:
            entries = [e for e in info.get("entries", []) if e]
            if not entries:
                return None
            info = entries[0]
    url = info.get("url")
    if not url:
        return None
    return {
        "id": "sc_" + str(info.get("id", "")),
        "title": info.get("title", "نامشخص"),
        "duration": info.get("duration"),
        "duration_text": _format_duration(info.get("duration")),
        "stream_url": url,
        "webpage_url": info.get("webpage_url", ""),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader", ""),
        "source": "soundcloud",
    }


def _search_sync(query: str) -> Optional[dict]:
    t0 = time.monotonic()
    logs.stage_start("SC_SEARCH", query=query)
    try:
        info = _extract(query)
        if info:
            logs.stage_ok("SC_SEARCH", took=time.monotonic() - t0, title=info["title"])
            return info
        logs.stage_fail("SC_SEARCH", err="نتیجه‌ای نداشت", took=time.monotonic() - t0)
        return None
    except Exception as e:  # noqa: BLE001
        logs.stage_fail("SC_SEARCH", err=f"{type(e).__name__}: {str(e)[:100]}",
                        took=time.monotonic() - t0)
        return None


def enabled() -> bool:
    return os.environ.get("USE_SOUNDCLOUD", "1").strip().lower() in ("1", "true", "yes", "on")


async def search(query: str) -> Optional[dict]:
    """جست‌وجوی ساوندکلاد؛ اطلاعات آهنگ یا None. مهلت سخت دارد."""
    if not enabled():
        return None
    loop = asyncio.get_event_loop()
    hard = float(os.environ.get("SC_TIMEOUT", "10"))
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _search_sync, query), timeout=hard
        )
    except asyncio.TimeoutError:
        logs.stage_fail("SC_SEARCH", err=f"مهلت {hard:.0f}s تمام شد")
        return None
