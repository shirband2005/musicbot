"""استخر پروکسی چرخشی (فقط پروکسی‌های باکیفیت با احراز هویت — Webshare).

پروکسی‌ها از منابع زیر خوانده می‌شوند (به‌ترتیب اولویت):
  1. متغیر محیطی PROXY_LIST      (خطوط ip:port:user:pass یا http://user:pass@ip:port)
  2. متغیر محیطی PROXY_LIST_URL  (URL یک لیست متنی)
  3. لیست پیش‌فرض تعبیه‌شده (_BUILTIN) — همان ۱۰ پروکسی Webshare

پروکسی موفق ابتدای صف می‌رود؛ پروکسی خراب موقتاً تحریم می‌شود.
پروکسی‌های عمومی رایگان حذف شده‌اند (همه ۴۰۷/کند بودند).
"""
import os
import threading
import time
import urllib.request
from collections import OrderedDict
from typing import List, Optional

from bot import logs

# --- لیست پیش‌فرض تعبیه‌شده: ۱۰ پروکسی Webshare (ip:port:user:pass) ---
# در صورت نیاز به تعویض، متغیر محیطی PROXY_LIST را ست کن (این لیست را override می‌کند).
_BUILTIN = [
    "0.0.0.0:6754:REDACTED:REDACTED",
    "0.0.0.0:7684:REDACTED:REDACTED",
    "0.0.0.0:6014:REDACTED:REDACTED",
    "0.0.0.0:6462:REDACTED:REDACTED",
    "0.0.0.0:6641:REDACTED:REDACTED",
    "0.0.0.0:6361:REDACTED:REDACTED",
    "0.0.0.0:6370:REDACTED:REDACTED",
    "0.0.0.0:6095:REDACTED:REDACTED",
    "0.0.0.0:5611:REDACTED:REDACTED",
    "0.0.0.0:6185:REDACTED:REDACTED",
]

_lock = threading.Lock()
# پروکسی‌های در دسترس: OrderedDict برای حفظ اولویت (موفق‌ها اول)
_pool: "OrderedDict[str, float]" = OrderedDict()
_last_refresh = 0.0
_REFRESH_TTL = 30 * 60  # هر ۳۰ دقیقه لیست را تازه کن
# پروکسی‌هایی که اخیراً شکست خورده‌اند: proxy -> زمان انقضای تحریم
_banned: dict[str, float] = {}
_BAN_TTL = 5 * 60  # ۵ دقیقه کنار گذاشتن پروکسی خراب


def _norm(p: str) -> Optional[str]:
    p = p.strip()
    if not p or p.startswith("#"):
        return None
    # فرمت Webshare: ip:port:user:pass  →  http://user:pass@ip:port
    if "://" not in p and p.count(":") == 3:
        ip, port, user, pw = p.split(":")
        return f"http://{user}:{pw}@{ip}:{port}"
    if "://" not in p:
        p = "http://" + p
    return p


def _parse_lines(text: str) -> List[str]:
    out = []
    for line in text.replace(",", "\n").splitlines():
        n = _norm(line)
        if n:
            out.append(n)
    return out


def _fetch_url(url: str) -> List[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return _parse_lines(r.read().decode("utf-8", "ignore"))
    except Exception as e:  # noqa: BLE001
        logs.warn("PROXY: دریافت لیست از %s ناموفق: %s", url, e)
        return []


def _collect() -> List[str]:
    """جمع‌آوری پروکسی‌ها از env یا لیست تعبیه‌شده."""
    raw = os.environ.get("PROXY_LIST", "").strip()
    if raw:
        return _parse_lines(raw)
    url = os.environ.get("PROXY_LIST_URL", "").strip()
    if url:
        found = []
        for u in url.split(","):
            if u.strip():
                found += _fetch_url(u.strip())
        if found:
            return found
    return _parse_lines("\n".join(_BUILTIN))


def refresh(force: bool = False) -> int:
    """بارگذاری/تازه‌سازی استخر پروکسی. تعداد پروکسی‌های موجود را برمی‌گرداند."""
    global _last_refresh
    with _lock:
        now = time.time()
        if not force and _pool and (now - _last_refresh) < _REFRESH_TTL:
            return len(_pool)

        collected = _collect()
        new_pool: "OrderedDict[str, float]" = OrderedDict()
        # حفظ اولویت پروکسی‌های موفق قبلی که هنوز در لیست‌اند
        for p in list(_pool.keys()):
            if p in collected:
                new_pool[p] = _pool[p]
        for p in collected:
            if p not in new_pool:
                new_pool[p] = 0.0

        _pool.clear()
        _pool.update(new_pool)
        _last_refresh = now
        logs.info("PROXY: استخر تازه شد — %d پروکسی (Webshare)", len(_pool))
        return len(_pool)


def candidates(limit: int = 40) -> List[str]:
    """فهرست پروکسی‌های قابل امتحان (تحریم‌نشده)، به‌ترتیب اولویت."""
    refresh()
    now = time.time()
    with _lock:
        for p in [p for p, exp in _banned.items() if exp < now]:
            _banned.pop(p, None)
        out = [p for p in _pool.keys() if p not in _banned]
    return out[:limit]


def mark_good(proxy: str) -> None:
    """پروکسی موفق را به ابتدای صف منتقل کن."""
    with _lock:
        _banned.pop(proxy, None)
        _pool.pop(proxy, None)
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
    """آیا استفاده از پروکسی فعال است؟

    پیش‌فرض: روشن (چون لیست Webshare تعبیه‌شده داریم).
    برای خاموش‌کردن: USE_PROXIES=0
    """
    flag = os.environ.get("USE_PROXIES", "1").strip().lower()
    return flag in ("1", "true", "yes", "on")


def stats() -> dict:
    with _lock:
        return {"total": len(_pool), "banned": len(_banned)}
