"""تست‌های فاز ۰ بازنویسی UI — پایه‌ها (ui.py، مهاجرت دیتابیس، Track.uid).

اجرا: .venv/bin/python -m pytest tests/test_ui_core.py -q
"""
import os
import sqlite3
import tempfile

import pytest


# ---------------------------------------------------------------- ui.timebar
def test_timebar_shape_and_bounds():
    from bot import ui

    # ابتدای آهنگ: سر نوار در خانه‌ی صفر
    bar = ui.timebar(0, 240)
    assert bar.startswith("00:00 │ ◉")
    assert bar.endswith("│ 04:00")

    # وسط: تعداد ━ متناسب با نسبت گذشته
    mid = ui.timebar(120, 240, length=12)
    assert mid.count("━") == 6
    assert mid.count("◉") == 1

    # انتها: نوار پر، ولی ◉ همیشه یکی است
    end = ui.timebar(240, 240, length=12)
    assert end.count("━") == 12
    assert end.count("◉") == 1
    assert end.count("─") == 0


def test_timebar_live_has_no_progress():
    from bot import ui

    for dur in (0, None):
        bar = ui.timebar(95, dur)
        assert "زنده" in bar
        assert "◉" not in bar  # نوار پیشرفت برای مدت نامعلوم معنا ندارد


def test_timebar_never_overflows_on_bad_position():
    """موقعیت بزرگ‌تر از مدت (drift استریم) نباید نوار را بشکند."""
    from bot import ui

    bar = ui.timebar(9999, 240, length=12)
    assert bar.count("━") == 12
    assert bar.count("◉") == 1


def test_timebar_hours_format():
    from bot import ui

    bar = ui.timebar(3700, 7320)  # فیلم دو ساعته
    assert bar.startswith("1:01:40")
    assert "2:02:00" in bar


def test_countdown_formats():
    from bot import ui

    assert ui.countdown(95) == "1:35"
    assert ui.countdown(1800) == "30:00"
    assert ui.countdown(3612) == "1:00:12"
    assert ui.countdown(-5) == "0:00"  # منفی نباید خطا بدهد


# ---------------------------------------------------------------- ui.Text
def test_text_entity_offsets_are_utf16():
    """آفست entity باید با UTF-16 حساب شود، نه len پایتون.

    ایموجی‌های خارج از BMP (مثل 🎧) دو code unit اشغال می‌کنند؛ اگر با len
    پایتون بشماریم، همه‌ی entityهای بعدی جابه‌جا می‌شوند.
    """
    from bot import ui

    t = ui.Text().title(ui.EMO_HEADPHONE, ui.BASE_HEADPHONE, "شادمهر عقیلی")
    total_u16 = len(t.text.encode("utf-16-le")) // 2
    for e in t.entities:
        assert e.offset >= 0
        assert e.offset + e.length <= total_u16

    # ایموجی پایه 🎧 دو واحد UTF-16 است
    emoji_ent = [e for e in t.entities if e.custom_emoji_id][0]
    assert emoji_ent.length == 2
    # عنوان بولد بعد از «🎧 » می‌آید → آفست ۳
    bold_ent = [e for e in t.entities if e.type.name == "BOLD"][0]
    assert bold_ent.offset == 3


def test_text_field_alternating_arrows():
    from bot import ui

    t = ui.Text()
    for i, (label, val) in enumerate([("وضعیت", "پخش"), ("نوع", "آهنگ"),
                                      ("پلتفرم", "یوتیوب")]):
        t.field(i, label, val)
    ids = [e.custom_emoji_id for e in t.entities if e.custom_emoji_id]
    assert ids == [ui.EMO_ARROW_BLUE, ui.EMO_ARROW_RED, ui.EMO_ARROW_BLUE]
    assert t.text.count("\n") == 3


def test_text_mention_and_emoji_coexist():
    """منشن و ایموجی پرمیوم در یک پیام باید هر دو سالم بمانند."""
    from bot import ui

    t = ui.Text()
    t.field(0, "پخش‌کننده", mention=("AB°L", 8406519786))
    types = {e.type.name for e in t.entities}
    assert "CUSTOM_EMOJI" in types
    assert "TEXT_MENTION" in types
    total_u16 = len(t.text.encode("utf-16-le")) // 2
    for e in t.entities:
        assert e.offset + e.length <= total_u16


