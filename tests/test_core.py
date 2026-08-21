"""تست‌های خودکار موزیک‌بات — بدون نیاز به اتصال تلگرام.

اجرا:  pytest -q
تمرکز روی منطق خالص: دیتابیس، صف پایدار، دسترسی، تنظیمات گروه، قفل پلتفرم،
فیلتر دستور فارسی، رنگ‌بندی پنل، طول entity ایموجی.
"""
import os

import pytest

# محیط لازم پیش از import هر ماژول ربات
os.environ.setdefault("API_ID", "1")
os.environ.setdefault("API_HASH", "x")
os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("STRING_SESSION", "x")
os.environ.setdefault("OWNER_ID", "8406519786")


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """برای هر تست یک دیتابیس تازه بساز."""
    dbfile = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(dbfile))
    import importlib
    import config
    importlib.reload(config)
    from bot import database as db
    importlib.reload(db)
    # اتصال داخلی را ریست کن
    db._conn = None
    yield db


# ---------------- دیتابیس: کاربران ویژه ----------------
def test_special_users_crud(fresh_db):
    db = fresh_db
    assert db.is_special(111) is False
    db.add_special(111, "Ali")
    assert db.is_special(111) is True
    assert db.special_name(111) == "Ali"
    assert db.list_special() == [111]
    db.remove_special(111)
    assert db.is_special(111) is False
    assert db.list_special() == []


# ---------------- دیتابیس: تنظیمات گروه ----------------
def test_group_settings_defaults_and_update(fresh_db):
    db = fresh_db
    d = db.group_get(-100)
    assert d == {"enabled": 0, "lock": "none", "platform": "both", "mode": "queue"}
    db.group_set(-100, enabled=1)
    assert db.group_get(-100)["enabled"] == 1
    db.group_set(-100, lock="youtube", platform="youtube")
    d = db.group_get(-100)
    assert d["lock"] == "youtube" and d["platform"] == "youtube"
    # enabled باید حفظ شود (به‌روزرسانی جزئی)
    assert d["enabled"] == 1


# ---------------- group_config ----------------
def test_group_config_enable_and_lock(fresh_db):
    from bot import group_config as gc
    cid = -200
    assert gc.is_enabled(cid) is False  # پیش‌فرض خاموش
    gc.set_enabled(cid, True)
    assert gc.is_enabled(cid) is True
    assert gc.get_lock(cid) == gc.LOCK_NONE
    assert gc.is_locked(cid) is False
    gc.set_lock(cid, gc.LOCK_SOUNDCLOUD)
    assert gc.get_lock(cid) == gc.LOCK_SOUNDCLOUD
    assert gc.is_locked(cid) is True


# ---------------- platform_pref: چرخش + قفل مؤثر ----------------
def test_platform_cycle_and_effective_lock(fresh_db):
    from bot import platform_pref as pp
    from bot import group_config as gc
    cid = -300
    assert pp.get(cid) == pp.BOTH
    assert pp.cycle(cid) == pp.YOUTUBE
    assert pp.cycle(cid) == pp.SOUNDCLOUD
    assert pp.cycle(cid) == pp.BOTH  # چرخش کامل
    # قفل باید انتخاب کاربر را override کند
    gc.set_lock(cid, gc.LOCK_YOUTUBE)
    assert pp.effective(cid) == pp.YOUTUBE
    gc.set_lock(cid, gc.LOCK_SOUNDCLOUD)
    assert pp.effective(cid) == pp.SOUNDCLOUD
    gc.set_lock(cid, gc.LOCK_NONE)
    pp.cycle(cid)  # به youtube
    assert pp.effective(cid) == pp.get(cid)


# ---------------- صف پخش پایدار ----------------
def test_queue_persist_and_restore(fresh_db):
    from bot import queue as q
    from bot.queue import Track
    cid = -400
    t1 = Track(title="A", stream_url="u1", webpage_url="", duration=100,
               duration_text="1:40", thumbnail=None, requester="me",
               source="youtube", local_path="/tmp/a.mp3", video_id="vid1")
    t2 = Track(title="B", stream_url="u2", webpage_url="", duration=50,
               duration_text="0:50", thumbnail=None, requester="me",
               source="soundcloud", query="B song")
    q.set_now_playing(cid, t1)
    q.add(cid, t2)
    # شبیه‌سازی ری‌استارت
    q._now_playing.clear()
    q._queues.clear()
    q._history.clear()
    resume = q.restore_all()
    assert cid in resume
    assert resume[cid].title == "A"
    assert resume[cid].source == "youtube"
    assert resume[cid].local_path == "/tmp/a.mp3"
    assert resume[cid].video_id == "vid1"
    rest = list(q.get_queue(cid))
    assert len(rest) == 1 and rest[0].title == "B"
    assert rest[0].source == "soundcloud" and rest[0].query == "B song"


