"""تست‌های فاز ۲ — صفحه‌ی لیست پخش: صفحه‌بندی هوشمند، پرش، حذف.

قواعد تأییدشده‌ی کاربر:
  · تعداد دکمه = تعداد آهنگ همان صفحه (۳ آهنگ → ۳ دکمه، نه ۵)
  · حداکثر ۵ آهنگ در هر صفحه؛ بیشتر شد → صفحه‌ی بعد
  · اگر فقط یک صفحه باشد، ردیف ناوبری نباشد
"""
import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    dbfile = tmp_path / "pl.db"
    monkeypatch.setenv("DB_PATH", str(dbfile))
    import importlib
    import config
    importlib.reload(config)
    from bot import database as db
    importlib.reload(db)
    db._conn = None
    yield db


def mk(title="آهنگ", dur="3:20", requester="AB°L"):
    from bot.queue import Track

    return Track(title=title, stream_url="u", webpage_url="w", duration=200,
                 duration_text=dur, thumbnail=None, requester=requester,
                 requester_id=1)


def fill(chat_id, n):
    """صف را با n آهنگ پر می‌کند و لیستشان را برمی‌گرداند."""
    from bot import queue as q

    q.clear(chat_id)
    q.set_now_playing(chat_id, mk("در حال پخش"))
    made = []
    for i in range(1, n + 1):
        t = mk(f"آهنگ شماره {i}")
        q.add(chat_id, t)
        made.append(t)
    return made


def shape(markup):
    return [len(r) for r in markup.inline_keyboard]


def labels(markup):
    return [[b.text for b in r] for r in markup.inline_keyboard]


def cbs(markup):
    return [b.callback_data for r in markup.inline_keyboard for b in r
            if b.callback_data]


# ---------------------------------------------------------------- صفحه‌بندی
def test_page_count_math():
    from bot import playlist_page as pp

    assert pp.page_count(0) == 1
    assert pp.page_count(1) == 1
    assert pp.page_count(5) == 1
    assert pp.page_count(6) == 2
    assert pp.page_count(10) == 2
    assert pp.page_count(11) == 3


def test_clamp_page_bounds():
    from bot import playlist_page as pp

    assert pp.clamp_page(0, 10) == 1
    assert pp.clamp_page(5, 10) == 2      # فقط ۲ صفحه هست
    assert pp.clamp_page(-3, 3) == 1


def test_slice_page_numbers_continue():
    """شماره‌ها در صفحه‌ی دوم ادامه می‌یابند (۶، ۷) نه از یک."""
    from bot import playlist_page as pp

    items = [mk(f"t{i}") for i in range(7)]
    rows, start = pp.slice_page(items, 1)
    assert len(rows) == 5 and start == 1
    rows, start = pp.slice_page(items, 2)
    assert len(rows) == 2 and start == 6


# ------------------------------------------------- تعداد دکمه = تعداد آهنگ
@pytest.mark.parametrize("n,expected", [
    (1, [1, 1, 1]),
    (3, [3, 3, 1]),
    (5, [5, 5, 1]),
])
def test_button_count_matches_item_count_single_page(n, expected):
    from bot import playlist_page as pp

    items = [mk(f"t{i}") for i in range(n)]
    kbm = pp.keyboard(items, 1)
    assert shape(kbm) == expected          # بدون ردیف ناوبری


def test_six_items_adds_navigation():
    from bot import playlist_page as pp

    items = [mk(f"t{i}") for i in range(6)]
    assert shape(pp.keyboard(items, 1)) == [5, 5, 2, 1]   # ۵ + ناوبری
    assert shape(pp.keyboard(items, 2)) == [1, 1, 2, 1]   # صفحه‌ی دوم: ۱ آهنگ


def test_seven_items_second_page_two_buttons():
    from bot import playlist_page as pp

    items = [mk(f"t{i}") for i in range(7)]
    assert shape(pp.keyboard(items, 2)) == [2, 2, 2, 1]


