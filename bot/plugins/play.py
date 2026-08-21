"""دستورات پخش با معادل‌های فارسی چندکلمه‌ای.

نگاشت دستورات (با/بدون پیشوند / . ! ،):
  پخش اهنگ / پخش آهنگ        → پخش آهنگ
  پخش فیلم / پخش ویدیو        → پخش ویدیو
  مکث / توقف                  → مکث
  ادامه / شروع                → ادامه
  رد / بعدی / اهنگ بعدی       → آهنگ بعدی
  خروج / اتمام                → توقف کامل
  صف / صف پخش / لیست / لیست پخش → نمایش صف
"""
import logging
import os

from pyrogram import Client
from pyrogram.types import Message

import config
from bot import auth
from bot import database as db
from bot import group_config as gc
from bot import logs
from bot import platform_pref
from bot import player
from bot import queue as q
from bot import soundcloud
from bot import youtube
from bot.facmd import fa_command
from bot.queue import Track

LOGGER = logging.getLogger("musicbot.play")

GROUP_ONLY = "این دستور فقط داخل گروه (با ویس‌چت فعال) کار می‌کند."
PLAYER_OFF = "🔇 موزیک‌پلیر در این گروه خاموش است."


async def _gate(client: Client, message: Message) -> bool:
    """گارد مشترک: گروه + دسترسی گروه (روشن بودن) + دسترسی کاربر."""
    if message.chat.type.name == "PRIVATE":
        # در خصوصی فقط مالک/ویژه
        if not await auth.guard_message(client, message):
            return False
        await message.reply_text(GROUP_ONLY)
        return False
    # ۱) اول: آیا گروه فعال است؟ (خاموش → «گروه دسترسی ندارد»)
    if not gc.is_enabled(message.chat.id):
        url = await auth.resolve_support_url(client)
        await message.reply_text(auth.DENY_GROUP, reply_markup=auth.support_kb(url))
        return False
    # ۲) سپس: آیا این کاربر دسترسی دارد؟ (نه → «شما دسترسی ندارید»)
    if not await auth.guard_message(client, message):
        return False
    return True


def _requester_name(message: Message) -> str:
    u = message.from_user
    if not u:
        return "ناشناس"
    return u.first_name or (u.username and "@" + u.username) or str(u.id)


async def _play_track(client: Client, message: Message, info: dict, is_video: bool, query: str, status):
    """یک نتیجه‌ی آماده را پخش/به صف اضافه می‌کند و پیام مناسب می‌دهد."""
    if not info.get("stream_url"):
        await status.edit_text("❌ لینک قابل پخشی پیدا نشد.")
        return

    if info.get("duration") and info["duration"] > config.DURATION_LIMIT:
        await status.edit_text(
            f"❌ طول محتوا ({info['duration_text']}) بیش از حد مجاز است."
        )
        return

    source = info.get("source", "youtube")
    track = Track(
        title=info["title"],
        stream_url=info["stream_url"],
        webpage_url=info["webpage_url"],
        duration=info.get("duration") or 0,
        duration_text=info["duration_text"],
        thumbnail=info.get("thumbnail"),
        requester=_requester_name(message),
        is_video=is_video,
        query=query,
        video_id=info.get("id") or "",
        source=source,
    )
    # اگر منبع آرشیو است، رکورد آماده را به track بده تا دوباره جست‌وجو نشود
    if source == "archive" and info.get("archive_rec"):
        track._archive_rec = info["archive_rec"]

    try:
        with logs.stage("CALL_PLAY", message.chat.id, title=track.title, video=is_video):
            pos = await player.play_or_queue(message.chat.id, track)
    except Exception as e:  # noqa: BLE001
        LOGGER.error("playback error: %s", e)
        err = str(e)
        if "GROUPCALL" in err.upper() or "no active" in err.lower():
            await status.edit_text("❌ ابتدا ویس‌چت گروه را روشن کنید.")
        else:
            await status.edit_text(f"❌ خطا در پخش:\n`{e}`")
        return

    if pos == 0:
        await status.delete()  # پنل پخش خودش ارسال می‌شود
    else:
        await status.edit_text(
            f"✅ به صف اضافه شد (موقعیت {pos}):\n**{track.title}**\n⏱ {track.duration_text}"
        )

    # لاگ پخش در کانال (بدون بلاک کردن پاسخ)
    try:
        import asyncio
        from bot import channel
        chat_title = getattr(message.chat, "title", "") or str(message.chat.id)
        asyncio.create_task(channel.log(
            f"🎵 **پخش جدید**\n"
            f"• آهنگ: {track.title}\n"
            f"• منبع: {track.source}\n"
            f"• گروه: {chat_title}\n"
            f"• توسط: {_requester_name(message)}"
        ))
    except Exception:  # noqa: BLE001
        pass


