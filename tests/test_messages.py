"""تست‌های فاز ۷ — پیام‌های وضعیت و خطا."""
import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    dbfile = tmp_path / "msg.db"
    monkeypatch.setenv("DB_PATH", str(dbfile))
    import importlib
    import config
    importlib.reload(config)
    from bot import database as db
    importlib.reload(db)
    db._conn = None
    yield db


def flat(kb):
    return [b.text for row in kb.inline_keyboard for b in row]


def urls(kb):
    return [b.url for row in kb.inline_keyboard for b in row if b.url]


def utf16_len(s):
    return len(s.encode("utf-16-le")) // 2


def check_entities(text, ents):
    total = utf16_len(text)
    for e in ents:
        assert e.offset >= 0
        assert e.offset + e.length <= total, (e.type, e.offset, e.length, total)


# ================================================================ کد خطا
def test_error_code_is_stable_and_short():
    from bot import messages as msg

    c1 = msg.error_code(ValueError("boom"))
    c2 = msg.error_code(ValueError("boom"))
    c3 = msg.error_code(ValueError("other"))
    assert c1 == c2 != c3
    assert c1.startswith("E-") and len(c1) == 6


def test_playback_error_hides_python_exception():
    """ایراد اصلی نسخه‌ی قبلی: متن خام استثنا به کاربر نشان داده می‌شد."""
    from bot import messages as msg

    exc = RuntimeError("Traceback: NoneType has no attribute 'foo' at line 42")
    text, ents, kb = msg.playback_error(exc, "https://t.me/support")
    assert "NoneType" not in text
    assert "Traceback" not in text
    assert "line 42" not in text
    assert msg.error_code(exc) in text
    assert "پشتیبانی" in flat(kb)
    check_entities(text, ents)


def test_playback_error_uses_friendly_when_given():
    from bot import messages as msg

    text, _e, _kb = msg.playback_error(Exception("raw"), "",
                                       "ویدیو در دسترس نیست")
    assert "ویدیو در دسترس نیست" in text
    assert "raw" not in text


# ================================================================ وضعیت
def test_searching_shows_stage_progress():
    """نسخه‌ی قبلی یک متن ثابت بود؛ کاربر نمی‌دانست کار پیش می‌رود."""
    from bot import messages as msg

    text, ents, _kb = msg.searching("شادمهر عقیلی", 1)
    assert "مرحله : ۱ از ۳" in text
    assert "شادمهر عقیلی" in text
    check_entities(text, ents)

    text, _e, _kb = msg.searching("x", 3)
    assert "مرحله : ۳ از ۳" in text
    assert "اتصال به ویس‌چت" in text

    # خارج از محدوده نباید خطا بدهد
    text, _e, _kb = msg.searching("x", 99)
    assert "۳ از ۳" in text


def test_queued_shows_position_and_playlist_button():
    from bot import messages as msg

    text, ents, kb = msg.queued(3, "آهنگ تست", "04:12")
    assert "موقعیت در صف : ۳" in text
    assert "آهنگ تست" in text
    assert "۰۴:۱۲" in text
    assert "لیست پخش" in flat(kb)
    check_entities(text, ents)


def test_downloading_and_stream_messages():
    from bot import messages as msg

    text, ents, _kb = msg.downloading("فایل من")
    assert "آماده‌سازی" in text and "فایل من" in text
    check_entities(text, ents)

    text, _e, _kb = msg.stream_big_file(120)
    assert "۱۲۰ مگابایت" in text


# ================================================================ خطاهای پخش
def test_no_voice_chat_says_what_why_how():
    from bot import messages as msg

    text, ents, kb = msg.no_voice_chat()
    assert "ویس‌چت روشن نیست" in text
    assert "چرا" in text or "برای پخش" in text
    assert "ویدیو چت" in text            # راه‌حل عملی
    check_entities(text, ents)


def test_bot_not_admin_message_exists():
    """حالتی که قبلاً هیچ پیامی نداشت و علت واقعی خیلی خطاها بود."""
    from bot import messages as msg

    text, _e, _kb = msg.bot_not_admin()
    assert "ادمین" in text
    assert "ویدیو چت" in text


def test_not_found_suggests_alternatives():
    from bot import messages as msg

    text, ents, _kb = msg.not_found("یه چیزی")
    assert "پیدا نشد" in text
    assert "یه چیزی" in text
    assert "لینک" in text                 # پیشنهاد جایگزین
    check_entities(text, ents)

    text, _e, _kb = msg.not_found()
    assert "پیدا نشد" in text


def test_too_long_states_both_numbers():
    from bot import messages as msg

    text, _e, _kb = msg.too_long("02:30:00", "60 دقیقه")
    assert "۰۲:۳۰:۰۰" in text
    assert "۶۰ دقیقه" in text