def test_empty_queue_only_back_button():
    from bot import playlist_page as pp

    kbm = pp.keyboard([], 1)
    assert shape(kbm) == [1]
    assert cbs(kbm) == ["q|back"]


# ---------------------------------------------------------------- ناوبری
def test_navigation_hides_prev_on_first_page():
    from bot import playlist_page as pp

    items = [mk(f"t{i}") for i in range(12)]
    nav = labels(pp.keyboard(items, 1))[2]
    assert "صفحه قبل" not in nav
    assert "صفحه بعد" in nav

    nav = labels(pp.keyboard(items, 2))[2]
    assert "صفحه قبل" in nav and "صفحه بعد" in nav

    nav = labels(pp.keyboard(items, 3))[2]
    assert "صفحه قبل" in nav
    assert "صفحه بعد" not in nav


def test_page_counter_is_persian():
    from bot import playlist_page as pp

    items = [mk(f"t{i}") for i in range(6)]
    nav = labels(pp.keyboard(items, 1))[2]
    assert "۱/۲" in nav


# ---------------------------------------------------------------- callback با uid
def test_callbacks_carry_uid_not_index():
    """اگر شماره‌ی ردیف را بفرستیم، پس از حذف/رد شدن آهنگ اشتباهی حذف می‌شود."""
    from bot import playlist_page as pp

    items = [mk(f"t{i}") for i in range(3)]
    kbm = pp.keyboard(items, 1)
    for t in items:
        assert f"q|jump|{t.uid}" in cbs(kbm)
        assert f"q|del|{t.uid}" in cbs(kbm)


def test_callbacks_within_telegram_limit():
    from bot import playlist_page as pp

    items = [mk(f"t{i}") for i in range(12)]
    for page in (1, 2, 3):
        for c in cbs(pp.keyboard(items, page)):
            assert len(c.encode()) <= 64, c
            assert c.startswith("q|")


def test_delete_row_is_red():
    from bot import playlist_page as pp
    from bot import ui

    items = [mk(f"t{i}") for i in range(3)]
    kbm = pp.keyboard(items, 1)
    assert all(str(b.style) == str(ui.RED) for b in kbm.inline_keyboard[1])
    assert all(str(b.style) == str(ui.PLAIN) for b in kbm.inline_keyboard[0])


# ---------------------------------------------------------------- متن صفحه
def test_content_lists_titles_and_duration():
    from bot import playlist_page as pp

    cur = mk("در حال پخش")
    items = [mk("آهنگ اول", "4:12"), mk("آهنگ دوم", "3:05")]
    text, ents = pp.content(cur, items, 1)
    assert "لیست پخش" in text
    assert "در حال پخش" in text
    assert "آهنگ اول" in text and "آهنگ دوم" in text
    assert "۴:۱۲" in text                     # ارقام فارسی
    total = len(text.encode("utf-16-le")) // 2
    for e in ents:
        assert e.offset + e.length <= total


def test_content_empty_state_guides_user():
    from bot import playlist_page as pp

    text, _e = pp.content(mk("فعلی"), [], 1)
    assert "خالی" in text
    assert "بفرست" in text                    # راهنمایی، نه فقط اعلام


def test_content_shows_page_indicator_only_when_needed():
    from bot import playlist_page as pp

    few, _ = pp.content(mk("x"), [mk("a"), mk("b")], 1)
    assert "صفحه" not in few

    many, _ = pp.content(mk("x"), [mk(f"t{i}") for i in range(8)], 1)
    assert "صفحه ۱ از ۲" in many


def test_long_title_is_truncated():
    from bot import playlist_page as pp

    long = "Pink Floyd — Comfortably Numb (Live at Pulse 1994 Remastered Edition)"
    text, _e = pp.content(None, [mk(long)], 1)
    assert "…" in text
    assert long not in text