def test_queue_clear_wipes_db(fresh_db):
    from bot import queue as q
    from bot.queue import Track
    cid = -401
    t = Track(title="X", stream_url="u", webpage_url="", duration=10,
              duration_text="0:10", thumbnail=None, requester="me")
    q.set_now_playing(cid, t)
    q.clear(cid)
    q._now_playing.clear(); q._queues.clear()
    assert cid not in q.restore_all()


def test_previous_history(fresh_db):
    from bot import queue as q
    from bot.queue import Track
    cid = -402
    a = Track(title="A", stream_url="u", webpage_url="", duration=10,
              duration_text="0:10", thumbnail=None, requester="me")
    b = Track(title="B", stream_url="u", webpage_url="", duration=10,
              duration_text="0:10", thumbnail=None, requester="me")
    q.set_now_playing(cid, a)
    q.set_now_playing(cid, b)  # a به تاریخچه رفت
    prev = q.pop_previous(cid)
    assert prev is not None and prev.title == "A"


# ---------------- فیلتر دستور فارسی ----------------
@pytest.mark.asyncio
async def test_fa_command_matches_and_normalizes(fresh_db):
    from bot.facmd import fa_command, normalize
    assert normalize("آهنگ") == "اهنگ"
    assert normalize("كتاب") == "کتاب"

    f = fa_command(["پخش اهنگ"])

    class M:
        def __init__(self, t):
            self.text = t
            self.caption = None
            self.command = None

    m = M("پخش آهنگ مرا ببوس")  # با «آ» — باید نرمال شده مطابقت کند
    assert await f(None, m) is True
    assert m.command[0] == "پخش اهنگ"
    assert m.command[1:] == ["مرا", "ببوس"]

    m2 = M("چیز دیگری")
    assert await f(None, m2) is False


# ---------------- رنگ‌بندی پنل مدیریت ----------------
def test_admin_panel_colors(fresh_db):
    from pyrogram import enums
    from bot import group_config as gc
    from bot.plugins.admin_panel import _panel
    cid = -500

    def styles(kb):
        return [[b.style for b in row] for row in kb.inline_keyboard]

    # پیش‌فرض: خاموش → «روشن» قرمز، «خاموش» سبز
    _, kb = _panel(cid)
    row0 = kb.inline_keyboard[0]
    assert row0[0].text == "روشن" and row0[0].style == enums.ButtonStyle.DANGER
    assert row0[1].text == "خاموش" and row0[1].style == enums.ButtonStyle.SUCCESS

    # روشن + قفل ساوندکلاد
    gc.set_enabled(cid, True)
    gc.set_lock(cid, gc.LOCK_SOUNDCLOUD)
    _, kb = _panel(cid)
    labels = {b.text: b.style for row in kb.inline_keyboard for b in row}
    assert labels["روشن"] == enums.ButtonStyle.SUCCESS
    assert labels["خاموش"] == enums.ButtonStyle.DANGER
    assert labels["ساوندکلاد"] == enums.ButtonStyle.SUCCESS
    assert labels["یوتیوب"] == enums.ButtonStyle.DANGER
    assert labels["انتخاب پلتفرم"] == enums.ButtonStyle.PRIMARY  # نمایشی، آبی


# ---------------- دکمه پلتفرم در پنل پخش بسته به قفل ----------------
def test_playback_panel_platform_button_visibility(fresh_db):
    from bot import group_config as gc
    from bot import panel
    from bot.queue import Track
    cid = -600
    t = Track(title="x", stream_url="u", webpage_url="w", duration=100,
              duration_text="1:40", thumbnail=None, requester="me")
    t.mark_started()
    # قفل نشده → دکمه پلتفرم هست
    gc.set_lock(cid, gc.LOCK_NONE)
    kb = panel.panel_keyboard(cid, t, 90, False)
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert any("پلتفرم" in x for x in labels)
    # قفل یوتیوب → دکمه پلتفرم نیست
    gc.set_lock(cid, gc.LOCK_YOUTUBE)
    kb = panel.panel_keyboard(cid, t, 90, False)
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert not any("پلتفرم" in x for x in labels)


