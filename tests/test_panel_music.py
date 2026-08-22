"""تست‌های فاز ۱ — پنل پخش موزیک، منوهای آکاردئونی، رفرش شرطی، تایمر خواب.

بدون اتصال به تلگرام: فقط ساختار کیبورد و متن بررسی می‌شود.
"""
import asyncio

import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    dbfile = tmp_path / "panel.db"
    monkeypatch.setenv("DB_PATH", str(dbfile))
    import importlib
    import config
    importlib.reload(config)
    from bot import database as db
    importlib.reload(db)
    db._conn = None
    yield db


def mk_track(**kw):
    from bot.queue import Track

    base = dict(title="شادمهر عقیلی — دیوانه", stream_url="u", webpage_url="w",
                duration=252, duration_text="4:12", thumbnail=None,
                requester="AB°L", requester_id=8406519786, source="youtube")
    base.update(kw)
    return Track(**base)


def labels(markup):
    return [[b.text for b in row] for row in markup.inline_keyboard]


def shape(markup):
    return [len(row) for row in markup.inline_keyboard]


def styles(markup, row):
    return [str(getattr(b, "style", "")) for b in markup.inline_keyboard[row]]


def cbs(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row
            if b.callback_data]


# ---------------------------------------------------------------- متن پنل
def test_panel_text_has_four_fields_no_volume():
    """«میزان صدا» عمداً از متن حذف شد (روی دکمه‌ی صدا دیده می‌شود)."""
    from bot import panel

    text, ents = panel.panel_content(mk_track(), 100, False, -100)
    assert text.count("\n") >= 5
    assert "وضعیت" in text and "نوع" in text and "پلتفرم پخش" in text
    assert "پخش‌کننده" in text
    assert "میزان صدا" not in text


def test_panel_text_states():
    from bot import panel

    assert "در حال پخش" in panel.panel_text(mk_track(), chat_id=-1)
    assert "متوقف موقت" in panel.panel_text(mk_track(paused=True), chat_id=-1)
    assert "ویدیو" in panel.panel_text(mk_track(is_video=True), chat_id=-1)
    assert "آهنگ" in panel.panel_text(mk_track(is_video=False), chat_id=-1)


def test_panel_text_entities_within_bounds():
    """آفست entityها باید داخل مرز UTF-16 متن بمانند (وگرنه تلگرام رد می‌کند)."""
    from bot import panel

    text, ents = panel.panel_content(mk_track(), chat_id=-1)
    total = len(text.encode("utf-16-le")) // 2
    assert ents
    for e in ents:
        assert e.offset >= 0 and e.offset + e.length <= total


def test_panel_text_has_clickable_requester():
    from bot import panel

    _t, ents = panel.panel_content(mk_track(), chat_id=-1)
    assert any(e.type.name == "TEXT_MENTION" for e in ents)


def test_panel_text_requester_without_id_is_plain():
    from bot import panel

    _t, ents = panel.panel_content(mk_track(requester_id=0), chat_id=-1)
    assert not any(e.type.name == "TEXT_MENTION" for e in ents)


def test_panel_text_shows_lock_marker(fresh_db):
    from bot import group_config as gc
    from bot import panel

    gc.set_lock(-300, gc.LOCK_YOUTUBE)
    assert "(قفل)" in panel.panel_text(mk_track(), chat_id=-300)


# ---------------------------------------------------------------- کیبورد پایه
def test_keyboard_default_shape():
    from bot import panel

    kbm = panel.panel_keyboard(-100, mk_track(), 100, False)
    # نوار / کنترل / صدا / لیست+حالت / تایمر / رسانه+پلتفرم / بستن
    assert shape(kbm) == [1, 4, 3, 2, 1, 2, 1]


def test_timebar_is_single_full_width_button():
    from bot import panel

    kbm = panel.panel_keyboard(-100, mk_track(), 100, False)
    bar = kbm.inline_keyboard[0][0]
    assert "│" in bar.text and "◉" in bar.text
    assert bar.callback_data == "p|refresh"


