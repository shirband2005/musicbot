"""روش «دیتابیس»: جست‌وجوی آهنگ از طریق ربات جستجوی خودمان (inline).

چرا یوزربات و نه ربات پلیر؟
    تلگرام به ربات‌ها اجازه نمی‌دهد آپدیت پیام ربات دیگر را ببینند، inline
    query بزنند، یا روی دکمه‌ی ربات دیگر کلیک کنند — حتی با دسترسی ادمین.
    یوزربات کمکی (`assistant`) یک اکانت واقعی است، پس همه‌ی این‌ها را می‌تواند.
    نتیجه: **ربات پلیر لازم نیست در گروه جستجو باشد؛ فقط یوزربات.**

جریان کار:
    ۱) یوزربات به ربات جستجو inline query می‌زند: `@zandXmusicBot <اسم آهنگ>`
    ۲) نتیجه‌ها را می‌گیرد (لیست ساختارمند، بدون پارس متن)
    ۳) نتیجه‌ی اول را در گروه جستجو می‌فرستد
    ۴) فایل صوتی را دانلود می‌کند و مسیر محلی را برمی‌گرداند
    ۵) پیام فرستاده‌شده در گروه جستجو پاک می‌شود (گروه تمیز بماند)

اگر هر مرحله شکست بخورد یا از SEARCH_TIMEOUT بگذرد، None برمی‌گردد و
مسیر پخش به یوتیوب fallback می‌کند.

تنظیمات محیطی:
    SEARCH_BOT     یوزرنیم ربات جستجو (پیش‌فرض zandXmusicBot)
    SEARCH_GROUP   شناسه‌ی گروه جستجو (عدد منفی)
    SEARCH_TIMEOUT ثانیه (پیش‌فرض ۲۵)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

import config
from bot import database as db

LOGGER = logging.getLogger("musicbot.searchbot")

DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/tmp/musicbot").strip() or "/tmp/musicbot"


def bot_username() -> str:
    return (os.environ.get("SEARCH_BOT", "").strip().lstrip("@")
            or "zandXmusicBot")


def group_id() -> int:
    return getattr(config, "SEARCH_GROUP", 0) or 0


def timeout() -> float:
    try:
        return float(os.environ.get("SEARCH_TIMEOUT", "25"))
    except ValueError:
        return 25.0


def enabled() -> bool:
    """روش دیتابیس فقط وقتی کار می‌کند که گروه جستجو تنظیم شده باشد."""
    return bool(group_id())


# ---------------------------------------------------------------- کمکی
_DUR_RE = re.compile(r"(\d{1,2}):(\d{2})")


def _parse_duration(text: str) -> int:
    """مدت را از متن نتیجه بیرون می‌کشد (مثل «2:13»). ۰ اگر پیدا نشد."""
    m = _DUR_RE.search(text or "")
    if not m:
        return 0
    return int(m.group(1)) * 60 + int(m.group(2))


def _clean_title(raw: str) -> str:
    """عنوان نتیجه را از ایموجی و فاصله‌های اضافه پاک می‌کند."""
    t = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", "", raw or "")
    return " ".join(t.split()).strip()


def _split_artist(title: str) -> tuple:
    """«خواننده - آهنگ» یا «آهنگ — خواننده» را به (عنوان، خواننده) می‌شکند."""
    for sep in (" — ", " – ", " - "):
        if sep in title:
            left, right = title.split(sep, 1)
            return right.strip(), left.strip()
    return title, ""


# ---------------------------------------------------------------- جست‌وجو
async def search(query: str, want_video: bool = False) -> list:
    """inline query به ربات جستجو می‌زند و نتیجه‌ها را برمی‌گرداند.

    هر آیتم: {"index", "title", "performer", "duration", "raw"}
    لیست خالی یعنی نتیجه‌ای نبود یا ربات جواب نداد.
    """
    if not enabled():
        return []
    from bot import assistant

    try:
        res = await asyncio.wait_for(
            assistant.get_inline_bot_results(bot_username(), query),
            timeout=timeout(),
        )
    except asyncio.TimeoutError:
        LOGGER.warning("SEARCHBOT timeout | q=%s", query)
        return []
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("SEARCHBOT inline query failed: %s", e)
        return []

    out = []
    for i, r in enumerate(getattr(res, "results", []) or []):
        raw_title = getattr(r, "title", "") or ""
        desc = getattr(r, "description", "") or ""
        title = _clean_title(raw_title)
        if not title:
            continue
        name, performer = _split_artist(title)
        out.append({
            "index": i,
            "title": title,
            "name": name,
            "performer": performer or _clean_title(desc),
            "duration": _parse_duration(desc) or _parse_duration(raw_title),
            "raw": raw_title,
            "query_id": getattr(res, "query_id", None),
            "result_id": getattr(r, "id", None),
        })
    LOGGER.info("SEARCHBOT | q=%s نتایج=%d", query, len(out))
    return out


async def fetch(query: str, pick: int = 0) -> dict | None:
    """نتیجه‌ی شماره‌ی `pick` را می‌گیرد، دانلود می‌کند و اطلاعاتش را برمی‌گرداند.

    خروجی: {"path", "title", "performer", "duration", "file_size"} یا None.
    پیام فرستاده‌شده در گروه جستجو پاک می‌شود تا گروه شلوغ نشود.
    """
    if not enabled():
        return None
    from bot import assistant

    results = await search(query)
    if not results:
        return None
    pick = max(0, min(pick, len(results) - 1))
    chosen = results[pick]

    sent = None
    path = ""
    try:
        sent = await asyncio.wait_for(
            assistant.send_inline_bot_result(
                group_id(), chosen["query_id"], chosen["result_id"]),
            timeout=timeout(),
        )
        # پیام واقعی (با فایل) را از گروه بخوان
        msg = await _resolve_message(assistant, sent)
        if msg is None:
            LOGGER.warning("SEARCHBOT: پیام نتیجه پیدا نشد")
            return None
        media = msg.audio or msg.voice or msg.document
        if media is None:
            LOGGER.warning("SEARCHBOT: نتیجه فایل صوتی نداشت")
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        path = await asyncio.wait_for(
            msg.download(file_name=os.path.join(DOWNLOAD_DIR,
                                               f"sb_{msg.id}")),
            timeout=max(60.0, timeout() * 3),
        )
        if not path or not os.path.isfile(path):
            return None

        title = (getattr(media, "title", "") or chosen["name"]
                 or chosen["title"])
        performer = getattr(media, "performer", "") or chosen["performer"]
        duration = int(getattr(media, "duration", 0) or chosen["duration"] or 0)
        size = int(getattr(media, "file_size", 0) or 0)
        if not size:
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0

        return {
            "path": path,
            "title": title,
            "performer": performer,
            "duration": duration,
            "file_size": size,
        }
    except asyncio.TimeoutError:
        LOGGER.warning("SEARCHBOT fetch timeout | q=%s", query)
        return None
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("SEARCHBOT fetch failed: %s", e)
        return None
    finally:
        # گروه جستجو را تمیز نگه دار
        if sent is not None:
            try:
                await _delete(assistant, sent)
            except Exception:  # noqa: BLE001
                pass


async def _resolve_message(client, sent):
    """`send_inline_bot_result` بسته به نسخه، پیام یا آبجکت آپدیت برمی‌گرداند."""
    if sent is None:
        return None
    if hasattr(sent, "audio") or hasattr(sent, "document"):
        return sent
    mid = getattr(sent, "id", None) or getattr(sent, "message_id", None)
    updates = getattr(sent, "updates", None)
    if mid is None and updates:
        for u in updates:
            m = getattr(u, "message", None)
            if m is not None and getattr(m, "id", None):
                mid = m.id
                break
    if mid is None:
        return None
    for _ in range(6):                       # چند تلاش کوتاه تا فایل برسد
        try:
            m = await client.get_messages(group_id(), mid)
            if m and (m.audio or m.voice or m.document):
                return m
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(0.7)
    return None


async def _delete(client, sent) -> None:
    mid = getattr(sent, "id", None) or getattr(sent, "message_id", None)
    if mid:
        await client.delete_messages(group_id(), mid)
