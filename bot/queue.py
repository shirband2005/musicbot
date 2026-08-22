"""مدیریت صف پخش (با پشتیبان دیتابیس)، تاریخچه (برای آهنگ قبلی) و منطق پخش.

صف و آهنگ در حال پخش هر گروه در دیتابیس هم ذخیره می‌شود تا با ری‌استارت از بین نرود.
"""
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, fields
from typing import Deque, Dict, List, Optional

from bot import database as db


@dataclass
class Track:
    title: str
    stream_url: str
    webpage_url: str
    duration: int  # ثانیه (۰ یعنی نامشخص/زنده)
    duration_text: str
    thumbnail: Optional[str]
    requester: str  # نام درخواست‌کننده
    requester_id: int = 0  # شناسه‌ی عددی درخواست‌کننده (برای منشن قابل کلیک در پنل)
    uid: str = ""  # شناسه‌ی یکتای این آیتم صف (برای callback پرش/حذف در لیست پخش)
    is_video: bool = False
    query: str = ""  # عبارت جست‌وجوی اصلی (برای دریافت رسانه/بازپخش)
    video_id: str = ""  # شناسه ویدیوی یوتیوب (کلید کش)
    local_path: str = ""  # مسیر فایل دانلودشده‌ی محلی (برای پخش پایدار در کال)
    source: str = "youtube"  # منبع: youtube | soundcloud | telegram | telegram_stream
    # برای استریم مستقیم فایل حجیم تلگرام (بدون دانلود کامل):
    tg_chat_id: int = 0  # چتی که فایل در آن است (برای دسترسی یوزربات)
    tg_msg_id: int = 0   # آی‌دی پیام حاوی فایل
    # زمان‌بندی برای نوار پیشرفت
    started_at: float = 0.0
    elapsed_before_pause: float = 0.0
    paused: bool = False

    def mark_started(self) -> None:
        self.started_at = time.time()
        self.elapsed_before_pause = 0.0
        self.paused = False

    def mark_paused(self) -> None:
        if not self.paused:
            self.elapsed_before_pause += time.time() - self.started_at
            self.paused = True

    def mark_resumed(self) -> None:
        if self.paused:
            self.started_at = time.time()
            self.paused = False

    def position(self) -> int:
        if self.paused:
            pos = self.elapsed_before_pause
        else:
            pos = self.elapsed_before_pause + (time.time() - self.started_at)
        if self.duration:
            pos = min(pos, self.duration)
        return int(pos)

    def __post_init__(self) -> None:
        # هر Track شناسه‌ی یکتا می‌گیرد تا callback لیست پخش به شماره‌ی ردیف
        # وابسته نباشد؛ شماره‌ها با رد شدن/حذف آهنگ جابه‌جا می‌شوند و کاربر
        # ممکن است آیتم اشتباهی را پخش/حذف کند.
        if not self.uid:
            self.uid = uuid.uuid4().hex[:8]


_TRACK_FIELDS = {f.name for f in fields(Track)}


def track_from_dict(d: dict) -> Track:
    return Track(**{k: v for k, v in d.items() if k in _TRACK_FIELDS})


# صف هر گروه: chat_id -> deque[Track]
_queues: Dict[int, Deque[Track]] = {}
# آهنگ در حال پخش هر گروه
_now_playing: Dict[int, Track] = {}
# تاریخچه پخش هر گروه (برای «آهنگ قبلی»)
_history: Dict[int, List[Track]] = {}
_HISTORY_MAX = 20  # حداکثر آهنگ در تاریخچه‌ی هر گروه (جلوگیری از نشت حافظه)


def _hist_add(chat_id: int, track: Track) -> None:
    """آهنگ را به تاریخچه اضافه می‌کند و تاریخچه را به _HISTORY_MAX محدود نگه می‌دارد."""
    h = _history.setdefault(chat_id, [])
    h.append(track)
    if len(h) > _HISTORY_MAX:
        del h[: len(h) - _HISTORY_MAX]


def _persist(chat_id: int) -> None:
    """وضعیت فعلی گروه (در حال پخش + صف) را در دیتابیس ذخیره می‌کند."""
    tracks = []
    cur = _now_playing.get(chat_id)
    if cur is not None:
        tracks.append(asdict(cur))
    for t in _queues.get(chat_id, deque()):
        tracks.append(asdict(t))
    try:
        if tracks:
            db.queue_save(chat_id, tracks)
        else:
            db.queue_clear(chat_id)
    except Exception:  # noqa: BLE001
        pass