async def _search(chat_id: int, query: str, is_video: bool, status):
    """جست‌وجوی هوشمند طبق ترجیح پلتفرم (با اعمال قفل گروه). info یا None.

    منطق (فقط برای صوت؛ ویدیو مستقیم یوتیوب):
    - both: یوتیوب اسمِ دقیق → آرشیو با video_id/اسم → ساوندکلاد با اسم دقیق →
            ساوندکلاد با دستور اصلی → یوتیوب دانلود (کیفیت پایین)
    - youtube: یوتیوب اسمِ دقیق → آرشیو → ساوندکلاد با اسم دقیق → یوتیوب دانلود
    - soundcloud: مستقیم ساوندکلاد با دستور اصلی
    آرشیو در _ensure_local_file هنگام پخش هم دوباره چک می‌شود؛ اینجا سریع‌ترین
    منبع را انتخاب می‌کنیم.
    """
    from bot import channel
    mode = platform_pref.effective(chat_id)

    # ویدیو: فقط یوتیوب
    if is_video:
        try:
            return await youtube.get_media(query, video=True)
        except Exception as e:  # noqa: BLE001
            LOGGER.warning("youtube video error: %s", e)
            friendly = logs.classify_youtube_error(str(e))
            await status.edit_text(f"❌ {friendly}\n\n`{str(e)[:300]}`")
            return None

    # فقط ساوندکلاد: مستقیم همان دستور
    if mode == platform_pref.SOUNDCLOUD:
        sc = await soundcloud.search(query)
        if sc and sc.get("stream_url"):
            return sc
        await status.edit_text("❌ در ساوند کلاد پیدا نشد.")
        return None

    # both یا youtube: اول اسم دقیق را از یوتیوب بگیر (سبک، بدون دانلود)
    exact_title = ""
    yt_vid = ""
    try:
        meta = await youtube.search_title(query)
        exact_title = (meta.get("title") or "").strip()
        yt_vid = meta.get("id") or ""
    except Exception as e:  # noqa: BLE001
        LOGGER.debug("yt title: %s", e)

    # چک آرشیو با video_id یا اسم دقیق (اگر بود، پخش از تلگرام بدون دانلود)
    if exact_title or yt_vid:
        try:
            rec = channel.archive_lookup(video_id=yt_vid, query=(exact_title or query))
            if rec:
                await status.edit_text(f"⚡️ از آرشیو: {rec.get('title') or exact_title}")
                return {
                    "id": yt_vid or ("q:" + (exact_title or query)),
                    "title": rec.get("title") or exact_title or query,
                    "duration": rec.get("duration") or 0,
                    "duration_text": _fmt_dur(int(rec.get("duration") or 0)),
                    "stream_url": "archive", "webpage_url": "",
                    "thumbnail": None, "source": "archive",
                    "archive_rec": rec,
                }
        except Exception as e:  # noqa: BLE001
            LOGGER.debug("archive lookup: %s", e)

    # ساوندکلاد با اسم دقیق، بعد با دستور اصلی
    sc_queries = [exact_title, query] if exact_title and exact_title != query else [query]
    for scq in sc_queries:
        sc = await soundcloud.search(scq)
        if sc and sc.get("stream_url"):
            return sc

    # حالت only-youtube یا هر دو: در نهایت یوتیوب (دانلود با کیفیت پایین)
    try:
        info = await youtube.get_media(query, video=False)
        return info
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("youtube error: %s", e)
        friendly = logs.classify_youtube_error(str(e))
        await status.edit_text(f"❌ {friendly}\n\n`{str(e)[:300]}`")
        return None


