"""دیتابیس محلی SQLite — فقط برای داده‌های ماندگار (لیست گروه‌های فعال و تنظیمات)."""
import os
import sqlite3
import threading
from typing import List, Optional

import config

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        # اطمینان از وجود پوشه‌ی مقصد فایل دیتابیس
        db_dir = os.path.dirname(config.DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        -- کش فایل‌های دانلودشده (برای پخش بدون دانلود دوباره)
        CREATE TABLE IF NOT EXISTS media_cache (
            video_id   TEXT PRIMARY KEY,
            path       TEXT NOT NULL,
            title      TEXT,
            duration   INTEGER,
            is_video   INTEGER DEFAULT 0,
            last_used  REAL DEFAULT 0
        );
        """
    )
    conn.commit()


# --- کش رسانه (فایل‌های دانلودشده) ---
def cache_get(video_id: str) -> Optional[dict]:
    """اطلاعات فایل کش‌شده را برمی‌گرداند (اگر باشد) و last_used را تازه می‌کند."""
    import time
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT video_id, path, title, duration, is_video FROM media_cache WHERE video_id=?",
            (video_id,),
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE media_cache SET last_used=? WHERE video_id=?", (time.time(), video_id))
        conn.commit()
        return {
            "video_id": row["video_id"],
            "path": row["path"],
            "title": row["title"],
            "duration": row["duration"],
            "is_video": bool(row["is_video"]),
        }


def cache_put(video_id: str, path: str, title: str, duration: int, is_video: bool) -> None:
    import time
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO media_cache(video_id, path, title, duration, is_video, last_used) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(video_id) DO UPDATE SET path=excluded.path, title=excluded.title, "
            "duration=excluded.duration, is_video=excluded.is_video, last_used=excluded.last_used",
            (video_id, path, title, duration, 1 if is_video else 0, time.time()),
        )
        conn.commit()


def cache_prune(keep: int = 10) -> List[str]:
    """فقط `keep` فایل اخیر (بر اساس last_used) را نگه می‌دارد.

    مسیر فایل‌هایی که باید از دیسک حذف شوند را برمی‌گرداند.
    """
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT video_id, path FROM media_cache ORDER BY last_used DESC"
        ).fetchall()
        to_delete = rows[keep:]
        paths = []
        for r in to_delete:
            conn.execute("DELETE FROM media_cache WHERE video_id=?", (r["video_id"],))
            paths.append(r["path"])
        conn.commit()
        return paths


# --- گروه‌های سرو شده ---
def add_chat(chat_id: int) -> None:
    with _lock:
        conn = _connect()
        conn.execute("INSERT OR IGNORE INTO chats(chat_id) VALUES (?)", (chat_id,))
        conn.commit()


def get_chats() -> List[int]:
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT chat_id FROM chats").fetchall()
        return [r["chat_id"] for r in rows]


# --- کاربران سرو شده ---
def add_user(user_id: int) -> None:
    with _lock:
        conn = _connect()
        conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
        conn.commit()


def get_users() -> List[int]:
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT user_id FROM users").fetchall()
        return [r["user_id"] for r in rows]


# --- تنظیمات کلید/مقدار ---
def set_setting(key: str, value: str) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()


def get_setting(key: str, default: str | None = None) -> str | None:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