def restore_all() -> Dict[int, Track]:
    """در بوت: صف‌های ذخیره‌شده را به RAM برمی‌گرداند.

    برمی‌گرداند {chat_id: now_playing_track} برای گروه‌هایی که باید ادامه پخش دهند.
    """
    resume: Dict[int, Track] = {}
    try:
        data = db.queue_load_all()
    except Exception:  # noqa: BLE001
        return resume
    for chat_id, items in data.items():
        if not items:
            continue
        tracks = [track_from_dict(d) for d in items]
        cur = tracks[0]
        _now_playing[chat_id] = cur
        _queues[chat_id] = deque(tracks[1:])
        resume[chat_id] = cur
    return resume


def get_queue(chat_id: int) -> Deque[Track]:
    return _queues.setdefault(chat_id, deque())


def add(chat_id: int, track: Track) -> int:
    q = get_queue(chat_id)
    q.append(track)
    _persist(chat_id)
    return len(q) - 1 + (1 if chat_id in _now_playing else 0)


def set_now_playing(chat_id: int, track: Track) -> None:
    # آهنگ فعلی را به تاریخچه منتقل کن
    cur = _now_playing.get(chat_id)
    if cur is not None and cur is not track:
        _hist_add(chat_id, cur)
    _now_playing[chat_id] = track
    track.mark_started()
    _persist(chat_id)


def now_playing(chat_id: int) -> Optional[Track]:
    return _now_playing.get(chat_id)


def pop_next(chat_id: int) -> Optional[Track]:
    q = get_queue(chat_id)
    if q:
        track = q.popleft()
        set_now_playing(chat_id, track)
        return track
    # صف خالی — آهنگ فعلی هم به تاریخچه برود
    cur = _now_playing.pop(chat_id, None)
    if cur is not None:
        _hist_add(chat_id, cur)
    _persist(chat_id)
    return None


def pop_previous(chat_id: int) -> Optional[Track]:
    """آهنگ قبلی را از تاریخچه بازیابی می‌کند و آهنگ فعلی را جلوی صف می‌گذارد."""
    hist = _history.get(chat_id)
    if not hist:
        return None
    prev = hist.pop()
    cur = _now_playing.get(chat_id)
    if cur is not None:
        get_queue(chat_id).appendleft(cur)
    # تنظیم مستقیم بدون افزودن دوباره به تاریخچه
    _now_playing[chat_id] = prev
    prev.mark_started()
    _persist(chat_id)
    return prev


def clear(chat_id: int) -> None:
    _queues.pop(chat_id, None)
    _now_playing.pop(chat_id, None)
    _history.pop(chat_id, None)
    try:
        db.queue_clear(chat_id)
    except Exception:  # noqa: BLE001
        pass


def end_current(chat_id: int) -> None:
    """پایان پخش: آهنگ فعلی به تاریخچه می‌رود و صف پاک می‌شود، اما تاریخچه
    نگه داشته می‌شود تا «آهنگ قبلی» بعد از پایان صف هم کار کند."""
    cur = _now_playing.pop(chat_id, None)
    if cur is not None:
        _hist_add(chat_id, cur)
    _queues.pop(chat_id, None)
    try:
        db.queue_clear(chat_id)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- دسترسی با uid
def find(chat_id: int, uid: str) -> Optional[Track]:
    """آهنگ صف را با شناسه‌ی یکتا پیدا می‌کند (نه با شماره‌ی ردیف).

    شماره‌ی ردیف با رد شدن یا حذف آهنگ جابه‌جا می‌شود؛ اگر callback شماره را
    حمل کند، کاربر ممکن است آیتم اشتباهی را پخش/حذف کند.
    """
    if not uid:
        return None
    for t in get_queue(chat_id):
        if t.uid == uid:
            return t
    return None


def remove(chat_id: int, uid: str) -> Optional[Track]:
    """آهنگ را از صف حذف می‌کند و خودش را برمی‌گرداند (None اگر نبود)."""
    q = get_queue(chat_id)
    for i, t in enumerate(q):
        if t.uid == uid:
            del q[i]
            _persist(chat_id)
            return t
    return None


def move_to_front(chat_id: int, uid: str) -> Optional[Track]:
    """آهنگ را به ابتدای صف می‌آورد تا با «بعدی» فوراً پخش شود.

    برای «پرش» در لیست پخش: خودِ پخش را عوض نمی‌کند، فقط ترتیب صف را.
    """
    t = remove(chat_id, uid)
    if t is None:
        return None
    get_queue(chat_id).appendleft(t)
    _persist(chat_id)
    return t


def queue_len(chat_id: int) -> int:
    return len(get_queue(chat_id))


def progress_bar(position: int, duration: int, length: int = 12) -> str:
    def fmt(sec: int) -> str:
        sec = int(sec)
        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    if not duration:
        return f"🔴 زنده  {fmt(position)}"

    filled = int(length * position / duration) if duration else 0
    filled = max(0, min(length, filled))
    bar = "━" * filled + "◉" + "─" * (length - filled)
    return f"{fmt(position)} {bar} {fmt(duration)}"
