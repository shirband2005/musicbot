"""دستور /start و پنل راهنما.

سه نسخه‌ی /start (چون دسترسی PV سه‌سطحی است و یک پیام یکسان برای همه گمراه‌کننده بود):
  · کاربر نو  → گام‌های شروع + دکمه‌ی افزودن به گروه
  · مالک      → آمار سریع + میان‌برهای مدیریت
  · کاربر ویژه → تأیید دسترسی + دستورها

راهنما تخت شد: ۹ صفحه‌ی تودرتوی قبلی به ۵ صفحه رسید. پنج زیرصفحه‌ی
«کنترل رسانه» هر کدام فقط یک خط داشتند و برای دیدن «مکث» دو کلیک لازم بود.
بخش «پنل و دکمه‌ها» هم اضافه شد که قبلاً هیچ توضیحی نداشت.

الگوی callback: `h|<node>`
"""
from __future__ import annotations

import logging
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, Message

from bot import auth
from bot import database as db
from bot import ui
from bot.facmd import fa_command

LOGGER = logging.getLogger("musicbot.start")

# یوزرنیم ربات از getMe گرفته و کش می‌شود.
# باگ نسخه‌ی قبلی: لینک «افزودن به گروه» به‌صورت `https://t.me/?startgroup=true`
# هاردکد شده بود — بدون یوزرنیم، یعنی دکمه کاربر را به هیچ‌جا می‌برد.
_bot_username: Optional[str] = None


async def bot_username(client: Client) -> str:
    global _bot_username
    if _bot_username:
        return _bot_username
    try:
        me = await client.get_me()
        _bot_username = me.username or ""
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("get_me: %s", e)
        _bot_username = ""
    return _bot_username


async def add_group_url(client: Client) -> str:
    uname = await bot_username(client)
    return f"https://t.me/{uname}?startgroup=true" if uname else ""


async def pv_url(client: Client, payload: str = "") -> str:
    """لینک PV ربات؛ با payload برای deep link (`?start=buy`)."""
    uname = await bot_username(client)
    if not uname:
        return ""
    return f"https://t.me/{uname}" + (f"?start={payload}" if payload else "")


# ==================================================================
#                            /start
# ==================================================================
async def _start_new_user(client: Client) -> tuple[str, list, InlineKeyboardMarkup]:
    """کاربر تازه: چهار گام شروع. صادقانه می‌گوید اشتراک لازم است."""
    t = ui.Text().title(ui.EMO_HEADPHONE, ui.BASE_HEADPHONE, "موزیک‌پلیر فارسی")
    t.add("آهنگ و فیلم را داخل ویس‌چت گروهت پخش می‌کنم.\n\n")
    t.line(0, "۱. من را به گروهت اضافه کن")
    t.line(1, "۲. در گروه ادمینم کن")
    t.line(2, "۳. ویس‌چت گروه را روشن کن")
    t.emoji(ui.alt_arrow(3)).add(" ۴. بنویس ")
    t.code("پخش اهنگ شادمهر")
    t.add("\n\n")
    t.italic("پخش در گروه به اشتراک فعال نیاز دارد.")

    add_url = await add_group_url(client)
    rows = []
    if add_url:
        rows.append([ui.btn("افزودن به گروه", None, ui.GREEN, None, url=add_url)])
    rows.append([ui.btn("خرید اشتراک", "buy|start", ui.BLUE, ui.EMO_DOWNLOAD)])
    rows.append([ui.btn("راهنما", "h|main", ui.PLAIN, ui.EMO_LIST),
                 ui.btn("پشتیبانی", None, ui.PLAIN, None,
                        url=await auth.resolve_support_url(client))])
    return t.text, t.entities, ui.kb(rows)


