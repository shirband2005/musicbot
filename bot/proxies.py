"""استخر پروکسی چرخشی — برای دور زدن بلاک IP یوتیوب روی سرورهای ابری.

پروکسی‌ها از منابع زیر خوانده می‌شوند (به‌ترتیب اولویت):
  1. متغیر محیطی PROXY_LIST  (پروکسی‌ها با کاما یا خط‌جدید جدا شده)
  2. متغیر محیطی PROXY_LIST_URL  (URL یک لیست متنی؛ می‌تواند چند URL با کاما باشد)
  3. چند منبع عمومی پیش‌فرض (رایگان — کیفیت پایین)

هر پروکسی که با موفقیت کار کند در ابتدای صف قرار می‌گیرد تا دفعه بعد
زودتر امتحان شود؛ پروکسی‌های خراب موقتاً کنار گذاشته می‌شوند.
"""
import os
import threading
import time
import urllib.request
from collections import OrderedDict
from typing import List, Optional

from bot import logs

# منابع عمومی پیش‌فرض (http proxy list). کیفیت پایین ولی رایگان.
_DEFAULT_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
]

_lock = threading.Lock()
# پروکسی‌های در دسترس: OrderedDict برای حفظ اولویت (موفق‌ها اول)
_pool: "OrderedDict[str, float]" = OrderedDict()
_last_refresh = 0.0
_REFRESH_TTL = 30 * 60  # هر ۳۰ دقیقه لیست را تازه کن
# پروکسی‌هایی که اخیراً شکست خورده‌اند: proxy -> زمان انقضای تحریم
_banned: dict[str, float] = {}
_BAN_TTL = 10 * 60  # ۱۰ دقیقه کنار گذاشتن پروکسی خراب


def _norm(p: str) -> Optional[str]:
    p = p.strip()
    if not p or p.startswith("#"):
        return None
    if "://" not in p:
        p = "http://" + p
    return p


def _fetch(url: str) -> List[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read().decode("utf-8", "ignore")
        out = []
        for line in text.splitlines():
            n = _norm(line)
            if n:
                out.append(n)
        return out
    except Exception as e:  # noqa: BLE001
        logs.warn("PROXY: دریافت لیست از %s ناموفق: %s", url, e)
        return []


def _sources() -> List[str]:
    env_url = os.environ.get("PROXY_LIST_URL", "").strip()
    if env_url:
        return [u.strip() for u in env_url.split(",") if u.strip()]
    return _DEFAULT_SOURCES


def _load_env_inline() -> List[str]:
    raw = os.environ.get("PROXY_LIST", "").strip()
    if not raw:
        return []
    parts = raw.replace("\n", ",").split(",")
    return [n for n in (_norm(p) for p in parts) if n]


def refresh(force: bool = False) -> int:
    """بارگذاری/تازه‌سازی استخر پروکسی. تعداد پروکسی‌های موجود را برمی‌گرداند."""
    global _last_refresh
    with _lock:
        now = time.time()
        if not force and _pool and (now - _last_refresh) < _REFRESH_TTL:
            return len(_pool)

        collected: List[str] = []
        collected += _load_env_inline()
        if not collected or os.environ.get("PROXY_LIST_URL"):
            for src in _sources():
                collected += _fetch(src)

        # حفظ اولویت پروکسی‌های موفق قبلی
        new_pool: "OrderedDict[str, float]" = OrderedDict()
        for p in list(_pool.keys()):  # موفق‌های قبلی اول
            if p in collected or _load_env_inline():
                new_pool[p] = _pool[p]
        for p in collected:
            if p not in new_pool:
                new_pool[p] = 0.0

        _pool.clear()
        _pool.update(new_pool)
        _last_refresh = now
        logs.info("PROXY: استخر تازه شد — %d پروکسی", len(_pool))
        return len(_pool)


def candidates(limit: int = 40) -> List[str]:
    """فهرست پروکسی‌های قابل امتحان (تحریم‌نشده)، به‌ترتیب اولویت."""
    refresh()
    now = time.time()
    with _lock:
        # پاک‌سازی تحریم‌های منقضی
        for p in [p for p, exp in _banned.items() if exp < now]:
            _banned.pop(p, None)
        out = [p for p in _pool.keys() if p not in _banned]
    return out[:limit]


def mark_good(proxy: str) -> None:
    """پروکسی موفق را به ابتدای صف منتقل کن."""
    with _lock:
        _banned.pop(proxy, None)
        _pool.pop(proxy, None)
        # درج در ابتدا
        new = OrderedDict()
        new[proxy] = time.time()
        new.update(_pool)
        _pool.clear()
        _pool.update(new)


def mark_bad(proxy: str) -> None:
    """پروکسی خراب را موقتاً تحریم کن."""
    with _lock:
        _banned[proxy] = time.time() + _BAN_TTL


def enabled() -> bool:
    """آیا استفاده از پروکسی فعال است؟ (اگر منبعی تعریف شده باشد)"""
    if os.environ.get("PROXY_LIST") or os.environ.get("PROXY_LIST_URL"):
        return True
    # منابع پیش‌فرض فقط وقتی USE_FREE_PROXIES=1 باشد فعال‌اند
    return os.environ.get("USE_FREE_PROXIES", "").strip() in ("1", "true", "yes")


def stats() -> dict:
    with _lock:
        return {"total": len(_pool), "banned": len(_banned)}