async def _handle_play(client: Client, message: Message, is_video: bool):
    if not await _gate(client, message):
        return

    # اگر روی یک فایل صوتی/ویدیویی تلگرام ریپلای شده، مستقیم آن را پخش کن
    if await _play_telegram_file(client, message):
        return

    query = " ".join(message.command[1:]).strip()
    if not query and message.reply_to_message and message.reply_to_message.text:
        query = message.reply_to_message.text.strip()
    if not query:
        example = "پخش فیلم هزارپا" if is_video else "پخش اهنگ شادمهر"
        await message.reply_text(f"نام {'فیلم' if is_video else 'آهنگ'} یا لینک را بده.\nمثال: `{example}`")
        return

    db.add_chat(message.chat.id)
    status = await message.reply_text("🔎 در حال جست‌وجو...")
    info = await _search(message.chat.id, query, is_video, status)
    if info is None:
        return
    await _play_track(client, message, info, is_video, query, status)


# --- ریپلای روی فایل صوتی/ویدیویی: افزودن به صف یا پخش ---
# آستانه: فایل‌های حجیم (بالای این حد) به‌جای دانلود، مستقیم از تلگرام استریم می‌شوند.
_TG_STREAM_THRESHOLD = int(os.environ.get("TG_STREAM_THRESHOLD_MB", "50")) * 1024 * 1024


async def _play_telegram_file(client: Client, message: Message) -> bool:
    """اگر روی یک فایل صوتی/ویدیویی ریپلای شده، آن را پخش/به صف می‌کند. True اگر انجام شد.

    - فایل کوچک (زیر آستانه): دانلود و پخش از فایل محلی (پایدار).
    - فایل حجیم (بالای آستانه): استریم مستقیم توسط یوزربات کمکی (بدون دانلود کامل).
    """
    reply = message.reply_to_message
    media = None
    if reply:
        media = reply.audio or reply.voice or reply.video or reply.document
    if not media:
        return False

    db.add_chat(message.chat.id)
    size = getattr(media, "file_size", 0) or 0
    title = getattr(media, "title", None) or getattr(media, "file_name", None) or "فایل تلگرام"
    dur = getattr(media, "duration", 0) or 0
    is_video = bool(reply.video or (reply.document and "video" in (getattr(media, "mime_type", "") or "")))

    # --- مسیر استریم مستقیم برای فایل حجیم (بدون دانلود) ---
    if size >= _TG_STREAM_THRESHOLD:
        # استریم ویدیو/فیلم حجیم فقط برای اشتراک حرفه‌ای (pro)
        from bot import subscription as sub
        if is_video and not sub.is_pro(message.chat.id):
            await message.reply_text(
                "🎬 استریم فیلم حجیم فقط با اشتراک **حرفه‌ای** فعال است.\n"
                "برای ارتقا، در خصوصی ربات «🛒 خرید اشتراک» را بزن."
            )
            return True
        status = await message.reply_text(
            f"📡 فایل حجیم ({size // (1024*1024)} مگ) — استریم مستقیم...\n"
            "بدون دانلود، همه با اینترنت سرور."
        )
        track = Track(
            title=title, stream_url="", webpage_url="",
            duration=dur, duration_text=_fmt_dur(dur), thumbnail=None,
            requester=_requester_name(message), is_video=True,
            query="", video_id="", source="telegram_stream",
            tg_chat_id=message.chat.id, tg_msg_id=reply.id,
        )
        try:
            with logs.stage("CALL_STREAM", message.chat.id, title=title):
                pos = await player.play_or_queue(message.chat.id, track)
        except Exception as e:  # noqa: BLE001
            LOGGER.error("tg stream playback error: %s", e)
            err = str(e)
            if "GROUPCALL" in err.upper() or "no active" in err.lower():
                await status.edit_text("❌ ابتدا ویس‌چت گروه را روشن کنید.")
            else:
                await status.edit_text(f"❌ خطا در استریم:\n`{str(e)[:200]}`")
            return True
        if pos == 0:
            await status.delete()
        else:
            await status.edit_text(f"✅ به صف اضافه شد (موقعیت {pos}):\n**{title}**")
        return True

    # --- مسیر دانلود برای فایل کوچک ---
    status = await message.reply_text("⬇️ در حال آماده‌سازی فایل...")
    try:
        os.makedirs(player.DOWNLOAD_DIR, exist_ok=True)
        path = await client.download_media(reply, file_name=os.path.join(player.DOWNLOAD_DIR, ""))
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("tg media download failed: %s", e)
        await status.edit_text(f"❌ دانلود فایل ناموفق:\n`{str(e)[:200]}`")
        return True

    track = Track(
        title=title, stream_url=path, webpage_url="",
        duration=dur, duration_text=_fmt_dur(dur), thumbnail=None,
        requester=_requester_name(message), is_video=is_video,
        query="", video_id="", source="telegram",
    )
    track.local_path = path
    try:
        with logs.stage("CALL_PLAY", message.chat.id, title=title, video=is_video):
            pos = await player.play_or_queue(message.chat.id, track)
    except Exception as e:  # noqa: BLE001
        LOGGER.error("playback error: %s", e)
        err = str(e)
        if "GROUPCALL" in err.upper() or "no active" in err.lower():
            await status.edit_text("❌ ابتدا ویس‌چت گروه را روشن کنید.")
        else:
            await status.edit_text(f"❌ خطا در پخش:\n`{e}`")
        return True
    if pos == 0:
        await status.delete()
    else:
        await status.edit_text(f"✅ به صف اضافه شد (موقعیت {pos}):\n**{title}**")
    return True


