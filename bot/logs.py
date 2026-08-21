"""سیستم لاگ‌گیری دقیق و شفاف — هر بخش با وضعیت واضح (شروع/موفق/ناموفق).

هدف: در لاگ ریلوی دقیقاً مشخص باشد هر مرحله (جست‌وجو، استخراج، پیوستن به کال،
پخش، دانلود) چه زمانی شروع شد، چقدر طول کشید، موفق بود یا خطا خورد و چرا.
"""
import logging
import time
from contextlib import contextmanager

LOG = logging.getLogger("musicbot")


def _fmt_chat(chat_id) -> str:
    return f"chat={chat_id}" if chat_id is not None else ""


def stage_start(stage: str, chat_id=None, **info) -> None:
    extra = " ".join(f"{k}={v!r}" for k, v in info.items())
    LOG.info("▶️  START   | %-14s | %s %s", stage, _fmt_chat(chat_id), extra)


def stage_ok(stage: str, chat_id=None, took: float | None = None, **info) -> None:
    extra = " ".join(f"{k}={v!r}" for k, v in info.items())
    t = f"({took*1000:.0f}ms)" if took is not None else ""
    LOG.info("✅ SUCCESS  | %-14s | %s %s %s", stage, _fmt_chat(chat_id), t, extra)


def stage_fail(stage: str, chat_id=None, err: object = "", took: float | None = None, **info) -> None:
    extra = " ".join(f"{k}={v!r}" for k, v in info.items())
    t = f"({took*1000:.0f}ms)" if took is not None else ""
    LOG.error("❌ FAILED   | %-14s | %s %s %s err=%s", stage, _fmt_chat(chat_id), t, extra, err)


def info(msg: str, *args) -> None:
    LOG.info("ℹ️  %s", msg % args if args else msg)


def warn(msg: str, *args) -> None:
    LOG.warning("⚠️  %s", msg % args if args else msg)


def debug(msg: str, *args) -> None:
    LOG.debug("🐛 %s", msg % args if args else msg)


@contextmanager
def stage(name: str, chat_id=None, **info):
    """context manager: لاگ خودکار شروع/موفق/ناموفق همراه با زمان اجرا.

    مثال:
        with stage("YT_SEARCH", chat_id, query=q):
            ...
    """
    stage_start(name, chat_id, **info)
    t0 = time.monotonic()
    try:
        yield
    except Exception as e:  # noqa: BLE001
        stage_fail(name, chat_id, err=f"{type(e).__name__}: {e}", took=time.monotonic() - t0, **info)
        raise
    else:
        stage_ok(name, chat_id, took=time.monotonic() - t0, **info)


def classify_youtube_error(err: str) -> str:
    """تشخیص نوع خطای یوتیوب و پیام فارسی قابل‌فهم برای کاربر."""
    e = err.lower()
    if "sign in to confirm" in e or "not a bot" in e:
        return (
            "🤖 یوتیوب سرور را ربات تشخیص داد (محدودیت IP ابری).\n"
            "نیاز به کوکی یا PO Token دارد."
        )
    if "requested format is not available" in e:
        return "📉 هیچ فرمت قابل پخشی در دسترس نبود (احتمالاً نیاز به PO Token)."
    if "page needs to be reloaded" in e:
        return "🔄 خطای reload — کلاینت player اشتباه انتخاب شده."
    if "video unavailable" in e or "private video" in e:
        return "🚫 این ویدیو در دسترس نیست (خصوصی یا حذف‌شده)."
    if "age" in e and "restrict" in e:
        return "🔞 محتوای دارای محدودیت سنی (نیاز به کوکی حساب لاگین‌شده)."
    return "خطای نامشخص یوتیوب."
