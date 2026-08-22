"""تست‌های بازنویسی کانال لاگ و کانال دیتابیس."""
import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    dbfile = tmp_path / "ch.db"
    monkeypatch.setenv("DB_PATH", str(dbfile))
    import importlib
    import config
    importlib.reload(config)
    from bot import database as db
    importlib.reload(db)
    db._conn = None
    yield db


def labels(kb):
    return [[b.text for b in r] for r in kb.inline_keyboard]


def cbs(kb):
    return [b.callback_data for r in kb.inline_keyboard for b in r
            if b.callback_data]


def check_entities(text, ents):
    total = len(text.encode("utf-16-le")) // 2
    for e in ents:
        assert e.offset >= 0 and e.offset + e.length <= total, e.type


# ================================================================ کمکی‌ها
def test_size_and_duration_text():
    from bot import channel_ui as cui

    assert cui.size_text(0) == "—"
    assert "کیلوبایت" in cui.size_text(500 * 1024)
    assert "مگابایت" in cui.size_text(5 * 1024 * 1024)

    assert cui.dur_text(0) == "—"
    assert cui.dur_text(75) == "1:15"
    assert cui.dur_text(3725) == "1:02:05"


def test_source_labels_are_persian():
    from bot import channel_ui as cui

    assert cui.source_text("youtube") == "یوتیوب"
    assert cui.source_text("soundcloud") == "ساوندکلاد"
    assert cui.source_text("forward") == "فوروارد مالک"
    assert cui.source_text("") == "—"


def test_media_title_strips_extension():
    from bot import channel

    class M:
        performer = "شادمهر"
        title = ""
        file_name = "Shadmehr - Divaneh.mp3"

    title, performer = channel.media_title(M())
    assert title == "Shadmehr - Divaneh"
    assert performer == "شادمهر"


def test_full_title_avoids_duplicate_performer():
    from bot import channel

    assert channel.full_title("دیوانه", "شادمهر") == "شادمهر - دیوانه"
    # اگر خواننده در عنوان باشد، تکرار نشود
    assert channel.full_title("شادمهر - دیوانه", "شادمهر") == "شادمهر - دیوانه"


# ================================================================ کپشن آهنگ
def test_song_caption_is_complete():
    """نسخه‌ی قبلی فقط «🎵 {title}» بود — بدون مدت، منبع، حجم، خواننده."""
    from bot import channel_ui as cui

    text, ents = cui.song_caption(
        "شادمهر عقیلی — دیوانه", performer="شادمهر عقیلی", duration=252,
        file_size=4 * 1024 * 1024, source="youtube",
        url="https://youtu.be/abc123", n_total=42)
    for field in ("خواننده", "مدت", "حجم", "منبع", "لینک", "شماره در دیتابیس"):
        assert field in text, field
    assert "۴:۱۲" in text
    assert "یوتیوب" in text
    assert "۴۲" in text
    check_entities(text, ents)


def test_song_caption_minimal_fields():
    from bot import channel_ui as cui

    text, ents = cui.song_caption("آهنگ بی‌نام")
    assert "مدت" in text and "حجم" in text
    assert "لینک" not in text            # لینک نداشت، فیلد خالی نساخته
    check_entities(text, ents)


def test_song_keyboard_has_delete_button():
    from bot import channel_ui as cui
    from bot import ui

    kb = cui.song_keyboard("abc123")
    assert labels(kb) == [["حذف از دیتابیس"]]
    assert cbs(kb) == ["arch|del|abc123"]
    assert str(kb.inline_keyboard[0][0].style) == str(ui.RED)


def test_confirm_keyboard_two_step():
    """حذف تأیید دومرحله‌ای دارد تا کلیک اشتباه آهنگ را پاک نکند."""
    from bot import channel_ui as cui

    kb = cui.confirm_keyboard("abc123")
    assert labels(kb) == [["بله، حذف کن", "انصراف"]]
    assert cbs(kb) == ["arch|yes|abc123", "arch|no|abc123"]


def test_long_key_is_shortened_for_callback():
    """callback_data سقف ۶۴ بایت دارد؛ کلید بلند هش می‌شود."""
    from bot import channel_ui as cui

    long_key = "q:" + ("آهنگ فارسی با اسم خیلی خیلی طولانی " * 3)
    kb = cui.song_keyboard(long_key)
    cb = cbs(kb)[0]
    assert len(cb.encode()) <= 64
    assert cb.startswith("arch|del|h:")


def test_short_key_passes_through():
    from bot import channel_ui as cui

    assert cui._short("dQw4w9WgXcQ") == "dQw4w9WgXcQ"


# ================================================================ دیتابیس
def test_archive_put_stores_full_info(fresh_db):
    fresh_db.archive_put("vid1", "FILEID", 555, "شادمهر - دیوانه", 252, False,
                         performer="شادمهر", file_size=4194304,
                         source="youtube", added_by=42,
                         url="https://youtu.be/vid1")
    rec = fresh_db.archive_get("vid1")
    assert rec["performer"] == "شادمهر"
    assert rec["file_size"] == 4194304
    assert rec["source"] == "youtube"
    assert rec["added_by"] == 42
    assert rec["url"] == "https://youtu.be/vid1"
    assert rec["added_at"] > 0


def test_archive_by_message(fresh_db):
    fresh_db.archive_put("vid2", "F", 777, "آهنگ", 100, False, source="forward")
    rec = fresh_db.archive_by_message(777)
    assert rec and rec["key"] == "vid2"
    assert rec["source"] == "forward"
    assert fresh_db.archive_by_message(999) is None
    assert fresh_db.archive_by_message(0) is None


