"""تست‌های فاز ۴ — /start سه‌نسخه‌ای و پنل راهنمای تخت‌شده.

نکته‌ی مهم: نسخه‌ی قبلی لینک «افزودن به گروه» را `https://t.me/?startgroup=true`
هاردکد کرده بود (بدون یوزرنیم) — دکمه کاربر را به هیچ‌جا می‌برد.
"""
import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    dbfile = tmp_path / "start.db"
    monkeypatch.setenv("DB_PATH", str(dbfile))
    import importlib
    import config
    importlib.reload(config)
    from bot import database as db
    importlib.reload(db)
    db._conn = None
    yield db


class FakeMe:
    username = "Ablhermesbot"
    id = 123


class FakeClient:
    async def get_me(self):
        return FakeMe()


@pytest.fixture(autouse=True)
def reset_username_cache():
    from bot.plugins import start
    start._bot_username = None
    yield
    start._bot_username = None


def labels(m):
    return [[b.text for b in r] for r in m.inline_keyboard]


def urls(m):
    return [b.url for r in m.inline_keyboard for b in r if b.url]


def cbs(m):
    return [b.callback_data for r in m.inline_keyboard for b in r
            if b.callback_data]


# ---------------------------------------------------------------- یوزرنیم ربات
@pytest.mark.asyncio
async def test_add_group_url_includes_bot_username():
    """باگ نسخه‌ی قبلی: لینک بدون یوزرنیم بود و دکمه کار نمی‌کرد."""
    from bot.plugins import start

    url = await start.add_group_url(FakeClient())
    assert url == "https://t.me/Ablhermesbot?startgroup=true"
    assert "t.me/?" not in url


@pytest.mark.asyncio
async def test_bot_username_is_cached():
    from bot.plugins import start

    calls = []

    class Counting(FakeClient):
        async def get_me(self):
            calls.append(1)
            return FakeMe()

    c = Counting()
    await start.bot_username(c)
    await start.bot_username(c)
    assert len(calls) == 1        # بار دوم از کش می‌آید


@pytest.mark.asyncio
async def test_get_me_failure_degrades_gracefully():
    """اگر get_me خطا داد، لینک خالی برگردد نه لینک شکسته."""
    from bot.plugins import start

    class Broken:
        async def get_me(self):
            raise RuntimeError("network")

    assert await start.add_group_url(Broken()) == ""


@pytest.mark.asyncio
async def test_pv_deep_link_payload():
    from bot.plugins import start

    assert await start.pv_url(FakeClient()) == "https://t.me/Ablhermesbot"
    assert await start.pv_url(FakeClient(), "buy") == \
        "https://t.me/Ablhermesbot?start=buy"
    assert (await start.pv_url(FakeClient(), "renew")).endswith("?start=renew")


# ---------------------------------------------------------------- /start نسخه‌ها
@pytest.mark.asyncio
async def test_start_new_user_has_steps_and_add_button():
    from bot.plugins import start

    text, ents, kb = await start._start_new_user(FakeClient())
    assert "۱." in text and "۴." in text          # چهار گام شماره‌دار
    assert "اشتراک" in text                        # صادقانه می‌گوید لازم است
    assert "افزودن به گروه" in labels(kb)[0][0]
    assert any("startgroup=true" in u for u in urls(kb))
    total = len(text.encode("utf-16-le")) // 2
    for e in ents:
        assert e.offset + e.length <= total


@pytest.mark.asyncio
async def test_start_new_user_add_button_is_green():
    from bot.plugins import start
    from bot import ui

    _t, _e, kb = await start._start_new_user(FakeClient())
    assert str(kb.inline_keyboard[0][0].style) == str(ui.GREEN)


@pytest.mark.asyncio
async def test_start_owner_shows_stats(fresh_db):
    from bot.plugins import start

    fresh_db.add_chat(-100111)
    fresh_db.add_chat(-100222)
    text, _e, kb = await start._start_owner(FakeClient())
    assert "پنل مالک" in text
    assert "گروه‌های ثبت‌شده" in text
    assert "۲ گروه" in text                        # ارقام فارسی
    assert "adm|main" in cbs(kb)


@pytest.mark.asyncio
async def test_start_owner_pending_badge(fresh_db):
    """اگر سفارش در انتظار باشد، دکمه‌ی قرمز هشدار اضافه شود."""
    import time
    from bot.plugins import start
    from bot import ui

    _t, _e, kb = await start._start_owner(FakeClient())
    assert not any("سفارش" in b for row in labels(kb) for b in row)

    fresh_db.order_create("oid1", 1, -100111, "basic", 1, 1000, "card")
    _t, _e, kb = await start._start_owner(FakeClient())
    flat = [b for row in labels(kb) for b in row]
    assert any("سفارش‌های در انتظار" in b for b in flat)
    assert "adm|pending" in cbs(kb)