def test_download_failed_and_empty_archive():
    from bot import messages as msg

    text, _e, kb = msg.download_failed("https://t.me/s")
    assert "دانلود ناموفق" in text
    assert urls(kb)

    text, _e, _kb = msg.empty_archive()
    assert "آرشیو خالی" in text
    assert "پخش کن" in text


def test_nothing_playing_and_empty_queue():
    from bot import messages as msg

    text, _e, _kb = msg.nothing_playing()
    assert "در حال پخش نیست" in text
    assert "پخش اهنگ" in text

    text, _e, _kb = msg.empty_queue()
    assert "صف خالی" in text


# ================================================================ دسترسی
def test_subscription_states_are_distinct():
    """نسخه‌ی قبلی برای همه‌ی این حالت‌ها یک پیام کلی می‌داد."""
    from bot import messages as msg

    t1, _e, kb1 = msg.no_subscription("https://t.me/b?start=buy", "https://t.me/s")
    t2, _e, kb2 = msg.subscription_expired("https://t.me/b?start=renew",
                                           "https://t.me/s")
    t3, _e, kb3 = msg.subscription_paused("https://t.me/s")
    t4, _e, kb4 = msg.player_off("https://t.me/s")

    assert "اشتراک فعال ندارد" in t1
    assert "تمام شد" in t2
    assert "مکث" in t3
    assert "خاموش" in t4
    assert len({t1, t2, t3, t4}) == 4      # چهار پیام متمایز

    assert "خرید اشتراک" in flat(kb1)
    assert "تمدید اشتراک" in flat(kb2)
    assert "پشتیبانی" in flat(kb3)


def test_deep_links_in_subscription_messages():
    from bot import messages as msg

    _t, _e, kb = msg.no_subscription("https://t.me/bot?start=buy")
    assert any(u.endswith("?start=buy") for u in urls(kb))

    _t, _e, kb = msg.subscription_expired("https://t.me/bot?start=renew")
    assert any(u.endswith("?start=renew") for u in urls(kb))


def test_group_only_has_add_button():
    from bot import messages as msg

    text, _e, kb = msg.group_only("https://t.me/bot?startgroup=true")
    assert "فقط در گروه" in text
    assert "افزودن به گروه" in flat(kb)


def test_not_admin_and_pv_denied():
    from bot import messages as msg

    text, _e, _kb = msg.not_admin("https://t.me/s")
    assert "ادمین" in text

    text, _e, _kb = msg.pv_denied("https://t.me/s")
    assert "خصوصی" in text
    assert "گروه" in text                  # راه‌حل: در گروه استفاده کن


def test_messages_without_urls_have_no_broken_buttons():
    """اگر لینک پشتیبانی نبود، دکمه‌ی شکسته ساخته نشود."""
    from bot import messages as msg

    for payload in (msg.no_subscription(), msg.subscription_expired(),
                    msg.subscription_paused(), msg.player_off(),
                    msg.not_admin(), msg.pv_denied(), msg.download_failed()):
        _t, _e, kb = payload
        for row in kb.inline_keyboard:
            for b in row:
                assert b.url or b.callback_data, b.text


def test_all_messages_have_valid_entities():
    """همه‌ی entityها باید داخل مرز UTF-16 متن باشند."""
    from bot import messages as msg

    payloads = [
        msg.searching("q", 2), msg.downloading("t"), msg.queued(2, "t", "01:00"),
        msg.stream_big_file(50), msg.no_voice_chat(), msg.bot_not_admin(),
        msg.not_found("q"), msg.too_long("01:00:00", "60 دقیقه"),
        msg.download_failed(), msg.playback_error(Exception("e")),
        msg.empty_archive(), msg.nothing_playing(), msg.empty_queue(),
        msg.no_subscription(), msg.subscription_expired(),
        msg.subscription_paused(), msg.not_admin(), msg.group_only(),
        msg.pv_denied(), msg.player_off(),
    ]
    assert len(payloads) == 20
    for text, ents, _kb in payloads:
        check_entities(text, ents)


def test_play_plugin_no_longer_leaks_exceptions():
    """در play.py هیچ جایی متن خام استثنا را به کاربر نفرستد."""
    import re

    src = open("/opt/data/musicbot/bot/plugins/play.py", encoding="utf-8").read()
    # الگوهای نشتی: `{e}` یا str(e)[:N] داخل متن پیام کاربر
    assert "خطا در پخش:" not in src
    assert "خطا در استریم:" not in src
    assert "دانلود فایل ناموفق:" not in src
    assert not re.search(r'edit_text\(f?"[^"]*\{e\}', src)