def test_archive_by_short_handles_hash(fresh_db):
    import hashlib
    from bot import channel_ui as cui

    long_key = "q:" + ("خیلی طولانی " * 8)
    fresh_db.archive_put(long_key, "F", 888, "آهنگ بلند", 100, False)
    short = cui._short(long_key)
    assert short.startswith("h:")
    rec = fresh_db.archive_by_short(short)
    assert rec and rec["key"] == long_key

    # کلید کوتاه هم باید کار کند
    fresh_db.archive_put("vid3", "F", 889, "آهنگ", 100, False)
    assert fresh_db.archive_by_short("vid3")["key"] == "vid3"
    assert fresh_db.archive_by_short("") is None


def test_archive_delete_returns_full_record(fresh_db):
    fresh_db.archive_put("vid4", "F", 900, "آهنگ حذفی", 120, False,
                         performer="خواننده", source="youtube")
    rec = fresh_db.archive_delete(message_id=900)
    assert rec["title"] == "آهنگ حذفی"
    assert rec["performer"] == "خواننده"
    assert rec["source"] == "youtube"
    assert fresh_db.archive_get("vid4") is None


def test_archive_random_includes_new_fields(fresh_db):
    fresh_db.archive_put("vid5", "F", 901, "آهنگ", 100, False,
                         performer="خواننده", source="soundcloud")
    rec = fresh_db.archive_random()
    assert rec["performer"] == "خواننده"
    assert rec["source"] == "soundcloud"


def test_old_db_without_new_columns_still_works(tmp_path, monkeypatch):
    """دیتابیس قدیمی بدون ستون‌های جدید نباید بشکند (مهاجرت ایمن)."""
    import sqlite3

    dbfile = tmp_path / "old.db"
    conn = sqlite3.connect(str(dbfile))
    conn.execute("""CREATE TABLE channel_songs (
        key TEXT PRIMARY KEY, file_id TEXT NOT NULL, message_id INTEGER,
        title TEXT, duration INTEGER DEFAULT 0, is_video INTEGER DEFAULT 0,
        added_at REAL DEFAULT 0)""")
    conn.execute("INSERT INTO channel_songs VALUES ('k','f',1,'t',10,0,0)")
    conn.commit()
    conn.close()

    monkeypatch.setenv("DB_PATH", str(dbfile))
    import importlib
    import config
    importlib.reload(config)
    from bot import database as db
    importlib.reload(db)
    db._conn = None

    rec = db.archive_get("k")
    assert rec["title"] == "t"
    assert rec["performer"] == ""       # ستون جدید با پیش‌فرض
    assert rec["source"] == ""


# ================================================================ پیام‌های لاگ
def test_log_messages_use_ui_layer():
    """پیام‌های لاگ باید entities داشته باشند، نه **Markdown**."""
    from bot import channel_ui as cui

    payloads = [
        cui.bot_started("Ablhermesbot", 5, 120),
        cui.bot_stopped(),
        cui.now_playing("آهنگ", "youtube", "گروه", "AB°L", 8406519786),
        cui.group_added("گروه جدید", -100111, "AB°L", 8406519786),
        cui.group_removed("گروه", -100111),
        cui.sub_activated("گروه", -100111, 2, "کارت به کارت", "۶۰ روز مانده"),
        cui.sub_rejected("گروه", -100111, "oid123"),
        cui.sub_expired("گروه", -100111),
        cui.free_access_ended("گروه", -100111),
        cui.backup_caption(120, 5),
        cui.restore_blob_caption(),
        cui.song_deleted("آهنگ", 119),
        cui.song_added_log("آهنگ", "forward", 121),
        cui.forward_processing("آهنگ"),
    ]
    assert len(payloads) == 14
    for text, ents in payloads:
        assert "**" not in text          # هیچ Markdown خامی نماند
        assert "•" not in text           # بولت قدیمی جایش را به فلش داد
        check_entities(text, ents)


def test_now_playing_mentions_requester():
    from bot import channel_ui as cui

    text, ents = cui.now_playing("آهنگ", "youtube", "گروه", "AB°L", 8406519786)
    assert any(e.type.name == "TEXT_MENTION" for e in ents)

    # بدون شناسه، منشن نساز
    text, ents = cui.now_playing("آهنگ", "youtube", "گروه", "AB°L", 0)
    assert not any(e.type.name == "TEXT_MENTION" for e in ents)


def test_subscription_log_events_exist():
    """رویدادهای اشتراک قبلاً هیچ‌جا لاگ نمی‌شدند."""
    from bot import channel_ui as cui

    text, _e = cui.sub_activated("گروه من", -100111, 3, "استارز", "۹۰ روز مانده")
    assert "اشتراک فعال شد" in text
    assert "۳ ماه" in text
    assert "استارز" in text

    text, _e = cui.sub_expired("گروه من", -100111)
    assert "منقضی" in text
    assert "خاموش شد" in text


def test_log_accepts_entities_signature():
    """channel.log باید (text, entities) بپذیرد تا با *payload کار کند."""
    import inspect

    from bot import channel

    params = list(inspect.signature(channel.log).parameters)
    assert params[:2] == ["text", "entities"]


def test_no_markdown_left_in_channel_code():
    """هیچ پیام لاگی نباید با **bold** خام فرستاده شود."""
    for path in ("/opt/data/musicbot/bot/channel.py",
                 "/opt/data/musicbot/bot/plugins/events.py",
                 "/opt/data/musicbot/main.py"):
        src = open(path, encoding="utf-8").read()
        assert "**ربات روشن شد**" not in src
        assert "**پخش جدید**" not in src
        assert "• آهنگ:" not in src