async def _start_owner(client: Client) -> tuple[str, list, InlineKeyboardMarkup]:
    """مالک: آمار سریع + میان‌برها. قبلاً همان پیام کاربر نو را می‌دید."""
    t = ui.Text().title(ui.EMO_GEAR, ui.BASE_ARROW, "پنل مالک")

    try:
        groups = len(db.get_chats())
    except Exception:  # noqa: BLE001
        groups = 0
    try:
        subs = len(db.sub_all())
    except Exception:  # noqa: BLE001
        subs = 0
    try:
        pending = len(db.orders_pending())
    except Exception:  # noqa: BLE001
        pending = 0

    t.field(0, "گروه‌های ثبت‌شده", f"{ui.fa(groups)} گروه")
    t.field(1, "اشتراک‌های فعال", f"{ui.fa(subs)} گروه")
    t.field(2, "سفارش در انتظار", ui.fa(pending) if pending else "ندارد")

    rows = [[ui.btn("مدیریت", "adm|main", ui.BLUE, ui.EMO_GEAR)]]
    if pending:
        rows.append([ui.btn(f"سفارش‌های در انتظار ({ui.fa(pending)})",
                            "adm|pending", ui.RED, ui.EMO_BELL)])
    rows.append([ui.btn("اشتراک من", "my|list", ui.PLAIN, ui.EMO_LIST),
                 ui.btn("راهنما", "h|main", ui.PLAIN, None)])
    return t.text, t.entities, ui.kb(rows)


async def _start_special(client: Client) -> tuple[str, list, InlineKeyboardMarkup]:
    """کاربر ویژه: دسترسی‌اش تأیید می‌شود، بدون حرف اشتراک."""
    t = ui.Text().title(ui.EMO_HEADPHONE, ui.BASE_HEADPHONE, "موزیک‌پلیر فارسی")
    t.add("دسترسی ویژه‌ی تو فعال است.\n\n")
    t.emoji(ui.alt_arrow(0)).add(" پخش آهنگ : ")
    t.code("پخش اهنگ <اسم>")
    t.add("\n")
    t.emoji(ui.alt_arrow(1)).add(" پخش فیلم : ")
    t.code("پخش فیلم <اسم>")
    t.add("\n")
    t.emoji(ui.alt_arrow(2)).add(" راهنمای کامل : ")
    t.code("راهنما پلیر")
    t.add("\n")

    add_url = await add_group_url(client)
    rows = []
    if add_url:
        rows.append([ui.btn("افزودن به گروه", None, ui.GREEN, None, url=add_url)])
    rows.append([ui.btn("راهنما", "h|main", ui.PLAIN, ui.EMO_LIST),
                 ui.btn("پشتیبانی", None, ui.PLAIN, None,
                        url=await auth.resolve_support_url(client))])
    return t.text, t.entities, ui.kb(rows)


async def _start_group(client: Client) -> tuple[str, list, InlineKeyboardMarkup]:
    """در گروه کوتاه بماند — جای پیام بلند PV نیست."""
    t = ui.Text().title(ui.EMO_HEADPHONE, ui.BASE_HEADPHONE, "موزیک‌پلیر فارسی")
    t.emoji(ui.alt_arrow(0)).add(" برای پخش بنویس : ")
    t.code("پخش اهنگ <اسم>")
    t.add("\n")
    t.italic("ویس‌چت گروه باید روشن باشد.")
    rows = [[ui.btn("راهنما", "h|main", ui.PLAIN, ui.EMO_LIST)]]
    return t.text, t.entities, ui.kb(rows)


@Client.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    if message.from_user:
        db.add_user(message.from_user.id)
    if message.chat.type.name != "PRIVATE":
        db.add_chat(message.chat.id)
        text, ents, kb = await _start_group(client)
        await message.reply_text(text, entities=ents, reply_markup=kb)
        return

    uid = message.from_user.id if message.from_user else 0

    # deep link: /start buy یا /start renew (از دکمه‌ی پیام‌های خطای گروه)
    parts = (message.text or "").split(maxsplit=1)
    payload = parts[1].strip().lower() if len(parts) > 1 else ""

    if uid == auth.OWNER_ID:
        text, ents, kb = await _start_owner(client)
    elif db.is_special(uid):
        text, ents, kb = await _start_special(client)
    else:
        text, ents, kb = await _start_new_user(client)

    await message.reply_text(text, entities=ents, reply_markup=kb)

    if payload in ("buy", "renew"):
        # جریان خرید در فاز بعدی متصل می‌شود؛ فعلاً کاربر را سرگردان نمی‌گذاریم.
        hint = ui.Text().title(ui.EMO_DOWNLOAD, ui.BASE_ARROW, "خرید اشتراک")
        hint.italic("برای شروع، دکمه‌ی «خرید اشتراک» را بزن.")
        await message.reply_text(hint.text, entities=hint.entities)