def _fmt_dur(seconds: int) -> str:
    if not seconds:
        return "نامشخص"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# --- «پخش» تنها (ریپلای روی فایل تلگرام، یا «پخش <اسم>») ---
# نکته: این هندلر «پخش» را می‌گیرد و چون قبل از play_cmd ثبت می‌شود،
# «پخش اهنگ/فیلم ...» هم به اینجا می‌رسد؛ پس خودمان کلیدواژه را تشخیص می‌دهیم.
_VIDEO_KW = {"فیلم", "ویدیو", "ویدئو", "کلیپ"}
_AUDIO_KW = {"اهنگ", "آهنگ", "موزیک", "موسیقی", "صدا"}


@Client.on_message(fa_command(["پخش", "بذار", "بنداز"]))
async def bare_play_cmd(client: Client, message: Message):
    if not await _gate(client, message):
        return

    # ۰) «پخش رندوم» → حالت رندوم و پخش تصادفی (قبل از هر چیز)
    args0 = message.command[1:]
    if args0 and _norm(args0[0]) == "رندوم":
        await _start_random(client, message)
        return

    # ۱) ریپلای روی فایل صوتی/ویدیویی تلگرام → مستقیم پخش
    if await _play_telegram_file(client, message):
        return

    # ۲) تشخیص «پخش اهنگ/فیلم <اسم>» و جداکردن نوع + پاک‌سازی کوئری
    args = message.command[1:]
    is_video = False
    if args and args[0] in _VIDEO_KW:
        is_video = True
        args = args[1:]
    elif args and args[0] in _AUDIO_KW:
        args = args[1:]

    query = " ".join(args).strip()
    if not query and message.reply_to_message and message.reply_to_message.text:
        query = message.reply_to_message.text.strip()
    if not query:
        await message.reply_text("نام آهنگ/فیلم یا لینک را بده، یا روی یک فایل ریپلای کن.\nمثال: `پخش اهنگ شادمهر`")
        return

    db.add_chat(message.chat.id)
    status = await message.reply_text("🔎 در حال جست‌وجو...")
    info = await _search(message.chat.id, query, is_video, status)
    if info is None:
        return
    await _play_track(client, message, info, is_video, query, status)


# --- پخش آهنگ: «پخش اهنگ» / «پخش آهنگ» ---
@Client.on_message(fa_command(["پخش اهنگ", "پخش آهنگ"]))
async def play_cmd(client: Client, message: Message):
    await _handle_play(client, message, is_video=False)


# --- پخش ویدیو: «پخش فیلم» / «پخش ویدیو» ---
@Client.on_message(fa_command(["پخش فیلم", "پخش ویدیو"]))
async def vplay_cmd(client: Client, message: Message):
    await _handle_play(client, message, is_video=True)


# --- شروع پخش رندوم: حالت را رندوم کن و فوراً یک آهنگ تصادفی پخش کن ---
def _norm(w: str) -> str:
    from bot.facmd import normalize
    return normalize(w)


