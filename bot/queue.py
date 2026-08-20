"""مدیریت صف پخش (در RAM) و منطق پخش/رد کردن آهنگ‌ها."""
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional


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
    # زمان شروع پخش واقعی (برای محاسبه نوار پیشرفت)
    started_at: float = 0.0
    # ثانیه‌های سپری‌شده پیش از آخرین resume (برای پشتیبانی از مکث)
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
        """ثانیه‌ی فعلی پخش."""
        if self.paused:
            pos = self.elapsed_before_pause
        else:
            pos = self.elapsed_before_pause + (time.time() - self.started_at)
        if self.duration:
            pos = min(pos, self.duration)
        return int(pos)


# صف هر گروه: chat_id -> deque[Track]
_queues: Dict[int, Deque[Track]] = {}
# آهنگ در حال پخش هر گروه: chat_id -> Track
_now_playing: Dict[int, Track] = {}


def get_queue(chat_id: int) -> Deque[Track]:
    return _queues.setdefault(chat_id, deque())


def add(chat_id: int, track: Track) -> int:
    """افزودن به صف؛ موقعیت در صف را برمی‌گرداند (۰ یعنی هم‌اکنون پخش می‌شود)."""
    q = get_queue(chat_id)
    q.append(track)
    return len(q) - 1 + (1 if chat_id in _now_playing else 0)


def set_now_playing(chat_id: int, track: Track) -> None:
    _now_playing[chat_id] = track
    track.mark_started()


def now_playing(chat_id: int) -> Optional[Track]:
    return _now_playing.get(chat_id)


def pop_next(chat_id: int) -> Optional[Track]:
    """آهنگ بعدی را از صف برمی‌دارد و به‌عنوان در حال پخش تنظیم می‌کند."""
    q = get_queue(chat_id)
    if q:
        track = q.popleft()
        set_now_playing(chat_id, track)
        return track
    _now_playing.pop(chat_id, None)
    return None


def clear(chat_id: int) -> None:
    _queues.pop(chat_id, None)
    _now_playing.pop(chat_id, None)


def progress_bar(position: int, duration: int, length: int = 15) -> str:
    """ساخت نوار پیشرفت متنی همراه با زمان."""
    def fmt(sec: int) -> str:
        sec = int(sec)
        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    if not duration:
        return f"🔴 زنده — {fmt(position)}"

    filled = int(length * position / duration) if duration else 0
    filled = max(0, min(length, filled))
    bar = "━" * filled + "●" + "─" * (length - filled)
    return f"{fmt(position)} {bar} {fmt(duration)}"