def test_control_row_colors_directional():
    """قرمز=عقب/توقف، سبز=جلو، آبی=مکث. رنگ‌بندی تأییدشده‌ی کاربر."""
    from bot import panel, ui

    kbm = panel.panel_keyboard(-100, mk_track(), 100, False)
    st = styles(kbm, 1)
    assert st[0] == str(ui.RED)      # قبلی
    assert st[1] == str(ui.BLUE)     # مکث
    assert st[2] == str(ui.RED)      # توقف
    assert st[3] == str(ui.GREEN)    # بعدی


def test_paused_shows_green_play_button():
    from bot import panel, ui

    kbm = panel.panel_keyboard(-100, mk_track(paused=True), 100, False)
    assert styles(kbm, 1)[1] == str(ui.GREEN)
    assert kbm.inline_keyboard[1][1].icon_custom_emoji_id == ui.EMO_PLAY


def test_volume_row_is_colorless_when_audible():
    from bot import panel, ui

    kbm = panel.panel_keyboard(-100, mk_track(), 80, False)
    assert styles(kbm, 2) == [str(ui.PLAIN)] * 3
    assert kbm.inline_keyboard[2][1].text == "80%"


def test_muted_shows_zero_percent_and_red():
    """در حالت بیصدا درصد باید صفر شود و فقط دکمه‌ی وسط قرمز باشد."""
    from bot import panel, ui

    kbm = panel.panel_keyboard(-100, mk_track(), 100, True)
    row = kbm.inline_keyboard[2]
    assert row[1].text == "0%"
    assert str(row[1].style) == str(ui.RED)
    assert str(row[0].style) == str(ui.PLAIN)
    assert str(row[2].style) == str(ui.PLAIN)


def test_control_buttons_use_zero_width_label():
    from bot import panel, ui

    kbm = panel.panel_keyboard(-100, mk_track(), 100, False)
    for b in kbm.inline_keyboard[1]:
        assert b.text == ui.ZW
        assert b.icon_custom_emoji_id


def test_live_stream_bar_has_no_progress():
    from bot import panel

    kbm = panel.panel_keyboard(-100, mk_track(duration=0), 100, False)
    assert "زنده" in kbm.inline_keyboard[0][0].text


# ---------------------------------------------------------------- منوی حالت پخش
def test_mode_menu_closed_shows_current_mode(fresh_db):
    from bot import panel

    panel.reset_menus(-100)
    kbm = panel.panel_keyboard(-100, mk_track(), 100, False)
    row = labels(kbm)[3]
    assert row[0] == "لیست پخش"
    assert row[1].startswith("حالت: ")
    assert "p|mode_open" in cbs(kbm)


def test_mode_menu_open_adds_one_row(fresh_db):
    from bot import panel

    panel.set_menu(-100, panel.MENU_MODE)
    kbm = panel.panel_keyboard(-100, mk_track(), 100, False)
    assert shape(kbm) == [1, 4, 3, 2, 3, 1, 2, 1]
    assert labels(kbm)[4] == ["صف", "تکرار", "رندوم"]
    assert "p|mode_set|repeat" in cbs(kbm)
    panel.reset_menus(-100)


def test_mode_menu_marks_active_green(fresh_db):
    from bot import group_config as gc
    from bot import panel, ui

    gc.set_mode(-100, gc.MODE_RANDOM)
    panel.set_menu(-100, panel.MENU_MODE)
    kbm = panel.panel_keyboard(-100, mk_track(), 100, False)
    st = styles(kbm, 4)
    assert st == [str(ui.PLAIN), str(ui.PLAIN), str(ui.GREEN)]
    panel.reset_menus(-100)


def test_toggle_menu_opens_then_closes(fresh_db):
    from bot import panel

    panel.reset_menus(-100)
    assert panel.toggle_menu(-100, panel.MENU_MODE) == panel.MENU_MODE
    assert panel.toggle_menu(-100, panel.MENU_MODE) is None
    # منوی دیگر جای منوی قبلی را می‌گیرد (دو منو همزمان باز نمی‌شود)
    panel.set_menu(-100, panel.MENU_MODE)
    assert panel.toggle_menu(-100, panel.MENU_SLEEP) == panel.MENU_SLEEP
    assert panel.open_menu(-100) == panel.MENU_SLEEP
    panel.reset_menus(-100)


