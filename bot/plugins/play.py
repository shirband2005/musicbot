"""دستورات پخش: /play, /vplay, /pause, /resume, /skip, /stop, /queue."""
import logging

from pyrogram import Client, filters
from pyrogram.types import Message

import config
from bot import database as db
from bot import player
from bot import queue as q
from bot import youtube
from bot.queue import Track

LOGGER = logging.getLogger("musicbot.play")

GROUP_ONLY = "این دستور فقط داخل گروه (با ویس‌چت فعال) کار می‌کند."


def _requester_name(message: Message) -> str:
    u = message.from_user
    if not u:
        return "ناشناس"
    return u.first_name or (u.username and "@" + u.username) or str(u.id)


async def _handle_play(client: Client, message: Message, is_video: bool):
    if message.chat.type.name == "PRIVATE":
        await message.reply_text(GROUP_ONLY)
        return

    query = " ".join(message.command[1:]).strip()
    if not query and message.reply_to_message and message.reply_to_message.text:
        query = message.reply_to_message.text.strip()
    if not query:
        cmd = "/vplay" if is_video else "/play"
        await message.reply_text(f"نام آهنگ یا لینک را بده.\nمثال: `{cmd} نام آهنگ`")
        return

    db.add_chat(message.chat.id)
    status = await message.reply_text("🔎 در حال جست‌وجو...")

    try:
        info = await youtube.get_media(query, video=is_video)
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("youtube error: %s", e)
        await status.edit_text(f"❌ خطا در پیدا کردن محتوا:\n`{e}`")
        return

    if not info.get("stream_url"):
        await status.edit_text("❌ لینک قابل پخشی پیدا نشد.")
        return

    if info.get("duration") and info["duration"] > config.DURATION_LIMIT:
        await status.edit_text(
            f"❌ طول محتوا ({info['duration_text']}) بیش از حد مجاز است."
        )
        return

    track = Track(
        title=info["title"],
        stream_url=info["stream_url"],
        webpage_url=info["webpage_url"],
        duration=info.get("duration") or 0,
        duration_text=info["duration_text"],
        thumbnail=info.get("thumbnail"),
        requester=_requester_name(message),
        is_video=is_video,
    )

    try:
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


@Client.on_message(filters.command(["play", "پخش"]))
async def play_cmd(client: Client, message: Message):
    await _handle_play(client, message, is_video=False)


@Client.on_message(filters.command(["vplay", "ویدیو"]))
async def vplay_cmd(client: Client, message: Message):
    await _handle_play(client, message, is_video=True)


@Client.on_message(filters.command(["pause", "مکث"]))
async def pause_cmd(client: Client, message: Message):
    track = q.now_playing(message.chat.id)
    if not track:
        await message.reply_text("چیزی در حال پخش نیست.")
        return
    from bot import call
    await call.pause(message.chat.id)
    track.mark_paused()
    await player.refresh_panel(message.chat.id)
    await message.reply_text("⏸ متوقف شد.")


@Client.on_message(filters.command(["resume", "ادامه"]))
async def resume_cmd(client: Client, message: Message):
    track = q.now_playing(message.chat.id)
    if not track:
        await message.reply_text("چیزی در حال پخش نیست.")
        return
    from bot import call
    await call.resume(message.chat.id)
    track.mark_resumed()
    await player.refresh_panel(message.chat.id)
    await message.reply_text("▶️ ادامه یافت.")


@Client.on_message(filters.command(["skip", "رد", "بعدی"]))
async def skip_cmd(client: Client, message: Message):
    if q.now_playing(message.chat.id) is None:
        await message.reply_text("چیزی در حال پخش نیست.")
        return
    nxt = await player.skip(message.chat.id)
    if nxt:
        await message.reply_text(f"⏭ رد شد. پخش بعدی:\n**{nxt.title}**")
    else:
        await message.reply_text("⏹ صف خالی شد. از کال خارج شدم.")


@Client.on_message(filters.command(["stop", "توقف", "end"]))
async def stop_cmd(client: Client, message: Message):
    if q.now_playing(message.chat.id) is None:
        await message.reply_text("چیزی در حال پخش نیست.")
        return
    await player.stop(message.chat.id)
    await message.reply_text("⏹ پخش متوقف و از کال خارج شدم.")


@Client.on_message(filters.command(["queue", "صف"]))
async def queue_cmd(client: Client, message: Message):
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
