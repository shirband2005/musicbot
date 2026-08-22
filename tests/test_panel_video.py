"""تست‌های فاز ۳ — پنل فیلم (`v|*`).

طرح تأییدشده: بدون پلتفرم، بدون حالت پخش، بدون لیست پخش، بدون قبلی/بعدی.
"""
import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    dbfile = tmp_path / "vid.db"
    monkeypatch.setenv("DB_PATH", str(dbfile))
    import importlib
    import config
    importlib.reload(config)
    from bot import database as db
    importlib.reload(db)
    db._conn = None
    yield db


def mk_video(**kw):
    from bot.queue import Track

    base = dict(title="هزارپا (۱۳۹۷)", stream_url="u", webpage_url="w",
                duration=7320, duration_text="2:02:00", thumbnail=None,
                requester="AB°L", requester_id=8406519786, is_video=True,
                source="youtube")
    base.update(kw)
    return Track(**base)


def mk_audio(**kw):
    from bot.queue import Track

    base = dict(title="شادمهر عقیلی — دیوانه", stream_url="u", webpage_url="w",
                duration=252, duration_text="4:12", thumbnail=None,
                requester="AB°L", requester_id=8406519786, is_video=False)
    base.update(kw)
    return Track(**base)


def shape(m):
    return [len(r) for r in m.inline_keyboard]


def labels(m):
    return [[b.text for b in r] for r in m.inline_keyboard]


def cbs(m):
    return [b.callback_data for r in m.inline_keyboard for b in r
            if b.callback_data]


# ---------------------------------------------------------------- متن
def test_video_text_has_three_fields():
    """فیلم سه خط دارد: وضعیت/نوع/پخش‌کننده — بدون پلتفرم و بدون صدا."""
    from bot import panel_video as pv

    text, ents = pv.content(mk_video(), 100, False, -100)
    assert "وضعیت" in text and "نوع" in text and "پخش‌کننده" in text
    assert "پلتفرم" not in text
    assert "میزان صدا" not in text
    assert "فیلم" in text


def test_video_text_uses_movie_icon():
    from bot import panel_video as pv
    from bot import ui

    _t, ents = pv.content(mk_video(), chat_id=-1)
    ids = [e.custom_emoji_id for e in ents if e.custom_emoji_id]
    assert ui.EMO_MOVIE in ids
    assert ui.EMO_HEADPHONE not in ids


def test_video_text_states():
    from bot import panel_video as pv

    assert "در حال پخش" in pv.content(mk_video())[0]
    assert "متوقف موقت" in pv.content(mk_video(paused=True))[0]


def test_video_text_entities_within_bounds():
    from bot import panel_video as pv

    text, ents = pv.content(mk_video(), chat_id=-1)
    total = len(text.encode("utf-16-le")) // 2
    assert ents
    for e in ents:
        assert e.offset + e.length <= total


def test_video_text_has_clickable_requester():
    from bot import panel_video as pv

    _t, ents = pv.content(mk_video(), chat_id=-1)
    assert any(e.type.name == "TEXT_MENTION" for e in ents)


# ---------------------------------------------------------------- کیبورد
def test_video_keyboard_shape():
    """نوار / کنترل(۲) / صدا(۳) / تایمر / دریافت / بستن"""
    from bot import panel, panel_video as pv

    panel.reset_menus(-100)
    kbm = pv.keyboard(-100, mk_video(), 100, False)
    assert shape(kbm) == [1, 2, 3, 1, 1, 1]


def test_video_control_row_has_only_two_buttons():
    """فیلم صف ندارد → «قبلی/بعدی» نباید باشد."""
    from bot import panel_video as pv

    kbm = pv.keyboard(-100, mk_video(), 100, False)
    assert len(kbm.inline_keyboard[1]) == 2
    all_cb = cbs(kbm)
    assert not any("prev" in c or "skip" in c for c in all_cb)


def test_video_has_no_playlist_mode_or_platform():
    from bot import panel_video as pv

    all_cb = " ".join(cbs(pv.keyboard(-100, mk_video(), 100, False)))
    for forbidden in ("playlist", "mode_", "plat_"):
        assert forbidden not in all_cb


def test_video_timebar_uses_hour_format():
    from bot import panel_video as pv

    tr = mk_video()
    tr.elapsed_before_pause = 1450.0
    tr.paused = True
    bar = pv.keyboard(-100, tr, 100, False).inline_keyboard[0][0].text
    assert "2:02:00" in bar          # مدت کل با ساعت
    assert "24:10" in bar            # موقعیت فعلی