# ==================================================================
#                          پنل راهنما
# ==================================================================
# ۵ صفحه (قبلاً ۹): منوی اصلی + پخش آهنگ + پخش فیلم + کنترل + پنل و دکمه‌ها
HELP_MAIN = "main"
HELP_SONG = "song"
HELP_MOVIE = "movie"
HELP_CONTROL = "control"
HELP_PANEL = "panel"

HELP_NODES = (HELP_MAIN, HELP_SONG, HELP_MOVIE, HELP_CONTROL, HELP_PANEL)

# گره‌های نسخه‌ی قبلی → گره‌های جدید (راهنماهای ماندهٔ گروه‌ها نباید بشکنند)
LEGACY_NODES = {
    "play_song": HELP_SONG,
    "play_video": HELP_MOVIE,
    "c_pause": HELP_CONTROL,
    "c_resume": HELP_CONTROL,
    "c_skip": HELP_CONTROL,
    "c_stop": HELP_CONTROL,
    "c_queue": HELP_CONTROL,
}


def resolve_node(node: str) -> str:
    """گره‌ی معتبر جدید را برمی‌گرداند (با نگاشت گره‌های قدیمی)."""
    if node in HELP_NODES:
        return node
    return LEGACY_NODES.get(node, HELP_MAIN)


def _cmd(t: ui.Text, i: int, label: str, *commands: str) -> ui.Text:
    """یک خط راهنما: برچسب + دستورها با فرمت code (کپی با یک لمس)."""
    t.emoji(ui.alt_arrow(i)).add(f" {label} : ")
    for j, c in enumerate(commands):
        if j:
            t.add("  ·  ")
        t.code(c)
    return t.add("\n")


def _help_main() -> ui.Text:
    t = ui.Text().title(ui.EMO_LIST, ui.BASE_ARROW, "راهنما")
    t.line(0, "پخش آهنگ و فیلم داخل ویس‌چت گروه")
    t.line(1, "کنترل کامل با دکمه‌های پنل")
    t.add("\n")
    t.italic("یکی از بخش‌ها را انتخاب کن:")
    return t


def _help_song() -> ui.Text:
    t = ui.Text().title(ui.EMO_HEADPHONE, ui.BASE_HEADPHONE, "پخش آهنگ")
    _cmd(t, 0, "با اسم", "پخش اهنگ شادمهر دیوانه")
    _cmd(t, 1, "با لینک", "پخش اهنگ <لینک یوتیوب>")
    _cmd(t, 2, "از ساوندکلاد", "پخش ساوند کلاد <اسم>")
    _cmd(t, 3, "تصادفی از آرشیو", "پخش رندوم")
    _cmd(t, 4, "فایل تلگرام", "روی فایل صوتی ریپلای کن و بنویس «پخش»")
    t.add("\n")
    t.italic("چند آهنگ پشت‌سرهم بفرست تا صف بسازی.")
    return t


def _help_movie() -> ui.Text:
    t = ui.Text().title(ui.EMO_MOVIE, ui.BASE_MOVIE, "پخش فیلم")
    _cmd(t, 0, "با اسم", "پخش فیلم هزارپا")
    _cmd(t, 1, "با لینک", "پخش فیلم <لینک یوتیوب>")
    _cmd(t, 2, "فایل تلگرام", "روی ویدیو ریپلای کن و بنویس «پخش فیلم»")
    t.add("\n")
    t.italic("فیلم صف ندارد؛ هر بار یک فیلم پخش می‌شود.")
    return t