# ---------------------------------------------------------------- تایمر خواب
def test_sleep_row_three_states(fresh_db):
    from bot import panel

    panel.reset_menus(-100)
    # ۱) خاموش
    kbm = panel.panel_keyboard(-100, mk_track(), 100, False, None)
    assert labels(kbm)[4] == ["تایمر خواب"]

    # ۲) منو باز → چهار گزینه، همان یک ردیف
    panel.set_menu(-100, panel.MENU_SLEEP)
    kbm = panel.panel_keyboard(-100, mk_track(), 100, False, None)
    assert labels(kbm)[4] == ["۱۵ دقیقه", "۳۰ دقیقه", "۴۵ دقیقه", "۱ ساعت"]
    assert shape(kbm) == [1, 4, 3, 2, 4, 2, 1]   # پنل بلندتر نمی‌شود
    panel.reset_menus(-100)

    # ۳) فعال → شمارش معکوس، قرمز
    kbm = panel.panel_keyboard(-100, mk_track(), 100, False, 1062)
    lbl = labels(kbm)[4][0]
    assert lbl.startswith("تایمر خواب : ") and "17:42" in lbl


def test_sleep_timer_start_left_cancel():
    from bot import sleep_timer

    sleep_timer.clear_all()
    assert sleep_timer.left(-1) is None
    left = sleep_timer.start(-1, 30)
    assert left == 1800
    assert 1790 < (sleep_timer.left(-1) or 0) <= 1800
    assert sleep_timer.is_active(-1) is True
    assert sleep_timer.cancel(-1) is True
    assert sleep_timer.cancel(-1) is False       # دوباره خاموش کردن
    assert sleep_timer.left(-1) is None
    sleep_timer.clear_all()


def test_sleep_timer_replaces_previous():
    from bot import sleep_timer

    sleep_timer.clear_all()
    sleep_timer.start(-2, 60)
    sleep_timer.start(-2, 15)                    # تایمر دوم جایگزین می‌شود
    assert (sleep_timer.left(-2) or 0) <= 900
    sleep_timer.clear_all()


@pytest.mark.asyncio
async def test_sleep_timer_fires_handler():
    """تایمر واقعاً هندلر پایان را صدا می‌زند (با زمان کوتاه شبیه‌سازی‌شده)."""
    from bot import sleep_timer

    sleep_timer.clear_all()
    fired = []

    async def handler(chat_id):
        fired.append(chat_id)

    old = sleep_timer._on_expire
    sleep_timer.set_expire_handler(handler)
    try:
        sleep_timer._deadline[-9] = 0.0
        import asyncio as _a
        sleep_timer._task[-9] = _a.create_task(sleep_timer._wait(-9, 0.05))
        await _a.sleep(0.3)
        assert fired == [-9]
        assert sleep_timer.left(-9) is None       # پس از اجرا پاک می‌شود
    finally:
        if old:
            sleep_timer.set_expire_handler(old)
        sleep_timer.clear_all()


# ---------------------------------------------------------------- پلتفرم
def test_platform_menu_closed_and_open(fresh_db):
    from bot import panel

    panel.reset_menus(-100)
    kbm = panel.panel_keyboard(-100, mk_track(), 100, False)
    assert labels(kbm)[5][0] == "دریافت رسانه"
    assert labels(kbm)[5][1].startswith("پلتفرم: ")

    panel.set_menu(-100, panel.MENU_PLAT)
    kbm = panel.panel_keyboard(-100, mk_track(), 100, False)
    assert labels(kbm)[6] == ["دیتابیس", "یوتیوب", "ساوندکلاد"]
    assert "p|plat_set|youtube" in cbs(kbm)
    panel.reset_menus(-100)