# ---------------- طول entity ایموجی پرمیوم (UTF-16) ----------------
def test_panel_entities_utf16_bounds(fresh_db):
    from bot import panel
    from bot.queue import Track
    t = Track(title="🎵 Test 🎬", stream_url="u", webpage_url="w", duration=100,
              duration_text="1:40", thumbnail=None, requester="AB°L")
    t.mark_started()
    text = panel.panel_text(t, 100, False)
    ents = panel.panel_entities(t, 100, False)
    total_u16 = len(text.encode("utf-16-le")) // 2
    for e in ents:
        # هر entity باید داخل مرز متن (بر حسب UTF-16) باشد
        assert e.offset >= 0
        assert e.offset + e.length <= total_u16


# ---------------- آرشیو کانال ----------------
def test_archive_crud(fresh_db):
    db = fresh_db
    assert db.archive_get("vidX") is None
    assert db.archive_count() == 0
    db.archive_put("vidX", "FILEID123", 42, "Song X", 180, False)
    rec = db.archive_get("vidX")
    assert rec is not None
    assert rec["file_id"] == "FILEID123"
    assert rec["message_id"] == 42
    assert rec["title"] == "Song X"
    assert rec["is_video"] is False
    assert db.archive_count() == 1
    db.archive_put("vidX", "NEWFILE", 43, "Song X", 180, False)
    assert db.archive_get("vidX")["file_id"] == "NEWFILE"
    assert db.archive_count() == 1


def test_channel_norm_key(fresh_db):
    import importlib
    from bot import channel
    importlib.reload(channel)
    assert channel._norm_key("abc123", "هر چیزی") == "abc123"
    k = channel._norm_key("", "آهنگ Test")
    assert k.startswith("q:")
    assert "اهنگ" in k


# ---------------- حالت پخش گروه (mode: queue/repeat/random) ----------------
def test_group_mode(fresh_db):
    import bot.group_config as gc
    import importlib
    importlib.reload(gc)
    cid = -100777
    # پیش‌فرض queue
    assert gc.get_mode(cid) == gc.MODE_QUEUE
    gc.set_mode(cid, gc.MODE_RANDOM)
    assert gc.get_mode(cid) == gc.MODE_RANDOM
    gc.set_mode(cid, gc.MODE_REPEAT)
    assert gc.get_mode(cid) == gc.MODE_REPEAT
    # مقدار نامعتبر نادیده گرفته می‌شود
    gc.set_mode(cid, "bogus")
    assert gc.get_mode(cid) == gc.MODE_REPEAT


def test_archive_random(fresh_db):
    db = fresh_db
    assert db.archive_random() is None
    db.archive_put("q:song one", "fid1", 11, "One", 100, False)
    db.archive_put("q:song two", "fid2", 12, "Two", 120, False)
    db.archive_put("vidX", "fidV", 13, "Vid", 200, True)  # ویدیو
    r = db.archive_random(audio_only=True)
    assert r is not None and r["is_video"] is False  # فقط صوتی


def test_history_capped(fresh_db):
    """تاریخچه‌ی پخش نباید بی‌نهایت رشد کند (جلوگیری از نشت حافظه)."""
    from bot import queue as q
    cid = -100888

    def mk(i):
        return q.Track(title=f"t{i}", stream_url="x", webpage_url="", duration=1,
                       duration_text="0:01", thumbnail=None, requester="a")
    # ۵۰ آهنگ پشت‌سرهم پخش کن
    for i in range(50):
        q.set_now_playing(cid, mk(i))
    assert len(q._history.get(cid, [])) <= q._HISTORY_MAX


def test_subscription_activate_and_expire(fresh_db):
    """فعال‌سازی، تیر، انقضا و تمدید اشتراک."""
    from bot import subscription as sub
    cid = -100555
    assert sub.is_active(cid) is False
    # فعال‌سازی ۱ ماهه پایه
    exp = sub.activate(cid, sub.TIER_BASIC, 1, buyer_id=42)
    assert exp > 0 and sub.is_active(cid) is True
    assert sub.get_tier(cid) == sub.TIER_BASIC
    assert sub.is_pro(cid) is False
    # ارتقا به دائمی حرفه‌ای
    exp2 = sub.activate(cid, sub.TIER_PRO, 0, buyer_id=42)
    assert exp2 == 0 and sub.is_pro(cid) is True
    # لغو
    sub.deactivate(cid)
    assert sub.is_active(cid) is False


def test_pay_settings_and_prices(fresh_db):
    """قیمت‌ها و تنظیمات پرداخت قابل ذخیره/بازیابی‌اند."""
    from bot import subscription as sub
    from bot import database as db
    # پیش‌فرض
    assert sub.get_price(sub.TIER_PRO, 1, "stars") > 0
    # override
    sub.set_price(sub.TIER_PRO, 1, "stars", 999)
    assert sub.get_price(sub.TIER_PRO, 1, "stars") == 999
    db.pay_set("card_number", "6037-xxxx")
    assert db.pay_get("card_number") == "6037-xxxx"


