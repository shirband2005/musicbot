"""تست‌های فاز ۶ — پنل مدیریت مالک و پنل مدیریت پلیر."""
import time

import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    dbfile = tmp_path / "manage.db"
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


def flat(m):
    return [b for row in labels(m) for b in row]


def cbs(m):
    return [b.callback_data for r in m.inline_keyboard for b in r
            if b.callback_data]


def shape(m):
    return [len(r) for r in m.inline_keyboard]


# ================================================================ صفحه‌ی اصلی
def test_main_page_counts_and_pending(fresh_db):
    from bot.plugins import manage

    text, _e, kb = manage.page_main(3, 2, 0)
    assert "۳ گروه" in text and "۲ گروه" in text
    assert "ندارد" in text
    assert not any("سفارش‌های در انتظار" in b for b in flat(kb))

    text, _e, kb = manage.page_main(3, 2, 4)
    assert any("سفارش‌های در انتظار (۴)" in b for b in flat(kb))
    assert "adm|pending" in cbs(kb)


def test_main_page_has_three_sections(fresh_db):
    from bot.plugins import manage

    _t, _e, kb = manage.page_main(1, 1, 0)
    f = flat(kb)
    assert "گروه‌های اشتراک‌دار" in f
    assert "گروه‌های بدون اشتراک" in f
    assert "مدیریت فروش" in f


# ================================================================ اشتراک‌دار
def test_subbed_list_shows_status(fresh_db):
    from bot import subscription as sub
    from bot.plugins import manage

    sub.activate(-100111, 1)
    _t, _e, kb = manage.page_subbed([(-100111, "گروه اول")])
    assert any("گروه اول" in b and "روز مانده" in b for b in flat(kb))
    assert "adm|sub|-100111" in cbs(kb)


def test_subbed_empty(fresh_db):
    from bot.plugins import manage

    text, _e, kb = manage.page_subbed([])
    assert "هیچ گروهی اشتراک ندارد" in text
    assert shape(kb) == [1]


def test_sub_page_day_buttons_symmetric(fresh_db):
    """دکمه‌های روز: منفی قرمز، مثبت سبز، به‌علاوه جهش‌های بزرگ."""
    from bot import subscription as sub
    from bot import ui
    from bot.plugins import manage

    sub.activate(-100111, 1)
    _t, _e, kb = manage.page_sub(-100111, "گروه")
    row = kb.inline_keyboard[0]
    assert [b.text for b in row] == ["− ۷ روز", "− ۱ روز", "+ ۱ روز", "+ ۷ روز"]
    assert [str(b.style) for b in row] == [str(ui.RED), str(ui.RED),
                                           str(ui.GREEN), str(ui.GREEN)]
    row1 = [b.text for b in kb.inline_keyboard[1]]
    assert row1 == ["+ ۱ ماه", "+ ۳ ماه", "دائمی"]


def test_sub_page_pause_resume_toggle(fresh_db):
    from bot import subscription as sub
    from bot.plugins import manage

    sub.activate(-100111, 1)
    _t, _e, kb = manage.page_sub(-100111, "گروه")
    assert "مکث اشتراک" in flat(kb)
    assert "ادامه اشتراک" not in flat(kb)

    sub.pause(-100111)
    text, _e, kb = manage.page_sub(-100111, "گروه")
    assert "ادامه اشتراک" in flat(kb)
    assert "مکث اشتراک" not in flat(kb)
    assert "مکث‌شده" in text
    assert "مصرف نمی‌شود" in text          # توضیح مفهوم تازه


def test_sub_page_permanent_hides_day_buttons(fresh_db):
    from bot import subscription as sub
    from bot.plugins import manage

    sub.activate(-100111, 1)
    sub.make_permanent(-100111)
    _t, _e, kb = manage.page_sub(-100111, "گروه")
    assert not any("روز" in b for b in flat(kb))
    assert "دائمی" not in flat(kb)          # دکمه‌ی دائمی هم لازم نیست


def test_sub_page_has_cancel(fresh_db):
    from bot import ui
    from bot.plugins import manage
    from bot import subscription as sub

    sub.activate(-100111, 1)
    _t, _e, kb = manage.page_sub(-100111, "گروه")
    cancel = [b for row in kb.inline_keyboard for b in row
              if b.text == "لغو اشتراک"]
    assert cancel and str(cancel[0].style) == str(ui.RED)


# ================================================================ بدون اشتراک
def test_free_group_page_states(fresh_db):
    from bot import group_config as gc
    from bot import subscription as sub
    from bot import ui
    from bot.plugins import manage

    cid = -100222
    # خاموش: ردیف روزها نباید باشد
    text, _e, kb = manage.page_free_group(cid, "گروه")
    assert "خاموش" in text
    assert shape(kb) == [2, 1]
    row = kb.inline_keyboard[0]
    assert str(row[0].style) == str(ui.PLAIN)     # روشن بی‌رنگ
    assert str(row[1].style) == str(ui.RED)       # خاموش قرمز

    # روشن با مهلت: ردیف روزها + بدون مهلت
    gc.set_enabled(cid, True)
    sub.set_free_days(cid, 3)
    text, _e, kb = manage.page_free_group(cid, "گروه")
    assert "روز" in text
    assert shape(kb) == [2, 4, 1, 1]
    assert "بدون مهلت (نامحدود)" in flat(kb)
    assert "خودکار خاموش می‌شود" in text