def test_platform_locked_shows_marker_and_no_menu(fresh_db):
    """در حالت قفل، دکمه می‌ماند با «(قفل)» ولی منو باز نمی‌شود."""
    from bot import group_config as gc
    from bot import panel

    gc.set_lock(-400, gc.LOCK_SOUNDCLOUD)
    panel.set_menu(-400, panel.MENU_PLAT)        # حتی اگر منو ست شده باشد
    kbm = panel.panel_keyboard(-400, mk_track(), 100, False)
    assert labels(kbm)[5][1] == "ساوندکلاد (قفل)"
    assert "p|plat_locked" in cbs(kbm)
    assert not any(c.startswith("p|plat_set") for c in cbs(kbm))
    assert shape(kbm) == [1, 4, 3, 2, 1, 2, 1]   # ردیف گزینه‌ها اضافه نشد
    panel.reset_menus(-400)


def test_platform_label_respects_lock(fresh_db):
    from bot import group_config as gc
    from bot import panel

    assert panel.platform_label(-500) == "دیتابیس"
    gc.set_lock(-500, gc.LOCK_YOUTUBE)
    assert panel.platform_label(-500) == "یوتیوب (قفل)"


# ---------------------------------------------------------------- callback
def test_all_callbacks_within_limit_and_prefixed():
    from bot import panel

    panel.set_menu(-100, panel.MENU_MODE)
    all_cbs = set(cbs(panel.panel_keyboard(-100, mk_track(), 100, False, 500)))
    panel.set_menu(-100, panel.MENU_SLEEP)
    all_cbs |= set(cbs(panel.panel_keyboard(-100, mk_track(), 100, False)))
    panel.set_menu(-100, panel.MENU_PLAT)
    all_cbs |= set(cbs(panel.panel_keyboard(-100, mk_track(), 100, False)))
    panel.reset_menus(-100)

    assert all_cbs
    for c in all_cbs:
        assert c.startswith("p|"), c
        assert len(c.encode()) <= 64, c


def test_legacy_callbacks_are_mapped():
    """پنل‌های ماندهٔ گروه‌ها با کالبک قدیمی نباید بشکنند."""
    from bot import group_config as gc
    from bot.plugins.callbacks import _parse

    assert _parse("p|mode_repeat|-100123") == ("mode_set", gc.MODE_REPEAT)
    assert _parse("p|mode_queue|-100123") == ("mode_set", gc.MODE_QUEUE)
    assert _parse("p|mode_random|-100123") == ("mode_set", gc.MODE_RANDOM)
    assert _parse("p|platform|-100123") == ("plat_cycle", "-100123")


def test_parse_new_callbacks():
    from bot.plugins.callbacks import _parse

    assert _parse("p|refresh") == ("refresh", None)
    assert _parse("p|sleep_set|45") == ("sleep_set", "45")
    assert _parse("p|plat_set|youtube") == ("plat_set", "youtube")
    assert _parse("p|close") == ("close", None)


# ---------------------------------------------------------------- رفرش شرطی
def test_signature_stable_across_same_second():
    """در یک ثانیه، نوار عوض نمی‌شود → امضا ثابت → ادیت نباید بزند."""
    from bot import panel, ui

    tr = mk_track()
    tr.mark_started()
    text = panel.panel_text(tr, 100, False, -100)
    kb1 = panel.panel_keyboard(-100, tr, 100, False)
    kb2 = panel.panel_keyboard(-100, tr, 100, False)
    assert ui.signature(text, kb1) == ui.signature(text, kb2)


def test_signature_changes_with_position():
    from bot import panel, ui

    tr = mk_track()
    tr.mark_started()
    kb_a = panel.panel_keyboard(-100, tr, 100, False)
    sig_a = ui.signature(panel.panel_text(tr, 100, False, -100), kb_a)
    # جلو بردن ساعت پخش با دست‌کاری زمان شروع (بدون sleep واقعی)
    tr.elapsed_before_pause = 60.0
    kb_b = panel.panel_keyboard(-100, tr, 100, False)
    sig_b = ui.signature(panel.panel_text(tr, 100, False, -100), kb_b)
    assert sig_a != sig_b


def test_signature_changes_when_muted():
    from bot import panel, ui

    tr = mk_track()
    a = ui.signature(panel.panel_text(tr, 100, False, -100),
                     panel.panel_keyboard(-100, tr, 100, False))
    b = ui.signature(panel.panel_text(tr, 100, True, -100),
                     panel.panel_keyboard(-100, tr, 100, True))
    assert a != b