@pytest.mark.asyncio
async def test_start_special_user_no_subscription_talk():
    from bot.plugins import start

    text, _e, kb = await start._start_special(FakeClient())
    assert "ویژه" in text
    assert "اشتراک" not in text                    # کاربر ویژه اشتراک نمی‌خواهد
    assert "پخش اهنگ" in text


@pytest.mark.asyncio
async def test_start_group_message_is_short():
    from bot.plugins import start

    text, _e, kb = await start._start_group(FakeClient())
    assert len(text) < 200
    assert "ویس‌چت" in text
    assert len(kb.inline_keyboard) == 1            # فقط راهنما


# ---------------------------------------------------------------- راهنما
def test_help_has_five_nodes():
    from bot.plugins import start

    assert len(start.HELP_NODES) == 5
    for node in start.HELP_NODES:
        text, ents = start.help_content(node)
        assert text.strip()
        total = len(text.encode("utf-16-le")) // 2
        for e in ents:
            assert e.offset + e.length <= total


def test_help_main_menu_has_four_sections():
    from bot.plugins import start

    kb = start.help_markup(start.HELP_MAIN)
    flat = [b for row in labels(kb) for b in row]
    assert "پخش آهنگ" in flat
    assert "پخش فیلم" in flat
    assert "کنترل پخش" in flat
    assert "پنل و دکمه‌ها" in flat


def test_help_control_page_flattens_five_old_subpages():
    """پنج زیرصفحه‌ی قبلی هر کدام یک خط بودند — حالا همه در یک صفحه."""
    from bot.plugins import start

    text, _e = start.help_content(start.HELP_CONTROL)
    for cmd in ("مکث", "ادامه", "بعدی", "خروج", "لیست"):
        assert cmd in text


def test_help_includes_new_features():
    """قابلیت‌هایی که در راهنمای قبلی کلاً غایب بودند."""
    from bot.plugins import start

    joined = " ".join(start.help_content(n)[0] for n in start.HELP_NODES)
    for feature in ("رندوم", "حالت پخش", "پلتفرم", "تایمر خواب", "لیست پخش"):
        assert feature in joined, feature


def test_help_panel_page_explains_buttons():
    from bot.plugins import start

    text, _e = start.help_content(start.HELP_PANEL)
    for item in ("نوار زمان", "صدا", "لیست پخش", "تایمر خواب", "پلتفرم"):
        assert item in text


def test_help_commands_are_code_entities():
    """دستورها باید code باشند تا با یک لمس کپی شوند."""
    from bot.plugins import start

    _t, ents = start.help_content(start.HELP_SONG)
    assert sum(1 for e in ents if e.type.name == "CODE") >= 4


def test_help_color_hierarchy():
    """رنگ فقط روی پشتیبانی (آبی) و بستن (قرمز)."""
    from bot.plugins import start
    from bot import ui

    kb = start.help_markup(start.HELP_MAIN, "https://t.me/support")
    styles = {}
    for row in kb.inline_keyboard:
        for b in row:
            styles[b.text] = str(b.style)
    assert styles["پشتیبانی"] == str(ui.BLUE)
    assert styles["بستن راهنما"] == str(ui.RED)
    assert styles["پخش آهنگ"] == str(ui.PLAIN)


def test_help_subpage_has_back_and_close():
    from bot.plugins import start

    for node in (start.HELP_SONG, start.HELP_MOVIE, start.HELP_CONTROL,
                 start.HELP_PANEL):
        flat = [b for row in labels(start.help_markup(node)) for b in row]
        assert flat == ["بازگشت", "بستن راهنما"]


def test_legacy_help_nodes_are_mapped():
    """راهنماهای ماندهٔ گروه‌ها با گره قدیمی نباید بشکنند."""
    from bot.plugins import start

    assert start.resolve_node("play_song") == start.HELP_SONG
    assert start.resolve_node("play_video") == start.HELP_MOVIE
    for old in ("c_pause", "c_resume", "c_skip", "c_stop", "c_queue"):
        assert start.resolve_node(old) == start.HELP_CONTROL
    assert start.resolve_node("unknown_node") == start.HELP_MAIN
    assert start.resolve_node("main") == start.HELP_MAIN


def test_help_callbacks_within_limit():
    from bot.plugins import start

    for node in start.HELP_NODES:
        for c in cbs(start.help_markup(node)):
            assert c.startswith("h|"), c
            assert len(c.encode()) <= 64, c


def test_support_url_fallback_used_when_none_passed():
    from bot import auth
    from bot.plugins import start

    kb = start.help_markup(start.HELP_MAIN)
    assert any(u == auth._support_cache["url"] for u in urls(kb))