async def _start_random(client: Client, message: Message):
    from bot import group_config as gc
    gc.set_mode(message.chat.id, gc.MODE_RANDOM)
    db.add_chat(message.chat.id)
    status = await message.reply_text("🔀 پخش رندوم روشن شد — در حال انتخاب آهنگ...")
    try:
        with logs.stage("RANDOM_PLAY", message.chat.id):
            await player.play_random(message.chat.id)
    except Exception as e:  # noqa: BLE001
        LOGGER.error("random play error: %s", e)
        err = str(e)
        if "GROUPCALL" in err.upper() or "no active" in err.lower():
            await status.edit_text("❌ ابتدا ویس‌چت گروه را روشن کنید.")
        else:
            await status.edit_text(f"❌ خطا در پخش رندوم:\n`{str(e)[:200]}`")
        return
    if q.now_playing(message.chat.id) is None:
        await status.edit_text("❌ آرشیو خالی است. اول چند آهنگ به کانال آرشیو اضافه/پخش کن.")
    else:
        await status.delete()


@Client.on_message(fa_command(["شروع پخش رندوم", "پخش رندوم", "رندوم"]))
async def random_cmd(client: Client, message: Message):
    if not await _gate(client, message):
        return
    await _start_random(client, message)


# --- مکث: «مکث» / «توقف موقت» (فقط نگه‌داشتن موقت، در کال می‌ماند) ---
@Client.on_message(fa_command(["مکث", "توقف موقت"]))
async def pause_cmd(client: Client, message: Message):
    if not await _gate(client, message):
        return
    track = q.now_playing(message.chat.id)
    if not track:
        await message.reply_text("چیزی در حال پخش نیست.")
        return
    from bot import call
    await call.pause(message.chat.id)
    track.mark_paused()
    await player.refresh_panel(message.chat.id)
    await message.reply_text("⏸ موقتاً متوقف شد. برای ادامه بنویس «ادامه».")


# --- ادامه: «ادامه» / «شروع» ---
@Client.on_message(fa_command(["ادامه", "شروع"]))
async def resume_cmd(client: Client, message: Message):
    if not await _gate(client, message):
        return
    track = q.now_playing(message.chat.id)
    if not track:
        await message.reply_text("چیزی در حال پخش نیست.")
        return
    from bot import call
    await call.resume(message.chat.id)
    track.mark_resumed()
    await player.refresh_panel(message.chat.id)
    await message.reply_text("▶️ ادامه یافت.")


# --- آهنگ بعدی: «رد» / «بعدی» / «آهنگ بعدی» / «اهنگ بعدی» ---
@Client.on_message(fa_command(["اهنگ بعدی", "آهنگ بعدی", "بعدی", "رد"]))
async def skip_cmd(client: Client, message: Message):
    if not await _gate(client, message):
        return
    if q.now_playing(message.chat.id) is None:
        await message.reply_text("چیزی در حال پخش نیست.")
        return
    nxt = await player.skip(message.chat.id)
    if nxt:
        await message.reply_text(f"⏭ رد شد. پخش بعدی:\n**{nxt.title}**")
    else:
        await message.reply_text("⏹ صف خالی شد. از کال خارج شدم.")


# --- توقف کامل: «توقف» / «خروج» / «اتمام» / «قطع» (از کال خارج می‌شود) ---
@Client.on_message(fa_command(["توقف", "خروج", "اتمام", "قطع"]))
async def stop_cmd(client: Client, message: Message):
    if not await _gate(client, message):
        return
    if q.now_playing(message.chat.id) is None:
        await message.reply_text("چیزی در حال پخش نیست.")
        return
    await player.stop(message.chat.id)
    await message.reply_text("⏹ پخش متوقف و از کال خارج شدم.")


# --- صف: «صف» / «صف پخش» / «لیست» / «لیست پخش» ---
@Client.on_message(fa_command(["صف پخش", "لیست پخش", "صف", "لیست"]))
async def queue_cmd(client: Client, message: Message):
    if not await _gate(client, message):
        return
    cur = q.now_playing(message.chat.id)
    if not cur:
        await message.reply_text("صف خالی است.")
        return
    lines = [f"🎧 **در حال پخش:** {cur.title} — `{cur.duration_text}`", ""]
    items = list(q.get_queue(message.chat.id))
    if items:
        lines.append("**در صف:**")
        for i, t in enumerate(items, 1):
            lines.append(f"{i}. {t.title} — `{t.duration_text}` ({t.requester})")
    else:
        lines.append("صف بعدی خالی است.")
    await message.reply_text("\n".join(lines))