def test_video_control_colors():
    from bot import panel_video as pv
    from bot import ui

    kbm = pv.keyboard(-100, mk_video(), 100, False)
    row = kbm.inline_keyboard[1]
    assert str(row[0].style) == str(ui.BLUE)     # مکث
    assert str(row[1].style) == str(ui.RED)      # توقف

    kbm = pv.keyboard(-100, mk_video(paused=True), 100, False)
    assert str(kbm.inline_keyboard[1][0].style) == str(ui.GREEN)   # پخش


def test_video_volume_row_matches_music_rules():
    from bot import panel_video as pv
    from bot import ui

    kbm = pv.keyboard(-100, mk_video(), 70, False)
    row = kbm.inline_keyboard[2]
    assert row[1].text == "70%"
    assert all(str(b.style) == str(ui.PLAIN) for b in row)

    kbm = pv.keyboard(-100, mk_video(), 70, True)
    row = kbm.inline_keyboard[2]
    assert row[1].text == "0%"
    assert str(row[1].style) == str(ui.RED)


def test_video_sleep_timer_three_states():
    from bot import panel, panel_video as pv

    panel.reset_menus(-100)
    assert labels(pv.keyboard(-100, mk_video(), 100, False, None))[3] == ["تایمر خواب"]

    panel.set_menu(-100, panel.MENU_SLEEP)
    kbm = pv.keyboard(-100, mk_video(), 100, False, None)
    assert labels(kbm)[3] == ["۱۵ دقیقه", "۳۰ دقیقه", "۴۵ دقیقه", "۱ ساعت"]
    assert shape(kbm) == [1, 2, 3, 4, 1, 1]     # پنل بلندتر نمی‌شود
    panel.reset_menus(-100)

    lbl = labels(pv.keyboard(-100, mk_video(), 100, False, 1062))[3][0]
    assert "17:42" in lbl


def test_video_media_button_says_film():
    from bot import panel_video as pv

    lbl = labels(pv.keyboard(-100, mk_video(), 100, False))[4][0]
    assert lbl == "دریافت فیلم"


def test_video_callbacks_prefixed_and_within_limit():
    from bot import panel, panel_video as pv

    panel.set_menu(-100, panel.MENU_SLEEP)
    all_cb = set(cbs(pv.keyboard(-100, mk_video(), 100, False)))
    panel.reset_menus(-100)
    all_cb |= set(cbs(pv.keyboard(-100, mk_video(), 100, False, 500)))
    assert all_cb
    for c in all_cb:
        assert c.startswith("v|"), c
        assert len(c.encode()) <= 64, c


def test_video_live_stream_bar():
    from bot import panel_video as pv

    bar = pv.keyboard(-100, mk_video(duration=0), 100, False).inline_keyboard[0][0]
    assert "زنده" in bar.text


# ------------------------------------------------- انتخاب پنل بر اساس نوع
def test_render_picks_video_panel_for_video_track():
    from bot import panel, player
    from bot import queue as q

    q.clear(-950)
    q.set_now_playing(-950, mk_video())
    cur = q.now_playing(-950)
    text, _e, kbm = player._render(-950, cur)
    assert "فیلم" in text
    assert cbs(kbm)[0] == "v|refresh"
    assert shape(kbm) == [1, 2, 3, 1, 1, 1]
    q.clear(-950)


def test_render_picks_music_panel_for_audio_track():
    from bot import panel, player
    from bot import queue as q

    q.clear(-951)
    q.set_now_playing(-951, mk_audio())
    cur = q.now_playing(-951)
    text, _e, kbm = player._render(-951, cur)
    assert cbs(kbm)[0] == "p|refresh"
    assert "پلتفرم پخش" in text
    q.clear(-951)


def test_video_ignores_playlist_view():
    """حتی اگر نمای لیست ست شده باشد، فیلم پنل خودش را نشان می‌دهد."""
    from bot import panel, player
    from bot import queue as q

    q.clear(-952)
    q.set_now_playing(-952, mk_video())
    q.add(-952, mk_audio())
    panel.set_view(-952, panel.VIEW_PLAYLIST, 1)
    cur = q.now_playing(-952)
    _t, _e, kbm = player._render(-952, cur)
    assert cbs(kbm)[0] == "v|refresh"
    panel.reset_menus(-952)
    q.clear(-952)
