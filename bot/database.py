"""دیتابیس محلی SQLite — فقط برای داده‌های ماندگار (لیست گروه‌های فعال و تنظیمات)."""
import os
import sqlite3
import threading
from typing import List

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
        """
    )
    conn.commit()


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