def test_mention_without_user_id_degrades_to_plain():
    """اگر شناسه‌ی عددی نداشته باشیم، نام ساده اضافه شود نه entity شکسته."""
    from bot import ui

    t = ui.Text().mention("ناشناس", 0)
    assert t.text == "ناشناس"
    assert t.entities == []


def test_text_code_entity_for_copyable_values():
    from bot import ui

    t = ui.Text().field(0, "کد سفارش", code="a1b2c3d4")
    assert any(e.type.name == "CODE" for e in t.entities)


# ---------------------------------------------------------------- ui helpers
def test_fa_digits_and_thousands():
    from bot import ui

    assert ui.fa(120000) == "۱۲۰,۰۰۰"
    assert ui.fa(5) == "۵"
    assert ui.fa("1.5") == "۱.۵"


def test_trunc_keeps_short_and_marks_long():
    from bot import ui

    assert ui.trunc("کوتاه", 38) == "کوتاه"
    long = "Pink Floyd — Comfortably Numb (Live at Pulse 1994)"
    out = ui.trunc(long, 20)
    assert len(out) == 20
    assert out.endswith("…")


def test_icon_btn_uses_zero_width_label():
    """دکمه‌ی فقط-آیکون باید متن بی‌عرض داشته باشد (تلگرام متن خالی نمی‌پذیرد)."""
    from bot import ui

    b = ui.icon_btn("p|stop", ui.EMO_STOP, ui.RED)
    assert b.text == ui.ZW
    assert b.icon_custom_emoji_id == ui.EMO_STOP
    assert b.callback_data == "p|stop"


def test_kb_drops_empty_rows():
    from bot import ui

    markup = ui.kb([[ui.btn("الف", "a")], [], [ui.btn("ب", "b")]])
    assert len(markup.inline_keyboard) == 2


def test_nav_row_optional_parts():
    from bot import ui

    assert len(ui.nav_row(back="x|back")) == 1
    assert len(ui.nav_row(back="x|back", close="x|close")) == 2
    assert ui.nav_row() == []


def test_callback_data_within_telegram_limit():
    """همه‌ی الگوهای callback طرح جدید باید زیر ۶۴ بایت بمانند."""
    samples = [
        "p|mode_set|random", "p|sleep_set|45", "p|plat_set|soundcloud",
        "q|jump|a1b2c3d4", "q|del|a1b2c3d4", "q|page|3",
        "buy|plan|crypto|3", "buy|grp|-1001234567890",
        "ord|ok|a1b2c3d4e5f6a7b8", "adm|day|-1001234567890|-7",
        "my|renew|-1001234567890", "v|sleep_set|60",
    ]
    for cb in samples:
        assert len(cb.encode("utf-8")) <= 64, cb


# ---------------------------------------------------------------- امضای رفرش
def test_signature_detects_change_and_stability():
    """رفرش شرطی: امضای یکسان = بدون ادیت، تغییر رنگ/برچسب = ادیت."""
    from bot import ui

    kb1 = ui.kb([[ui.btn(ui.timebar(10, 240), "p|refresh", ui.BLUE)]])
    kb2 = ui.kb([[ui.btn(ui.timebar(10, 240), "p|refresh", ui.BLUE)]])
    kb3 = ui.kb([[ui.btn(ui.timebar(30, 240), "p|refresh", ui.BLUE)]])

    assert ui.signature("متن", kb1) == ui.signature("متن", kb2)
    assert ui.signature("متن", kb1) != ui.signature("متن", kb3)
    assert ui.signature("متن", kb1) != ui.signature("متن دیگر", kb1)

    # تغییر رنگ هم باید دیده شود (بیصدا → قرمز)
    a = ui.kb([[ui.btn("100%", "p|mute", ui.PLAIN)]])
    b = ui.kb([[ui.btn("0%", "p|mute", ui.RED)]])
    assert ui.signature("x", a) != ui.signature("x", b)


def test_signature_handles_no_markup():
    from bot import ui

    assert ui.signature("سلام", None) == ui.signature("سلام", None)


# ---------------------------------------------------------------- Track
def test_track_gets_unique_uid():
    from bot.queue import Track

    def mk():
        return Track(title="t", stream_url="u", webpage_url="w", duration=10,
                     duration_text="0:10", thumbnail=None, requester="me")

    uids = {mk().uid for _ in range(50)}
    assert len(uids) == 50
    assert all(len(u) == 8 for u in uids)


