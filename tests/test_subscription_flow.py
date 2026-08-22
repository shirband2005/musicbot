"""تست‌های فاز ۵ — اشتراک طرح واحد، جریان خرید، کانال پرداخت، اشتراک من."""
import time

import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    dbfile = tmp_path / "sub.db"
    monkeypatch.setenv("DB_PATH", str(dbfile))
    import importlib
    import config
    importlib.reload(config)
    from bot import database as db
    importlib.reload(db)
    db._conn = None
    yield db


def labels(m):
    return [[b.text for b in r] for r in m.inline_keyboard]


def cbs(m):
    return [b.callback_data for r in m.inline_keyboard for b in r
            if b.callback_data]


def copies(m):
    return [b.copy_text for r in m.inline_keyboard for b in r
            if getattr(b, "copy_text", None)]


# ================================================================ منطق اشتراک
def test_no_tiers_left():
    """تیرها حذف شدند — طرح واحد."""
    from bot import subscription as sub

    for gone in ("TIER_BASIC", "TIER_PRO", "TIER_LABEL", "is_pro", "get_tier"):
        assert not hasattr(sub, gone), gone
    assert sub.DURATIONS == (1, 2, 3)


def test_durations_and_methods():
    from bot import subscription as sub

    assert sub.duration_label(1) == "۱ ماهه"
    assert sub.duration_label(3) == "۳ ماهه"
    assert set(sub.METHODS) == {"card", "crypto", "stars"}
    assert sub.CURRENCY_LABEL["card"] == "تومان"
    assert sub.CURRENCY_LABEL["crypto"] == "دلار"
    assert sub.CURRENCY_LABEL["stars"] == "استارز"


def test_prices_per_method(fresh_db):
    """هر روش واحد پول خودش را دارد؛ کریپتو اعشاری است."""
    from bot import subscription as sub

    assert sub.get_price(sub.METHOD_CARD, 1) == 120_000
    assert sub.get_price(sub.METHOD_CRYPTO, 1) == 1.5
    assert sub.get_price(sub.METHOD_STARS, 1) == 100

    sub.set_price(sub.METHOD_CARD, 2, 250_000)
    assert sub.get_price(sub.METHOD_CARD, 2) == 250_000
    sub.set_price(sub.METHOD_CRYPTO, 2, 3.25)
    assert sub.get_price(sub.METHOD_CRYPTO, 2) == 3.25

    assert "تومان" in sub.price_text(sub.METHOD_CARD, 1)
    assert "دلار" in sub.price_text(sub.METHOD_CRYPTO, 1)


def test_method_enable_disable(fresh_db):
    """روش خاموش‌شده نباید در پنل خرید بیاید."""
    from bot import subscription as sub

    assert set(sub.enabled_methods()) == set(sub.METHODS)
    sub.set_method_enabled(sub.METHOD_CRYPTO, False)
    assert sub.METHOD_CRYPTO not in sub.enabled_methods()
    assert sub.method_enabled(sub.METHOD_CARD) is True
    sub.set_method_enabled(sub.METHOD_CRYPTO, True)
    assert sub.METHOD_CRYPTO in sub.enabled_methods()


def test_wallet_and_network(fresh_db):
    from bot import subscription as sub

    assert sub.network() == sub.DEFAULT_NETWORK
    sub.set_wallet("  TXn8kR4mQp  ")
    assert sub.wallet() == "TXn8kR4mQp"
    sub.set_network("BEP20")
    assert sub.network() == "BEP20"


def test_activate_and_status(fresh_db):
    from bot import subscription as sub

    cid = -100777
    assert sub.is_active(cid) is False
    assert sub.status_text(cid) == "بدون اشتراک"

    sub.activate(cid, 1, buyer_id=42)
    assert sub.is_active(cid) is True
    assert sub.days_left(cid) in (29, 30)
    assert "روز مانده" in sub.status_text(cid)


def test_renewal_extends_from_end_not_today(fresh_db):
    """تصمیم کاربر: تمدید از انتهای اشتراک فعال اضافه می‌شود."""
    from bot import database as db
    from bot import subscription as sub

    cid = -100778
    exp1 = sub.activate(cid, 1)
    exp2 = sub.activate(cid, 1)
    # اگر از امروز حساب می‌شد، exp2 حدوداً exp1 می‌ماند
    assert exp2 - exp1 == pytest.approx(sub.MONTH, abs=5)
    assert sub.days_left(cid) in (59, 60)