def _help_control() -> ui.Text:
    """پنج زیرصفحه‌ی قبلی در یک صفحه — هر کدام فقط یک خط بودند."""
    t = ui.Text().title(ui.EMO_GEAR, ui.BASE_ARROW, "کنترل پخش")
    _cmd(t, 0, "توقف موقت", "مکث", "توقف")
    _cmd(t, 1, "ادامه", "ادامه", "شروع")
    _cmd(t, 2, "بعدی", "بعدی", "اهنگ بعدی", "رد")
    _cmd(t, 3, "پایان پخش", "خروج", "اتمام")
    _cmd(t, 4, "لیست پخش", "لیست", "صف")
    _cmd(t, 5, "حالت پخش", "حالت پخش")
    _cmd(t, 6, "پلتفرم", "پلتفرم")
    t.add("\n")
    t.italic("همه‌ی این‌ها با دکمه‌های پنل هم انجام می‌شوند.")
    return t


def _help_panel() -> ui.Text:
    """بخش تازه — پنل ده دکمه دارد و قبلاً هیچ توضیحی نداشت."""
    t = ui.Text().title(ui.EMO_HEADPHONE, ui.BASE_HEADPHONE, "پنل و دکمه‌ها")
    t.line(0, "نوار زمان : زمان گذشته، پیشرفت، مدت کل. کلیک = تازه‌سازی")
    t.line(1, "قبلی و بعدی : جابه‌جایی در صف")
    t.line(2, "مکث و توقف : توقف موقت یا پایان پخش")
    t.line(3, "صدا : کم و زیاد کردن، دکمه‌ی وسط بیصدا می‌کند")
    t.line(4, "لیست پخش : صف را می‌بینی، روی شماره بزنی همان پخش می‌شود")
    t.line(5, "حالت پخش : صف، تکرار، یا رندوم")
    t.line(6, "تایمر خواب : پس از مدت انتخابی پخش قطع می‌شود")
    t.line(7, "پلتفرم : یوتیوب، ساوندکلاد، یا هر دو")
    t.line(8, "دریافت رسانه : فایل آهنگ در حال پخش را می‌فرستد")
    return t


_BUILDERS = {
    HELP_MAIN: _help_main,
    HELP_SONG: _help_song,
    HELP_MOVIE: _help_movie,
    HELP_CONTROL: _help_control,
    HELP_PANEL: _help_panel,
}


def help_content(node: str):
    """متن + entities یک صفحه‌ی راهنما."""
    t = _BUILDERS[resolve_node(node)]()
    return t.text, t.entities


def help_text(node: str) -> str:
    return help_content(node)[0]


def help_entities(node: str):
    return help_content(node)[1]


def help_markup(node: str, support_url: Optional[str] = None) -> InlineKeyboardMarkup:
    """کیبورد صفحه‌ی راهنما. رنگ فقط روی پشتیبانی (آبی) و بستن (قرمز)."""
    node = resolve_node(node)
    link = support_url or auth._support_cache["url"]

    if node == HELP_MAIN:
        rows = [
            [ui.btn("پخش آهنگ", f"h|{HELP_SONG}", ui.PLAIN, ui.EMO_HEADPHONE),
             ui.btn("پخش فیلم", f"h|{HELP_MOVIE}", ui.PLAIN, ui.EMO_MOVIE)],
            [ui.btn("کنترل پخش", f"h|{HELP_CONTROL}", ui.PLAIN, ui.EMO_GEAR),
             ui.btn("پنل و دکمه‌ها", f"h|{HELP_PANEL}", ui.PLAIN, ui.EMO_LIST)],
            [ui.btn("پشتیبانی", None, ui.BLUE, None, url=link)],
            [ui.btn("بستن راهنما", "h|close", ui.RED, ui.EMO_CLOSE)],
        ]
    else:
        rows = [
            [ui.btn("بازگشت", f"h|{HELP_MAIN}", ui.PLAIN, ui.EMO_BACK),
             ui.btn("بستن راهنما", "h|close", ui.RED, ui.EMO_CLOSE)],
        ]
    return ui.kb(rows)


@Client.on_message(fa_command(["راهنما پلیر", "راهنما اهنگ", "راهنما آهنگ",
                              "راهنما"]))
async def help_cmd(client: Client, message: Message):
    url = await auth.resolve_support_url(client)
    text, ents = help_content(HELP_MAIN)
    await message.reply_text(text, entities=ents,
                             reply_markup=help_markup(HELP_MAIN, url))