# ---------------------------------------------------------------- عملیات صف
def test_queue_find_and_remove_by_uid():
    from bot import queue as q

    items = fill(-900, 3)
    target = items[1]
    assert q.find(-900, target.uid) is target
    assert q.remove(-900, target.uid) is target
    assert q.find(-900, target.uid) is None
    assert q.queue_len(-900) == 2
    assert q.remove(-900, target.uid) is None     # حذف دوباره
    q.clear(-900)


def test_queue_move_to_front():
    from bot import queue as q

    items = fill(-901, 4)
    last = items[-1]
    assert q.move_to_front(-901, last.uid) is last
    assert list(q.get_queue(-901))[0] is last
    assert q.queue_len(-901) == 4                 # چیزی گم نشد
    q.clear(-901)


def test_move_to_front_unknown_uid():
    from bot import queue as q

    fill(-902, 2)
    assert q.move_to_front(-902, "nonexistent") is None
    q.clear(-902)


def test_remove_last_item_of_page_shifts_back():
    """حذف تنها آهنگِ صفحه‌ی ۲ → صفحه باید به ۱ برگردد."""
    from bot import playlist_page as pp
    from bot import queue as q

    items = fill(-903, 6)
    assert pp.page_count(6) == 2
    q.remove(-903, items[-1].uid)                 # حالا ۵ آهنگ = یک صفحه
    assert pp.page_count(q.queue_len(-903)) == 1
    assert pp.clamp_page(2, q.queue_len(-903)) == 1
    q.clear(-903)


# ---------------------------------------------------------------- نمای پنل
def test_view_state_switch_and_reset():
    from bot import panel

    panel.set_view(-100, panel.VIEW_PANEL)
    assert panel.get_view(-100) == panel.VIEW_PANEL

    panel.set_view(-100, panel.VIEW_PLAYLIST, 3)
    assert panel.get_view(-100) == panel.VIEW_PLAYLIST
    assert panel.get_view_page(-100) == 3

    # تعویض آهنگ/بستن پنل باید نما را به پنل پخش برگرداند
    panel.reset_menus(-100)
    assert panel.get_view(-100) == panel.VIEW_PANEL
    assert panel.get_view_page(-100) == 1


def test_view_page_never_below_one():
    from bot import panel

    panel.set_view(-100, panel.VIEW_PLAYLIST, 0)
    assert panel.get_view_page(-100) == 1
    panel.reset_menus(-100)


def test_render_switches_between_panel_and_playlist():
    """_render باید بر اساس نما، پنل یا لیست را بسازد."""
    from bot import panel
    from bot import player

    items = fill(-904, 3)
    cur = __import__("bot.queue", fromlist=["x"]).now_playing(-904)

    panel.set_view(-904, panel.VIEW_PANEL)
    text_a, _e, kb_a = player._render(-904, cur)
    assert "وضعیت" in text_a
    assert kb_a.inline_keyboard[0][0].callback_data == "p|refresh"

    panel.set_view(-904, panel.VIEW_PLAYLIST, 1)
    text_b, _e, kb_b = player._render(-904, cur)
    assert "لیست پخش" in text_b
    assert any(c.startswith("q|jump|") for c in cbs(kb_b))

    panel.reset_menus(-904)
    __import__("bot.queue", fromlist=["x"]).clear(-904)


def test_render_clamps_stale_page_after_removal():
    """اگر صفحه‌ی ذخیره‌شده بعد از حذف آهنگ‌ها وجود نداشته باشد، عقب می‌رود."""
    from bot import panel
    from bot import player
    from bot import queue as q

    items = fill(-905, 6)
    panel.set_view(-905, panel.VIEW_PLAYLIST, 2)
    for t in items[4:]:
        q.remove(-905, t.uid)                    # حالا ۴ آهنگ = یک صفحه
    cur = q.now_playing(-905)
    player._render(-905, cur)
    assert panel.get_view_page(-905) == 1
    panel.reset_menus(-905)
    q.clear(-905)