def test_orders_flow(fresh_db):
    """ساخت سفارش، تغییر وضعیت، لیست pending."""
    from bot import database as db
    db.order_create("abc123", 42, -100, "pro", 3, 250, "stars")
    o = db.order_get("abc123")
    assert o and o["status"] == "pending"
    assert len(db.orders_pending()) == 1
    db.order_set_status("abc123", "paid", ref="charge_1")
    assert db.order_get("abc123")["status"] == "paid"
    assert len(db.orders_pending()) == 0


def test_txid_reuse_guard(fresh_db):
    """یک TxID کریپتو نباید دوبار برای سفارش‌های مختلف paid شود."""
    from bot import database as db
    db.order_create("o1", 1, -1, "pro", 1, 100, "crypto")
    db.order_set_status("o1", "paid", ref="TX_ABC")
    paid = db.orders_all_paid()
    assert any(o["ref"] == "TX_ABC" for o in paid)


def test_usdt_conversion():
    """تبدیل تومان به USDT با نرخ."""
    from bot import crypto_verify as cv
    from decimal import Decimal
    assert cv.toman_to_usdt(100000, 100000) == Decimal("1.00")
    assert cv.toman_to_usdt(250000, 100000) == Decimal("2.50")
    assert cv.toman_to_usdt(100000, 0) == Decimal("0")


def test_gift_codes(fresh_db):
    """ساخت، اعتبارسنجی، مصرف و اتمام ظرفیت کد هدیه."""
    from bot import database as db
    db.gift_create("NOWRUZ", "pro", 1, max_uses=2)
    g = db.gift_get("NOWRUZ")
    assert g and g["tier"] == "pro" and g["max_uses"] == 2
    assert db.gift_redeem("NOWRUZ") is True   # استفاده ۱
    assert db.gift_redeem("NOWRUZ") is True   # استفاده ۲
    assert db.gift_redeem("NOWRUZ") is False  # ظرفیت تمام
    assert db.gift_redeem("UNKNOWN") is False  # کد ناموجود


# ---------------- migration از settings قدیمی ----------------
def test_migration_from_settings(tmp_path, monkeypatch):
    import sqlite3
    dbfile = tmp_path / "legacy.db"
    # ساخت دیتابیس قدیمی با کلیدهای settings
    conn = sqlite3.connect(dbfile)
    conn.executescript(
        "CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);"
        "INSERT INTO settings VALUES('special_777','Reza');"
        "INSERT INTO settings VALUES('player_on_-100','1');"
        "INSERT INTO settings VALUES('player_lock_-100','youtube');"
        "INSERT INTO settings VALUES('platform_-100','soundcloud');"
    )
    conn.commit(); conn.close()

    monkeypatch.setenv("DB_PATH", str(dbfile))
    import importlib
    import config
    importlib.reload(config)
    from bot import database as db
    importlib.reload(db)
    db._conn = None
    # اولین اتصال → مهاجرت اجرا می‌شود
    assert db.is_special(777) is True
    assert db.special_name(777) == "Reza"
    g = db.group_get(-100)
    assert g["enabled"] == 1
    assert g["lock"] == "youtube"
    assert g["platform"] == "soundcloud"


# ---------------- bootstrap: RESTORE_BLOB خودکفا ----------------
def test_restore_blob_roundtrip_and_apply(monkeypatch):
    import bootstrap
    data = {"BOT_TOKEN": "tok_abc", "OWNER_ID": "8406519786", "PROXY_LIST": "1.2.3.4:80:u:p"}
    blob = bootstrap._make_blob(data)
    assert "." in blob  # کلید.توکن
    assert bootstrap._read_blob(blob) == data

    # apply فقط متغیرهای غایب را می‌گذارد و متغیرهای موجود را override نمی‌کند
    monkeypatch.setenv("RESTORE_BLOB", blob)
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setenv("OWNER_ID", "999")  # از قبل ست → نباید عوض شود
    assert bootstrap.apply() is True
    import os
    assert os.environ["BOT_TOKEN"] == "tok_abc"      # غایب بود → بازیابی شد
    assert os.environ["OWNER_ID"] == "999"           # موجود بود → حفظ شد
    assert os.environ["PROXY_LIST"] == "1.2.3.4:80:u:p"


def test_restore_blob_invalid_is_safe(monkeypatch):
    import bootstrap
    monkeypatch.setenv("RESTORE_BLOB", "garbage-not-a-valid-blob")
    # نباید استثنا بدهد؛ فقط False برگرداند
    assert bootstrap.apply() is False