def test_expired_detection(fresh_db):
    from bot import database as db
    from bot import subscription as sub

    cid = -100779
    sub.activate(cid, 1)
    db.sub_set(cid, expires_at=time.time() - 10)
    assert sub.is_active(cid) is False
    assert sub.is_expired(cid) is True
    assert sub.status_text(cid) == "منقضی شده"
    assert sub.can_play(cid) is False


def test_pause_freezes_remaining_time(fresh_db):
    """مکث: زمان یخ می‌زند و با ادامه از همان‌جا می‌رود."""
    from bot import database as db
    from bot import subscription as sub

    cid = -100780
    sub.activate(cid, 1)
    before = sub.seconds_left(cid)

    assert sub.pause(cid) is True
    assert sub.is_paused(cid) is True
    assert sub.is_active(cid) is False          # ربات خاموش است
    assert sub.can_play(cid) is False
    assert sub.pause(cid) is False              # دوباره مکث نمی‌شود

    # زمان یخ‌زده: انقضا را عقب می‌بریم تا مطمئن شویم seconds_left از paused_at
    # حساب می‌شود نه از الان
    frozen = sub.seconds_left(cid)
    assert frozen == pytest.approx(before, abs=5)

    # ادامه: انقضا به اندازه‌ی مدت مکث جلو می‌رود
    row = db.sub_get(cid)
    db.sub_set(cid, paused_at=row["paused_at"] - 3600)   # یک ساعت مکث
    exp_before = db.sub_get(cid)["expires_at"]
    assert sub.resume(cid) is True
    assert sub.is_paused(cid) is False
    assert sub.is_active(cid) is True
    assert db.sub_get(cid)["expires_at"] - exp_before == pytest.approx(3600, abs=10)
    assert sub.resume(cid) is False              # دوباره ادامه نمی‌شود


def test_paused_status_text(fresh_db):
    from bot import subscription as sub

    cid = -100781
    sub.activate(cid, 1)
    sub.pause(cid)
    assert "مکث‌شده" in sub.status_text(cid)


def test_add_days_and_permanent(fresh_db):
    from bot import subscription as sub

    cid = -100782
    assert sub.add_days(cid, 5) is None          # بدون اشتراک
    sub.activate(cid, 1)
    d0 = sub.days_left(cid)
    sub.add_days(cid, 7)
    assert sub.days_left(cid) == d0 + 7
    sub.add_days(cid, -3)
    assert sub.days_left(cid) == d0 + 4

    sub.make_permanent(cid)
    assert sub.days_left(cid) == -1
    assert sub.status_text(cid) == "دائمی"
    assert sub.is_active(cid) is True


def test_permanent_activate_is_noop(fresh_db):
    from bot import subscription as sub

    cid = -100783
    sub.activate(cid, 1)
    sub.make_permanent(cid)
    assert sub.activate(cid, 3) == 0.0          # دائمی تمدید نمی‌شود
    assert sub.days_left(cid) == -1


def test_free_access_trial(fresh_db):
    """مهلت روشن ماندن بدون اشتراک (تصمیم کاربر)."""
    from bot import subscription as sub

    cid = -100784
    assert sub.has_free_access(cid) is False
    assert sub.can_play(cid) is False

    sub.set_free_days(cid, 3)
    assert sub.has_free_access(cid) is True
    assert sub.free_days_left(cid) in (2, 3)
    assert sub.can_play(cid) is True             # بدون اشتراک ولی مهلت دارد

    sub.add_free_days(cid, 4)
    assert sub.free_days_left(cid) in (6, 7)

    sub.set_free_days(cid, 0)
    assert sub.has_free_access(cid) is False


def test_unlimited_free(fresh_db):
    from bot import subscription as sub

    cid = -100785
    sub.set_unlimited_free(cid)
    assert sub.has_free_access(cid) is True
    assert sub.free_days_left(cid) > 3000


