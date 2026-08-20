"""جست‌وجو و استخراج اطلاعات از یوتیوب با استفاده از yt-dlp."""
import asyncio
import os
from typing import Optional

import yt_dlp

import config

# ترفند دور زدن خطای «Sign in to confirm you're not a bot» روی IPهای ابری
_YDL_COMMON = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "geo_bypass": True,
    "extractor_args": {
        "youtube": {"player_client": ["tv", "ios", "android", "web_safari"]}
    },
}


def _cookie_opts() -> dict:
    if config.COOKIES_FILE and os.path.isfile(config.COOKIES_FILE):
        return {"cookiefile": config.COOKIES_FILE}
    return {}


def _format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "زنده / نامشخص"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _extract(query: str, video: bool) -> dict:
    """اجرای همزمان yt-dlp (در ترد جدا صدا زده می‌شود)."""
    is_url = query.startswith(("http://", "https://"))
    search = query if is_url else f"ytsearch1:{query}"

    fmt = (
        "bestvideo[height<=720]+bestaudio/best[height<=720]"
        if video
        else "bestaudio/best"
    )
    opts = {**_YDL_COMMON, **_cookie_opts(), "format": fmt}

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(search, download=False)
        if "entries" in info:
            if not info["entries"]:
                raise ValueError("چیزی پیدا نشد")
            info = info["entries"][0]

    return {
        "title": info.get("title", "نامشخص"),
        "duration": info.get("duration"),
        "duration_text": _format_duration(info.get("duration")),
        "stream_url": info.get("url"),
        "webpage_url": info.get("webpage_url", query),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader", ""),
    }


async def get_media(query: str, video: bool = False) -> dict:
    """جست‌وجوی آهنگ/ویدیو و برگرداندن لینک استریم قابل‌پخش."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract, query, video)
