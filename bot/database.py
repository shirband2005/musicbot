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


def close() -> None:
    """اتصال دیتابیس را می‌بندد (برای جایگزینی فایل هنگام بازیابی از کانال)."""
    global _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:  # noqa: BLE001
                pass
            _conn = None


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
        -- صف پخش پایدار (برای بازیابی پس از ری‌استارت)
        CREATE TABLE IF NOT EXISTS play_queue (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id   INTEGER NOT NULL,
            pos       INTEGER NOT NULL,   -- 0 = در حال پخش، >=1 ترتیب صف
            data      TEXT NOT NULL       -- JSON از فیلدهای Track
        );
        -- کاربران ویژه (دسترسی سراسری، فقط توسط مالک)
        CREATE TABLE IF NOT EXISTS special_users (
            user_id  INTEGER PRIMARY KEY,
            name     TEXT DEFAULT '',
            added_at REAL DEFAULT 0
        );
        -- تنظیمات هر گروه (روشن/خاموش + قفل پلتفرم + ترجیح پلتفرم)
        CREATE TABLE IF NOT EXISTS group_settings (
            chat_id  INTEGER PRIMARY KEY,
            enabled  INTEGER DEFAULT 0,
            lock     TEXT DEFAULT 'none',   -- none|youtube|soundcloud
            platform TEXT DEFAULT 'both',   -- both|youtube|soundcloud (چرخش کاربر)
            mode     TEXT DEFAULT 'queue'    -- queue|repeat|random (حالت پخش)
        );
        -- آرشیو آهنگ در کانال: کلید = video_id یا کوئری نرمال‌شده
        CREATE TABLE IF NOT EXISTS channel_songs (
            key         TEXT PRIMARY KEY,   -- video_id یا 'q:'+کوئری نرمال‌شده
            file_id     TEXT NOT NULL,      -- file_id تلگرام (برای ارسال سریع)
            message_id  INTEGER,            -- شناسه پیام در کانال آرشیو
            title       TEXT,
            duration    INTEGER DEFAULT 0,
            is_video    INTEGER DEFAULT 0,
            added_at    REAL DEFAULT 0
        );
        -- اشتراک هر گروه
        CREATE TABLE IF NOT EXISTS subscriptions (
            chat_id       INTEGER PRIMARY KEY,
            tier          TEXT DEFAULT 'basic',   -- basic | pro
            expires_at    REAL DEFAULT 0,         -- 0 = دائمی، وگرنه timestamp انقضا
            buyer_id      INTEGER DEFAULT 0,
            started_at    REAL DEFAULT 0,
            last_notified REAL DEFAULT 0          -- ضد اسپم پیام تمدید
        );
        -- سفارش‌های پرداخت (همه‌ی روش‌ها)
        CREATE TABLE IF NOT EXISTS orders (
            id         TEXT PRIMARY KEY,   -- uuid
            buyer_id   INTEGER,
            chat_id    INTEGER,
            tier       TEXT,
            months     INTEGER,            -- 0 = دائمی
            amount     INTEGER,            -- مبلغ (تومان یا تعداد Stars)
            method     TEXT,               -- stars | card | crypto
            status     TEXT DEFAULT 'pending',  -- pending | paid | rejected | expired
            ref        TEXT DEFAULT '',    -- شناسه تراکنش/رسید
            created_at REAL,
            paid_at    REAL DEFAULT 0
        );
        -- تنظیمات پرداخت (key/value) — قابل ویرایش از پنل مالک
        CREATE TABLE IF NOT EXISTS pay_settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    conn.commit()
    # افزودن ستون mode به دیتابیس‌های قدیمی (اگر نبود)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(group_settings)").fetchall()]
        if "mode" not in cols:
            conn.execute("ALTER TABLE group_settings ADD COLUMN mode TEXT DEFAULT 'queue'")
            conn.commit()
    except Exception:  # noqa: BLE001
        pass
    _migrate_from_settings(conn)