def test_track_uid_survives_serialization():
    """صف در دیتابیس JSON می‌شود؛ uid و requester_id نباید گم شوند."""
    from dataclasses import asdict
    from bot.queue import Track, track_from_dict

    t = Track(title="t", stream_url="u", webpage_url="w", duration=10,
              duration_text="0:10", thumbnail=None, requester="AB°L",
              requester_id=8406519786)
    back = track_from_dict(asdict(t))
    assert back.uid == t.uid
    assert back.requester_id == 8406519786


def test_track_explicit_uid_is_respected():
    from bot.queue import Track

    t = Track(title="t", stream_url="u", webpage_url="w", duration=1,
              duration_text="0:01", thumbnail=None, requester="me", uid="deadbeef")
    assert t.uid == "deadbeef"


# ---------------------------------------------------------------- مهاجرت DB
def _fresh_db(monkeypatch, path):
    """دیتابیس تازه با مسیر موقت (بدون دست زدن به DB واقعی)."""
    import config
    from bot import database as db

    db.close()
    monkeypatch.setattr(config, "DB_PATH", path, raising=False)
    return db


def test_new_columns_exist_on_fresh_db(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, str(tmp_path / "new.db"))
    assert db.group_get(-1)["free_until"] == 0.0
    db.sub_set(-1, expires_at=123.0, paused_at=55.0)
    assert db.sub_get(-1)["paused_at"] == 55.0
    db.close()


def test_migration_adds_columns_to_old_db(monkeypatch, tmp_path):
    """دیتابیس قدیمی (بدون ستون‌های جدید) باید بی‌خطا ارتقا یابد و داده حفظ شود."""
    path = str(tmp_path / "old.db")
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE group_settings (
            chat_id  INTEGER PRIMARY KEY,
            enabled  INTEGER DEFAULT 0,
            lock     TEXT DEFAULT 'none',
            platform TEXT DEFAULT 'both'
        );
        CREATE TABLE subscriptions (
            chat_id       INTEGER PRIMARY KEY,
            tier          TEXT DEFAULT 'basic',
            expires_at    REAL DEFAULT 0,
            buyer_id      INTEGER DEFAULT 0,
            started_at    REAL DEFAULT 0,
            last_notified REAL DEFAULT 0
        );
        INSERT INTO group_settings(chat_id, enabled, lock) VALUES (-777, 1, 'youtube');
        INSERT INTO subscriptions(chat_id, tier, expires_at) VALUES (-777, 'pro', 999.0);
        """
    )
    con.commit()
    con.close()

    db = _fresh_db(monkeypatch, path)
    g = db.group_get(-777)
    assert g["enabled"] == 1 and g["lock"] == "youtube"   # داده‌ی قدیمی حفظ شد
    assert g["mode"] == "queue" and g["free_until"] == 0.0  # ستون‌های جدید
    s = db.sub_get(-777)
    assert s["expires_at"] == 999.0 and s["paused_at"] == 0.0
    db.close()


def test_migration_is_idempotent(monkeypatch, tmp_path):
    """اجرای دوباره‌ی مهاجرت نباید خطا بدهد یا داده را خراب کند."""
    path = str(tmp_path / "twice.db")
    db = _fresh_db(monkeypatch, path)
    db.group_set(-5, enabled=1, free_until=42.0)
    db.close()
    db = _fresh_db(monkeypatch, path)
    assert db.group_get(-5)["free_until"] == 42.0
    db.close()


# ---------------------------------------------------------------- کارت‌ها
def test_pay_cards_crud(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, str(tmp_path / "cards.db"))
    assert db.cards_all() == []

    id1 = db.card_add("6037997712345678", "علی رضایی")
    id2 = db.card_add("5859831187654321", "علی رضایی")
    cards = db.cards_all()
    assert [c["id"] for c in cards] == [id1, id2]      # ترتیب افزودن حفظ می‌شود
    assert cards[0]["number"] == "6037997712345678"

    assert db.card_delete(id1) is True
    assert db.card_delete(id1) is False               # حذف دوباره → False
    assert len(db.cards_all()) == 1
    db.close()


def test_card_add_strips_whitespace(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, str(tmp_path / "cards2.db"))
    cid = db.card_add("  6037-9977-1234-5678  ", "  علی  ")
    c = db.cards_all()[0]
    assert c["number"] == "6037-9977-1234-5678"
    assert c["holder"] == "علی"
    db.close()
