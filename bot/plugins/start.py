"""دستورات /start و راهنما (راهنما پلیر) با پنل چندسطحی."""
from pyrogram import Client, enums, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import database as db
from bot.facmd import fa_command

# رنگ دکمه‌های راهنما
_BLUE = enums.ButtonStyle.PRIMARY
_RED = enums.ButtonStyle.DANGER
_GREEN = enums.ButtonStyle.SUCCESS

# دکمه پشتیبانی به پروفایل مالک (با آیدی عددی) وصل می‌شود
SUPPORT_USERNAME = "tg://user?id=8406519786"

START_TEXT = (
    "🎵 **سلام! به موزیک‌پلیر فارسی خوش اومدی.**\n\n"
    "من می‌تونم آهنگ و ویدیو رو مستقیم داخل ویس‌چت گروه پخش کنم.\n\n"
    "منو رو به گروهت اضافه کن، ادمینم کن و ویس‌چت رو روشن کن.\n"
    "برای دیدن دستورها بنویس: `راهنما پلیر`"
)


def _start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📖 راهنما", callback_data="h|main", style=_GREEN)],
            [InlineKeyboardButton("➕ افزودن به گروه", url="https://t.me/?startgroup=true", style=_BLUE)],
        ]
    )


@Client.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    if message.from_user:
        db.add_user(message.from_user.id)
    if message.chat.type.name != "PRIVATE":
        db.add_chat(message.chat.id)
    await message.reply_text(START_TEXT, reply_markup=_start_kb())


# =====================  متن‌ها و کیبوردهای راهنما  =====================
# الگوی callback: 'h|<node>'

HELP_NODES = {
    "main": {
        "text": "📖 **راهنما**\n\nیکی از بخش‌ها را انتخاب کن:",
        "buttons": [
            [("🎵 پخش آهنگ", "h|play_song"), ("🎬 پخش فیلم", "h|play_video")],
            [("🎛 کنترل رسانه", "h|control")],
            [("💬 پشتیبانی", "url|" + SUPPORT_USERNAME)],
        ],
    },
    "play_song": {
        "text": (
            "🎵 **راهنما: پخش آهنگ**\n\n"
            "`پخش اهنگ` + اسم آهنگ\n\n"
            "مثال:\n`پخش اهنگ شادمهر`"
        ),
        "buttons": [
            [("❌ بستن راهنما", "h|close"), ("🔙 برگشت", "h|main")],
        ],
    },
    "play_video": {
        "text": (
            "🎬 **راهنما: پخش فیلم**\n\n"
            "`پخش فیلم` + اسم فیلم\n\n"
            "مثال:\n`پخش فیلم هزارپا`"
        ),
        "buttons": [
            [("❌ بستن راهنما", "h|close"), ("🔙 برگشت", "h|main")],
        ],
    },
    "control": {
        "text": "🎛 **دستورات کنترل**\n\nیکی از دستورها را انتخاب کن:",
        "buttons": [
            [("⏸ توقف رسانه", "h|c_pause"), ("▶️ ادامه رسانه", "h|c_resume")],
            [("⏭ رسانه بعدی", "h|c_skip"), ("⏹ اتمام پخش", "h|c_stop")],
            [("📃 لیست پخش", "h|c_queue")],
            [("❌ بستن پنل", "h|close"), ("🔙 برگشت", "h|main")],
        ],
    },
    "c_pause": {
        "text": "⏸ **دستورات توقف رسانه:**\n\n`مکث`  -  `توقف`",
        "buttons": [[("❌ بستن پنل", "h|close"), ("🔙 برگشت", "h|control")]],
    },
    "c_resume": {
        "text": "▶️ **دستورات ادامه پخش رسانه:**\n\n`ادامه`  -  `شروع`",
        "buttons": [[("❌ بستن پنل", "h|close"), ("🔙 برگشت", "h|control")]],
    },
    "c_skip": {
        "text": "⏭ **دستورات پخش رسانه بعدی:**\n\n`بعدی`  -  `اهنگ بعدی`  -  `رد`",
        "buttons": [[("❌ بستن پنل", "h|close"), ("🔙 برگشت", "h|control")]],
    },
    "c_stop": {
        "text": "⏹ **دستورات اتمام پخش رسانه:**\n\n`خروج`  -  `اتمام`",
        "buttons": [[("❌ بستن پنل", "h|close"), ("🔙 برگشت", "h|control")]],
    },
    "c_queue": {
        "text": "📃 **دستورات لیست پخش:**\n\n`لیست`  -  `لیست پخش`\n`صف`  -  `صف پخش`",
        "buttons": [[("❌ بستن پنل", "h|close"), ("🔙 برگشت", "h|control")]],
    },
}


def help_markup(node: str) -> InlineKeyboardMarkup:
    rows = []
    for row in HELP_NODES[node]["buttons"]:
        btn_row = []
        for label, data in row:
            if data.startswith("url|"):
                btn_row.append(InlineKeyboardButton(label, url=data[4:], style=_BLUE))
            elif data == "h|close":
                # دکمه‌های بستن پنل/راهنما → قرمز
                btn_row.append(InlineKeyboardButton(label, callback_data=data, style=_RED))
            elif label.startswith("🔙") or data in ("h|main", "h|control"):
                # دکمه‌های بازگشت → آبی
                btn_row.append(InlineKeyboardButton(label, callback_data=data, style=_BLUE))
            else:
                # سایر دکمه‌های ناوبری راهنما → آبی
                btn_row.append(InlineKeyboardButton(label, callback_data=data, style=_BLUE))
        rows.append(btn_row)
    return InlineKeyboardMarkup(rows)


def help_text(node: str) -> str:
    return HELP_NODES[node]["text"]


# --- دستور «راهنما پلیر / راهنما اهنگ / راهنما آهنگ» ---
@Client.on_message(fa_command(["راهنما پلیر", "راهنما اهنگ", "راهنما آهنگ"]))
async def help_cmd(client: Client, message: Message):
    await message.reply_text(help_text("main"), reply_markup=help_markup("main"))