def _migrate_from_settings(conn) -> None:
    """مهاجرت یک‌باره‌ی داده‌های قدیمی از جدول settings به جدول‌های اختصاصی."""
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    except Exception:  # noqa: BLE001
        return
    migrated = 0
    for r in rows:
        key = r["key"]
        val = r["value"]
        try:
            if key.startswith("special_"):
                uid = int(key.split("_", 1)[1])
                conn.execute(
                    "INSERT OR IGNORE INTO special_users(user_id, name, added_at) VALUES (?,?,0)",
                    (uid, val if val != "1" else ""),
                )
                conn.execute("DELETE FROM settings WHERE key=?", (key,))
                migrated += 1
            elif key.startswith("player_on_"):
                cid = int(key.split("player_on_", 1)[1])
                conn.execute(
                    "INSERT INTO group_settings(chat_id, enabled) VALUES (?,?) "
                    "ON CONFLICT(chat_id) DO UPDATE SET enabled=excluded.enabled",
                    (cid, 1 if val == "1" else 0),
                )
                conn.execute("DELETE FROM settings WHERE key=?", (key,))
                migrated += 1
            elif key.startswith("player_lock_"):
                cid = int(key.split("player_lock_", 1)[1])
                conn.execute(
                    "INSERT INTO group_settings(chat_id, lock) VALUES (?,?) "
                    "ON CONFLICT(chat_id) DO UPDATE SET lock=excluded.lock",
                    (cid, val),
                )
                conn.execute("DELETE FROM settings WHERE key=?", (key,))
                migrated += 1
            elif key.startswith("platform_"):
                cid = int(key.split("platform_", 1)[1])
                conn.execute(
                    "INSERT INTO group_settings(chat_id, platform) VALUES (?,?) "
                    "ON CONFLICT(chat_id) DO UPDATE SET platform=excluded.platform",
                    (cid, val),
                )
                conn.execute("DELETE FROM settings WHERE key=?", (key,))
                migrated += 1
        except (ValueError, IndexError):
            pass
    if migrated:
        conn.commit()


# --- صف پخش پایدار ---
def queue_save(chat_id: int, tracks: list) -> None:
    """کل وضعیت صف یک گروه را ذخیره می‌کند. tracks[0] = در حال پخش."""
    import json
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM play_queue WHERE chat_id=?", (chat_id,))
        for pos, t in enumerate(tracks):
            conn.execute(
                "INSERT INTO play_queue(chat_id, pos, data) VALUES (?,?,?)",
                (chat_id, pos, json.dumps(t, ensure_ascii=False)),
            )
        conn.commit()


def queue_load_all() -> dict:
    """همه صف‌های ذخیره‌شده را برمی‌گرداند: {chat_id: [track_dict, ...]}."""
    import json
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT chat_id, pos, data FROM play_queue ORDER BY chat_id, pos"
        ).fetchall()
    out: dict = {}
    for r in rows:
        try:
            out.setdefault(r["chat_id"], []).append(json.loads(r["data"]))
        except Exception:  # noqa: BLE001
            pass
    return out


def queue_clear(chat_id: int) -> None:
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM play_queue WHERE chat_id=?", (chat_id,))
        conn.commit()


# --- آرشیو آهنگ در کانال (دیتابیس بی‌نهایت) ---
def archive_get(key: str) -> Optional[dict]:
    """اطلاعات آهنگ آرشیوشده در کانال را برمی‌گرداند (اگر باشد)."""
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT key, file_id, message_id, title, duration, is_video "
            "FROM channel_songs WHERE key=?",
            (key,),
        ).fetchone()
        if not row:
            return None
        return {
            "key": row["key"],
            "file_id": row["file_id"],
            "message_id": row["message_id"],
            "title": row["title"],
            "duration": row["duration"],
            "is_video": bool(row["is_video"]),
        }


def archive_put(key: str, file_id: str, message_id: int, title: str,
                duration: int, is_video: bool) -> None:
    import time
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO channel_songs(key, file_id, message_id, title, duration, is_video, added_at) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET file_id=excluded.file_id, "
            "message_id=excluded.message_id, title=excluded.title, "
            "duration=excluded.duration, is_video=excluded.is_video",
            (key, file_id, message_id, title, duration, 1 if is_video else 0, time.time()),
        )
        conn.commit()


def archive_count() -> int:
    with _lock:
        conn = _connect()
        return conn.execute("SELECT COUNT(*) AS c FROM channel_songs").fetchone()["c"]


def archive_delete(key: str = "", message_id: int = 0) -> Optional[dict]:
    """یک آهنگ را از آرشیو حذف می‌کند (با key یا message_id). رکورد حذف‌شده یا None."""
    with _lock:
        conn = _connect()
        if message_id:
            row = conn.execute(
                "SELECT key, title, message_id FROM channel_songs WHERE message_id=?",
                (message_id,),
            ).fetchone()
        elif key:
            row = conn.execute(
                "SELECT key, title, message_id FROM channel_songs WHERE key=?",
                (key,),
            ).fetchone()
        else:
            return None
        if not row:
            return None
        conn.execute("DELETE FROM channel_songs WHERE key=?", (row["key"],))
        conn.commit()
        return {"key": row["key"], "title": row["title"], "message_id": row["message_id"]}


def archive_random(audio_only: bool = True) -> Optional[dict]:
    """یک آهنگ تصادفی از آرشیو کانال برمی‌گرداند (برای حالت پخش رندوم)."""
    with _lock:
        conn = _connect()
        sql = ("SELECT key, file_id, message_id, title, duration, is_video "
               "FROM channel_songs")
        if audio_only:
            sql += " WHERE is_video=0"
        sql += " ORDER BY RANDOM() LIMIT 1"
        row = conn.execute(sql).fetchone()
        if not row:
            return None
        return {
            "key": row["key"],
            "file_id": row["file_id"],
            "message_id": row["message_id"],
            "title": row["title"],
            "duration": row["duration"],
            "is_video": bool(row["is_video"]),
        }


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


