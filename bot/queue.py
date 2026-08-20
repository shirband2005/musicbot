"""مدیریت صف پخش (در RAM)، تاریخچه (برای آهنگ قبلی) و منطق پخش."""
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional


@dataclass
class Track:
    title: str
    stream_url: str
    webpage_url: str
    duration: int  # ثانیه (۰ یعنی نامشخص/زنده)
    duration_text: str
    thumbnail: Optional[str]
    requester: str  # نام درخواست‌کننده
    is_video: bool = False
    query: str = ""  # عبارت جست‌وجوی اصلی (برای دریافت رسانه/بازپخش)
    video_id: str = ""  # شناسه ویدیوی یوتیوب (کلید کش)
    local_path: str = ""  # مسیر فایل دانلودشده‌ی محلی (برای پخش پایدار در کال)
    source: str = "youtube"  # منبع: youtube | soundcloud
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


# صف هر گروه: chat_id -> deque[Track]
_queues: Dict[int, Deque[Track]] = {}
# آهنگ در حال پخش هر گروه
_now_playing: Dict[int, Track] = {}
# تاریخچه پخش هر گروه (برای «آهنگ قبلی»)
_history: Dict[int, List[Track]] = {}


def get_queue(chat_id: int) -> Deque[Track]:
    return _queues.setdefault(chat_id, deque())


def add(chat_id: int, track: Track) -> int:
    q = get_queue(chat_id)
    q.append(track)
    return len(q) - 1 + (1 if chat_id in _now_playing else 0)


def set_now_playing(chat_id: int, track: Track) -> None:
    # آهنگ فعلی را به تاریخچه منتقل کن
    cur = _now_playing.get(chat_id)
    if cur is not None and cur is not track:
        _history.setdefault(chat_id, []).append(cur)
    _now_playing[chat_id] = track
    track.mark_started()


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
        _history.setdefault(chat_id, []).append(cur)
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
    return prev


def clear(chat_id: int) -> None:
    _queues.pop(chat_id, None)
    _now_playing.pop(chat_id, None)
    _history.pop(chat_id, None)


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