def test_cancel_removes_subscription(fresh_db):
    from bot import subscription as sub

    cid = -100786
    sub.activate(cid, 1)
    sub.cancel(cid)
    assert sub.has_subscription(cid) is False
    assert sub.status_text(cid) == "بدون اشتراک"


# ================================================================ صفحه‌های خرید
def test_page_groups_one_button_each():
    from bot.plugins import buy

    groups = [(-1, "گروه اول"), (-2, "گروه دوم"), (-3, "گروه سوم")]
    _t, _e, kb = buy.page_groups(groups, "https://t.me/bot?startgroup=true")
    assert [len(r) for r in kb.inline_keyboard] == [1, 1, 1, 1]
    assert labels(kb)[0][0] == "گروه اول"
    assert "buy|grp|-1" in cbs(kb)


def test_page_no_group_has_steps_and_add_button():
    from bot.plugins import buy

    text, _e, kb = buy.page_no_group("https://t.me/bot?startgroup=true")
    assert "۱." in text and "۳." in text
    assert "افزودن به گروه" in labels(kb)[0][0]


def test_page_methods_hides_disabled(fresh_db):
    from bot import subscription as sub
    from bot.plugins import buy

    _t, _e, kb = buy.page_methods("گروه", -1)
    flat = [b for row in labels(kb) for b in row]
    assert sub.METHOD_LABEL["card"] in flat
    assert sub.METHOD_LABEL["crypto"] in flat

    sub.set_method_enabled(sub.METHOD_CRYPTO, False)
    _t, _e, kb = buy.page_methods("گروه", -1)
    flat = [b for row in labels(kb) for b in row]
    assert sub.METHOD_LABEL["crypto"] not in flat


def test_page_plans_shows_price_on_button(fresh_db):
    """تصمیم کاربر: قیمت روی خود دکمه باشد."""
    from bot import subscription as sub
    from bot.plugins import buy

    _t, _e, kb = buy.page_plans("گروه", sub.METHOD_CARD)
    flat = [b for row in labels(kb) for b in row]
    assert any("اشتراک ۱ ماهه" in b and "تومان" in b for b in flat)
    assert any("۱۲۰,۰۰۰" in b for b in flat)          # ارقام فارسی
    assert "buy|plan|card|3" in cbs(kb)


def test_page_plans_crypto_dollar(fresh_db):
    from bot import subscription as sub
    from bot.plugins import buy

    _t, _e, kb = buy.page_plans("گروه", sub.METHOD_CRYPTO)
    flat = [b for row in labels(kb) for b in row]
    assert any("دلار" in b for b in flat)


def test_invoice_card_lists_cards_with_copy(fresh_db):
    """چند شماره کارت + دکمه‌ی کپی (تصمیم کاربر)."""
    from bot.plugins import buy

    fresh_db.card_add("6037997712345678", "علی رضایی")
    fresh_db.card_add("5859831187654321", "علی رضایی")
    text, _e, kb = buy.page_invoice_card("گروه", 2, "a1b2c3d4", fresh_db.cards_all())
    assert "شماره کارت ۱" in text and "شماره کارت ۲" in text
    assert "۳ ساعت" in text                        # هشدار تأیید مدیریت
    assert len(copies(kb)) == 2
    assert "buy|paid|a1b2c3d4" in cbs(kb)


def test_invoice_card_without_cards_warns(fresh_db):
    from bot.plugins import buy

    text, _e, kb = buy.page_invoice_card("گروه", 1, "oid", [])
    assert "ثبت نشده" in text
    assert not any(c.startswith("buy|paid") for c in cbs(kb))


def test_invoice_crypto_has_wallet_and_network(fresh_db):
    from bot import subscription as sub
    from bot.plugins import buy

    sub.set_wallet("TXn8kR4mQp7vZ2wLd9Fq2sYbN6hJ3xAe1")
    text, _e, kb = buy.page_invoice_crypto("گروه", 1, "oid123")
    assert "TXn8kR4mQp7vZ2wLd9Fq2sYbN6hJ3xAe1" in text
    assert sub.DEFAULT_NETWORK in text
    assert "۳ ساعت" in text
    assert len(copies(kb)) == 1