def cache_paths() -> List[str]:
    """مسیر همه فایل‌های موجود در کش (برای محافظت هنگام پاک‌سازی یتیم‌ها)."""
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT path FROM media_cache").fetchall()
        return [r["path"] for r in rows]


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


# --- کاربران ویژه (دسترسی سراسری به ربات، فقط توسط مالک تنظیم می‌شود) ---
def add_special(user_id: int, name: str = "") -> None:
    import time
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO special_users(user_id, name, added_at) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET name=excluded.name",
            (user_id, name, time.time()),
        )
        conn.commit()


def remove_special(user_id: int) -> None:
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM special_users WHERE user_id=?", (user_id,))
        conn.commit()


def is_special(user_id: int) -> bool:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT 1 FROM special_users WHERE user_id=?", (user_id,)
        ).fetchone()
        return row is not None


def special_name(user_id: int) -> str:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT name FROM special_users WHERE user_id=?", (user_id,)
        ).fetchone()
        return row["name"] if row else ""


def list_special() -> List[int]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT user_id FROM special_users ORDER BY added_at"
        ).fetchall()
        return [r["user_id"] for r in rows]


# --- تنظیمات هر گروه (روشن/خاموش + قفل پلتفرم + ترجیح پلتفرم) ---
def group_get(chat_id: int) -> dict:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT enabled, lock, platform, mode FROM group_settings WHERE chat_id=?",
            (chat_id,),
        ).fetchone()
        if not row:
            return {"enabled": 0, "lock": "none", "platform": "both", "mode": "queue"}
        return {"enabled": row["enabled"], "lock": row["lock"],
                "platform": row["platform"], "mode": row["mode"] or "queue"}


def group_set(chat_id: int, **fields) -> None:
    """به‌روزرسانی یک یا چند فیلد تنظیماتِ گروه (enabled/lock/platform/mode)."""
    allowed = {"enabled", "lock", "platform", "mode"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO group_settings(chat_id) VALUES (?) ON CONFLICT(chat_id) DO NOTHING",
            (chat_id,),
        )
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(
            f"UPDATE group_settings SET {sets} WHERE chat_id=?",
            (*fields.values(), chat_id),
        )
        conn.commit()


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


# --- اشتراک گروه‌ها ---
def sub_get(chat_id: int) -> Optional[dict]:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT chat_id, tier, expires_at, buyer_id, started_at, last_notified "
            "FROM subscriptions WHERE chat_id=?", (chat_id,),
        ).fetchone()
        if not row:
            return None
        return dict(row)


def sub_set(chat_id: int, **fields) -> None:
    allowed = {"tier", "expires_at", "buyer_id", "started_at", "last_notified"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO subscriptions(chat_id) VALUES (?) ON CONFLICT(chat_id) DO NOTHING",
            (chat_id,),
        )
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE subscriptions SET {sets} WHERE chat_id=?",
                     (*fields.values(), chat_id))
        conn.commit()


def sub_delete(chat_id: int) -> None:
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM subscriptions WHERE chat_id=?", (chat_id,))
        conn.commit()


def sub_all() -> list:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT chat_id, tier, expires_at, buyer_id, started_at, last_notified "
            "FROM subscriptions ORDER BY expires_at"
        ).fetchall()
        return [dict(r) for r in rows]


def sub_expired(now_ts: float) -> list:
    """اشتراک‌های منقضی‌شده (expires_at>0 و < now) برای زمان‌بند."""
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT chat_id, tier, expires_at, buyer_id, last_notified "
            "FROM subscriptions WHERE expires_at>0 AND expires_at<?", (now_ts,),
        ).fetchall()
        return [dict(r) for r in rows]


# --- سفارش‌های پرداخت ---
def order_create(oid: str, buyer_id: int, chat_id: int, tier: str, months: int,
                 amount: int, method: str) -> None:
    import time
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO orders(id, buyer_id, chat_id, tier, months, amount, method, "
            "status, created_at) VALUES (?,?,?,?,?,?,?, 'pending', ?)",
            (oid, buyer_id, chat_id, tier, months, amount, method, time.time()),
        )
        conn.commit()


def order_get(oid: str) -> Optional[dict]:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        return dict(row) if row else None


def order_set_status(oid: str, status: str, ref: str = "") -> None:
    import time
    with _lock:
        conn = _connect()
        paid = time.time() if status == "paid" else 0
        conn.execute(
            "UPDATE orders SET status=?, ref=?, paid_at=? WHERE id=?",
            (status, ref, paid, oid),
        )
        conn.commit()


def orders_pending() -> list:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM orders WHERE status='pending' ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        return [dict(r) for r in rows]


# --- تنظیمات پرداخت (key/value) ---
def pay_get(key: str, default: str = "") -> str:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT value FROM pay_settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def pay_set(key: str, value: str) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO pay_settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        conn.commit()