def test_free_list_shows_state(fresh_db):
    from bot import group_config as gc
    from bot import subscription as sub
    from bot.plugins import manage

    gc.set_enabled(-100222, True)
    sub.set_free_days(-100222, 5)
    _t, _e, kb = manage.page_free([(-100222, "گروه آزاد")])
    assert any("گروه آزاد" in b and "مهلت" in b for b in flat(kb))


def test_free_and_subbed_lists_are_disjoint(fresh_db):
    """گروهی که اشتراک دارد نباید در لیست بدون اشتراک بیاید."""
    from bot import subscription as sub
    from bot.plugins import manage

    fresh_db.add_chat(-100111)
    fresh_db.add_chat(-100222)
    sub.activate(-100111, 1)
    assert manage._subbed_ids() == [-100111]
    assert manage._free_ids() == [-100222]


# ================================================================ مدیریت فروش
def test_sales_page_shows_method_states(fresh_db):
    from bot import subscription as sub
    from bot.plugins import manage

    fresh_db.card_add("6037997712345678", "علی")
    text, _e, kb = manage.page_sales()
    assert "۱ کارت ثبت‌شده" in text
    assert sub.DEFAULT_NETWORK in text
    assert "فعال" in text

    sub.set_method_enabled(sub.METHOD_CRYPTO, False)
    text, _e, _kb = manage.page_sales()
    assert "خاموش" in text


def test_card_page_lists_cards_and_prices(fresh_db):
    from bot.plugins import manage

    fresh_db.card_add("6037997712345678", "علی رضایی")
    fresh_db.card_add("5859831187654321", "علی رضایی")
    text, _e, kb = manage.page_card()
    assert "کارت ۱" in text and "کارت ۲" in text
    assert "۱۲۰,۰۰۰ تومان" in text
    assert "شماره کارت‌ها" in flat(kb)
    assert "قیمت‌گذاری" in flat(kb)


def test_cards_page_crud_buttons(fresh_db):
    from bot.plugins import manage

    text, _e, kb = manage.page_cards()
    assert "هیچ کارتی ثبت نشده" in text
    assert "افزودن کارت" in flat(kb)

    cid = fresh_db.card_add("6037997712345678", "علی")
    _t, _e, kb = manage.page_cards()
    assert f"adm|cdel|{cid}" in cbs(kb)


def test_method_toggle_button_reflects_state(fresh_db):
    from bot import subscription as sub
    from bot import ui
    from bot.plugins import manage

    _t, _e, kb = manage.page_card()
    tog = [b for row in kb.inline_keyboard for b in row
           if b.callback_data == "adm|mtog|card"][0]
    assert "خاموش کن" in tog.text
    assert str(tog.style) == str(ui.GREEN)

    sub.set_method_enabled(sub.METHOD_CARD, False)
    _t, _e, kb = manage.page_card()
    tog = [b for row in kb.inline_keyboard for b in row
           if b.callback_data == "adm|mtog|card"][0]
    assert "فعال کن" in tog.text
    assert str(tog.style) == str(ui.RED)


def test_crypto_page_wallet_and_network(fresh_db):
    from bot import subscription as sub
    from bot.plugins import manage

    text, _e, kb = manage.page_crypto()
    assert "ثبت نشده" in text

    sub.set_wallet("TXn8kR4mQp7vZ2wLd9Fq2sYbN6hJ3xAe1")
    text, _e, kb = manage.page_crypto()
    assert "TXn8kR4mQp7vZ2wLd9Fq2sYbN6hJ3xAe1" in text
    assert "تغییر آدرس کیف‌پول" in flat(kb)
    assert "تغییر شبکه" in flat(kb)


def test_price_page_three_durations(fresh_db):
    from bot import subscription as sub
    from bot.plugins import manage

    _t, _e, kb = manage.page_price(sub.METHOD_CARD)
    assert len(kb.inline_keyboard) == 4          # سه مدت + بازگشت
    assert "adm|pset|card|2" in cbs(kb)

    _t, _e, kb = manage.page_price(sub.METHOD_CRYPTO)
    assert any("دلار" in b for b in flat(kb))


def test_stars_page_notes_instant(fresh_db):
    from bot.plugins import manage

    text, _e, kb = manage.page_stars()
    assert "آنی" in text
    assert "قیمت‌گذاری" in flat(kb)


