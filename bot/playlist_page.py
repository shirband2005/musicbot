"""صفحه‌ی لیست پخش — پرش و حذف، با صفحه‌بندی هوشمند.

طرح تأییدشده:
  · روی شماره‌ی هر آهنگ بزنی، همان پخش می‌شود؛ ردیف دوم برای حذف
  · تعداد دکمه = تعداد آهنگ همان صفحه (اگر ۳ آهنگ است، ۳ دکمه نه ۵)
  · حداکثر ۵ آهنگ در هر صفحه؛ بیشتر شد → صفحه‌ی بعد
  · اگر فقط یک صفحه باشد، ردیف ناوبری کلاً نمایش داده نمی‌شود
  · callback شناسه‌ی یکتای آهنگ را حمل می‌کند نه شماره‌ی ردیف

الگوی callback:
    q|page|<n>          رفتن به صفحه
    q|jump|<uid>        پخش فوری آن آهنگ
    q|del|<uid>         حذف از صف
    q|back              بازگشت به پنل پخش
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from pyrogram.types import InlineKeyboardMarkup

from bot import ui
from bot.queue import Track

PER_PAGE = 5


def page_count(total: int) -> int:
    """تعداد صفحه‌ها (حداقل ۱، حتی برای صف خالی)."""
    if total <= 0:
        return 1
    return (total + PER_PAGE - 1) // PER_PAGE


def clamp_page(page: int, total: int) -> int:
    """شماره‌ی صفحه را در بازه‌ی معتبر نگه می‌دارد.

    لازم است چون بعد از حذف آخرین آهنگِ یک صفحه، آن صفحه دیگر وجود ندارد و
    کاربر باید خودکار به صفحه‌ی قبل برگردد.
    """
    last = page_count(total)
    return max(1, min(page, last))


def slice_page(items: List[Track], page: int) -> Tuple[List[Track], int]:
    """آهنگ‌های یک صفحه + شماره‌ی شروع (۱-پایه) را برمی‌گرداند."""
    page = clamp_page(page, len(items))
    start = (page - 1) * PER_PAGE
    return items[start:start + PER_PAGE], start + 1


def content(current: Optional[Track], items: List[Track], page: int = 1):
    """متن صفحه‌ی لیست پخش. برمی‌گرداند (text, entities)."""
    t = ui.Text().title(ui.EMO_LIST, ui.BASE_ARROW, "لیست پخش")

    if current is not None:
        t.emoji(ui.EMO_HEADPHONE, ui.BASE_HEADPHONE)
        t.add(" در حال پخش : ").bold(ui.trunc(current.title, 34)).add("\n\n")

    if not items:
        t.add("صف بعدی خالی است.\n")
        t.italic("یک آهنگ دیگر بفرست تا به صف اضافه شود.")
        return t.text, t.entities

    rows, start = slice_page(items, page)
    for i, tr in enumerate(rows):
        num = start + i
        t.emoji(ui.alt_arrow(i))
        t.add(f" {ui.fa(num)}. {ui.trunc(tr.title, 30)}")
        if tr.duration_text:
            t.add(f"  ·  {ui.fa(tr.duration_text)}")
        t.add("\n")
        if tr.requester:
            t.add(f"      {tr.requester}\n")

    total_pages = page_count(len(items))
    if total_pages > 1:
        t.add("\n")
        t.italic(f"صفحه {ui.fa(clamp_page(page, len(items)))} از {ui.fa(total_pages)}"
                 f"  ·  {ui.fa(len(items))} آهنگ در صف")
    else:
        t.add("\n")
        t.italic("برای پخش هر آهنگ روی شماره‌اش بزن.")
    return t.text, t.entities


def keyboard(items: List[Track], page: int = 1) -> InlineKeyboardMarkup:
    """کیبورد صفحه‌ی لیست پخش."""
    if not items:
        return ui.kb([[ui.btn("بازگشت به پنل", "q|back", ui.PLAIN, ui.EMO_BACK)]])

    page = clamp_page(page, len(items))
    rows_items, start = slice_page(items, page)

    # ردیف پرش: تعداد دکمه = تعداد آهنگ همین صفحه
    jump = [ui.btn(ui.fa(start + i), f"q|jump|{tr.uid}")
            for i, tr in enumerate(rows_items)]
    # ردیف حذف: هم‌تراز با ردیف پرش
    dele = [ui.btn(f"حذف {ui.fa(start + i)}", f"q|del|{tr.uid}", ui.RED)
            for i, tr in enumerate(rows_items)]

    rows = [jump, dele]

    total_pages = page_count(len(items))
    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(ui.btn("صفحه قبل", f"q|page|{page - 1}", ui.PLAIN, ui.EMO_BACK))
        nav.append(ui.btn(f"{ui.fa(page)}/{ui.fa(total_pages)}", "q|noop"))
        if page < total_pages:
            nav.append(ui.btn("صفحه بعد", f"q|page|{page + 1}"))
        rows.append(nav)

    rows.append([ui.btn("بازگشت به پنل", "q|back", ui.PLAIN, ui.EMO_BACK)])
    return ui.kb(rows)