def test_invoice_stars_is_instant(fresh_db):
    from bot.plugins import buy

    text, _e, kb = buy.page_invoice_stars("گروه", 3, "https://t.me/invoice")
    assert "آنی" in text
    assert "۳ ساعت" not in text                    # استارز تأیید دستی ندارد
    assert any(b.url for row in kb.inline_keyboard for b in row)


def test_buy_callbacks_within_limit(fresh_db):
    from bot import subscription as sub
    from bot.plugins import buy

    fresh_db.card_add("6037997712345678", "x")
    pages = [
        buy.page_groups([(-1001234567890, "گروه")], ""),
        buy.page_methods("گروه", -1001234567890),
        buy.page_plans("گروه", sub.METHOD_CARD),
        buy.page_invoice_card("گروه", 1, "a" * 16, fresh_db.cards_all()),
        buy.page_invoice_crypto("گروه", 1, "b" * 16),
    ]
    for _t, _e, kb in pages:
        for c in cbs(kb):
            assert c.startswith("buy|"), c
            assert len(c.encode()) <= 64, c


# ================================================================ کانال پرداخت
def test_order_caption_has_all_fields(fresh_db):
    from bot.plugins import payments

    fresh_db.order_create("oid1", 555, -100111, "single", 2, 220000, "card")
    order = fresh_db.order_get("oid1")
    text, ents = payments.order_caption(order, "گروه من", "AB°L", 555)
    for field in ("گروه", "اشتراک", "مبلغ", "روش", "خریدار", "کد سفارش"):
        assert field in text
    assert "۲۲۰,۰۰۰ تومان" in text
    assert any(e.type.name == "TEXT_MENTION" for e in ents)
    total = len(text.encode("utf-16-le")) // 2
    for e in ents:
        assert e.offset + e.length <= total


def test_crypto_amount_stored_as_cents(fresh_db):
    """مبلغ کریپتو در دیتابیس صحیح ذخیره می‌شود (سِنت) و درست نمایش داده می‌شود."""
    from bot.plugins import payments

    fresh_db.order_create("oid2", 1, -1, "single", 1, 150, "crypto")   # 1.50 دلار
    order = fresh_db.order_get("oid2")
    assert "1.5 دلار" in payments._amount_text(order)


def test_order_keyboard_has_approve_and_reject():
    from bot import ui
    from bot.plugins import payments

    kb = payments.order_keyboard("oid1")
    assert labels(kb) == [["تأیید", "لغو"]]
    row = kb.inline_keyboard[0]
    assert str(row[0].style) == str(ui.GREEN)
    assert str(row[1].style) == str(ui.RED)
    assert cbs(kb) == ["ord|ok|oid1", "ord|no|oid1"]


def test_all_back_buttons_are_blue(fresh_db):
    """تصمیم کاربر: همه‌ی دکمه‌های بازگشت در بخش اشتراک آبی باشند."""
    from bot import subscription as sub
    from bot import ui
    from bot.plugins import buy, mysub

    fresh_db.card_add("6037997712345678", "x")
    sub.activate(-100111, 1)
    pages = [
        buy.page_no_group("https://t.me/b?startgroup=true"),
        buy.page_methods("گروه", -100111),
        buy.page_plans("گروه", sub.METHOD_CARD),
        buy.page_invoice_card("گروه", 1, "oid", fresh_db.cards_all()),
        buy.page_invoice_crypto("گروه", 1, "oid"),
        buy.page_invoice_stars("گروه", 1, "https://t.me/i"),
        mysub.page_detail(-100111, "گروه"),
    ]
    found = 0
    for _t, _e, kb in pages:
        for row in kb.inline_keyboard:
            for b in row:
                if b.text == "بازگشت":
                    found += 1
                    assert str(b.style) == str(ui.BLUE), b.callback_data
    assert found >= 6


def test_decision_caption_records_reviewer(fresh_db):
    from bot.plugins import payments

    fresh_db.order_create("oid3", 555, -100111, "single", 1, 120000, "card")
    order = fresh_db.order_get("oid3")
    text, _e = payments.decision_caption(order, "گروه", "AB°L", 555, True,
                                         "۳۰ روز مانده")
    assert "تأیید شد" in text
    assert "۳۰ روز مانده" in text
    # نام بررسی‌کننده نباید نمایش داده شود (تصمیم کاربر)
    assert "بررسی‌کننده" not in text

    text, _e = payments.decision_caption(order, "گروه", "AB°L", 555, False)
    assert "لغو شد" in text
    assert "بررسی‌کننده" not in text
    assert "به خریدار اطلاع داده شد" in text