# ================================================================ سفارش‌ها
def test_pending_page_pairs_buttons(fresh_db):
    from bot.plugins import manage

    fresh_db.order_create("oid1", 1, -100111, "single", 2, 220000, "card")
    fresh_db.order_create("oid2", 2, -100222, "single", 1, 150, "crypto")
    orders = fresh_db.orders_pending()
    names = {-100111: "گروه اول", -100222: "گروه دوم"}
    text, _e, kb = manage.page_pending(orders, names)
    assert "گروه اول" in text and "گروه دوم" in text
    assert "۲۲۰,۰۰۰ تومان" in text
    assert "۱.۵ دلار" in text                    # کریپتو از سِنت برگشت، ارقام فارسی
    assert "ord|ok|oid1" in cbs(kb)
    assert "ord|no|oid2" in cbs(kb)


def test_pending_empty(fresh_db):
    from bot.plugins import manage

    text, _e, kb = manage.page_pending([], {})
    assert "سفارشی در انتظار نیست" in text


# ================================================================ رنگ و کالبک
def test_all_back_buttons_blue(fresh_db):
    """همه‌ی دکمه‌های بازگشت پنل مدیریت آبی‌اند."""
    from bot import subscription as sub
    from bot import ui
    from bot.plugins import manage

    sub.activate(-100111, 1)
    fresh_db.card_add("6037997712345678", "x")
    pages = [
        manage.page_main(1, 1, 0),
        manage.page_subbed([(-100111, "گ")]),
        manage.page_sub(-100111, "گ"),
        manage.page_free([(-100222, "گ")]),
        manage.page_free_group(-100222, "گ"),
        manage.page_sales(),
        manage.page_card(),
        manage.page_cards(),
        manage.page_crypto(),
        manage.page_stars(),
        manage.page_price(sub.METHOD_CARD),
        manage.page_pending([], {}),
    ]
    found = 0
    for _t, _e, kb in pages:
        for row in kb.inline_keyboard:
            for b in row:
                if b.text == "بازگشت":
                    found += 1
                    assert str(b.style) == str(ui.BLUE), b.callback_data
    assert found >= 11


def test_manage_callbacks_within_limit(fresh_db):
    from bot import subscription as sub
    from bot.plugins import manage

    sub.activate(-1001234567890, 1)
    fresh_db.card_add("6037997712345678", "x")
    pages = [
        manage.page_main(1, 1, 2),
        manage.page_sub(-1001234567890, "گ"),
        manage.page_free_group(-1001234567890, "گ"),
        manage.page_cards(),
        manage.page_price(sub.METHOD_CRYPTO),
    ]
    for _t, _e, kb in pages:
        for c in cbs(kb):
            assert len(c.encode()) <= 64, c


def test_no_dead_noop_buttons(fresh_db):
    """پنل قدیمی دکمه‌ی noop داشت که کاری نمی‌کرد."""
    from bot import subscription as sub
    from bot.plugins import manage

    sub.activate(-100111, 1)
    pages = [manage.page_main(1, 1, 1), manage.page_sub(-100111, "گ"),
             manage.page_sales(), manage.page_card(), manage.page_crypto()]
    for _t, _e, kb in pages:
        for c in cbs(kb):
            assert "noop" not in c, c


# ================================================================ پنل پلیر
def test_player_panel_accordion_platform(fresh_db):
    from bot import group_config as gc
    from bot.plugins import admin_panel as ap

    cid = -100333
    ap._plat_open.pop(cid, None)
    _t, _e, kb = ap.panel(cid, "گروه من")
    assert shape(kb) == [2, 1, 1, 1]
    assert any("پلتفرم مجاز:" in b for b in flat(kb))
    assert f"mp|plat_open|{cid}" in cbs(kb)

    ap._plat_open[cid] = True
    _t, _e, kb = ap.panel(cid, "گروه من")
    assert shape(kb) == [2, 1, 3, 1, 1]
    assert "ساوندکلاد" in flat(kb) and "یوتیوب" in flat(kb) and "هر دو" in flat(kb)
    assert f"mp|lock_youtube|{cid}" in cbs(kb)
    ap._plat_open.pop(cid, None)


def test_player_panel_shows_group_and_subscription(fresh_db):
    from bot import subscription as sub
    from bot.plugins import admin_panel as ap

    cid = -100444
    sub.activate(cid, 1)
    text, _e, kb = ap.panel(cid, "گروه موزیک بچه‌ها")
    assert "گروه موزیک بچه‌ها" in text
    assert "اشتراک" in text
    assert "روز مانده" in text
    assert "مدیریت اشتراک این گروه" in flat(kb)


def test_player_panel_lock_marker(fresh_db):
    from bot import group_config as gc
    from bot.plugins import admin_panel as ap

    cid = -100555
    text, _e, _kb = ap.panel(cid, "گ")
    assert "هر دو" in text
    assert "(قفل)" not in text

    gc.set_lock(cid, gc.LOCK_YOUTUBE)
    text, _e, _kb = ap.panel(cid, "گ")
    assert "یوتیوب (قفل)" in text


def test_player_panel_callbacks_prefixed(fresh_db):
    from bot.plugins import admin_panel as ap

    cid = -1001234567890
    ap._plat_open[cid] = True
    for c in cbs(ap.panel(cid, "گ")[2]):
        assert c.startswith("mp|"), c
        assert len(c.encode()) <= 64, c
    ap._plat_open.pop(cid, None)