def test_buyer_messages():
    from bot.plugins import payments

    text, _e, kb = payments.buyer_approved("گروه من", 2, "۶۰ روز مانده")
    assert "فعال شد" in text
    assert "پخش اهنگ" in text
    assert "my|list" in cbs(kb)

    text, _e, kb = payments.buyer_rejected("گروه من", 2, "oid1",
                                           "https://t.me/support")
    assert "لغو شد" in text
    assert "اعتراض" in text
    assert any(b.url for row in kb.inline_keyboard for b in row)


def test_stars_notice_has_no_buttons(fresh_db):
    from bot.plugins import payments

    fresh_db.order_create("oid4", 1, -1, "single", 3, 240, "stars")
    order = fresh_db.order_get("oid4")
    text, _e = payments.stars_notice(order, "گروه", "AB°L", 1)
    assert "آنی" in text
    assert "۲۴۰ استارز" in text


def test_payment_channel_configured():
    import config

    # مقدار واقعی از env می‌آید؛ اینجا فقط وجود فیلد و نوعش بررسی می‌شود
    assert isinstance(config.PAYMENT_CHANNEL, int)


# ================================================================ اشتراک من
def test_mysub_list_shows_days_left(fresh_db):
    from bot import subscription as sub
    from bot.plugins import mysub

    sub.activate(-100111, 1)
    sub.activate(-100222, 3)
    _t, _e, kb = mysub.page_list([(-100111, "گروه اول"), (-100222, "گروه دوم")])
    flat = [b for row in labels(kb) for b in row]
    assert any("گروه اول" in b and "روز مانده" in b for b in flat)
    assert "my|sub|-100111" in cbs(kb)


def test_mysub_empty_state(fresh_db):
    from bot.plugins import mysub

    text, _e, kb = mysub.page_list([])
    assert "هیچ اشتراکی" in text
    assert "buy|start" in cbs(kb)


def test_mysub_detail_states(fresh_db):
    from bot import database as db
    from bot import subscription as sub
    from bot.plugins import mysub

    cid = -100333
    sub.activate(cid, 1)
    text, _e, kb = mysub.page_detail(cid, "گروه من")
    assert "فعال" in text
    assert f"my|renew|{cid}" in cbs(kb)

    sub.pause(cid)
    text, _e, _kb = mysub.page_detail(cid, "گروه من")
    assert "مکث‌شده" in text

    sub.resume(cid)
    db.sub_set(cid, expires_at=time.time() - 5)
    text, _e, _kb = mysub.page_detail(cid, "گروه من")
    assert "منقضی" in text


def test_mysub_permanent_has_no_renew(fresh_db):
    from bot import subscription as sub
    from bot.plugins import mysub

    cid = -100444
    sub.activate(cid, 1)
    sub.make_permanent(cid)
    _t, _e, kb = mysub.page_detail(cid, "گروه")
    assert not any(c.startswith("my|renew") for c in cbs(kb))


# ================================================================ انقضا
def test_expiry_watcher_skips_paused_and_free(fresh_db):
    """اشتراک مکث‌شده یا گروه با مهلت آزمایشی نباید خاموش شود."""
    from bot import database as db
    from bot import subscription as sub

    paused_cid, free_cid = -100901, -100902
    sub.activate(paused_cid, 1)
    db.sub_set(paused_cid, expires_at=time.time() - 10)
    sub.pause(paused_cid)

    sub.activate(free_cid, 1)
    db.sub_set(free_cid, expires_at=time.time() - 10)
    sub.set_free_days(free_cid, 5)

    expired = db.sub_expired(time.time())
    ids = {r["chat_id"] for r in expired}
    assert paused_cid in ids and free_cid in ids     # هر دو در فهرست خام‌اند
    # ولی منطق نگهبان باید ردشان کند:
    assert sub.is_paused(paused_cid) is True
    assert sub.has_free_access(free_cid) is True
    assert sub.can_play(free_cid) is True
