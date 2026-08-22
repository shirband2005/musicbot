"""پیکربندی ربات — همه مقادیر از متغیرهای محیطی (Environment Variables) خوانده می‌شوند."""
import os


def _int(name: str, default: int = 0) -> int:
    val = os.environ.get(name, "").strip()
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# --- اعتبارنامه‌های تلگرام ---
API_ID = _int("API_ID")
API_HASH = os.environ.get("API_HASH", "").strip()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# رشته‌ی نشست یوزربات کمکی (اکانتی که وارد ویس‌چت می‌شود و پخش می‌کند)
STRING_SESSION = os.environ.get("STRING_SESSION", "").strip()

# --- مالک و مدیریت ---
# آیدی عددی مالک؛ حتماً در env تنظیم شود (بدون پیش‌فرض تا ریپو عمومی امن بماند).
OWNER_ID = _int("OWNER_ID")

# --- کانال‌ها (اختیاری) ---
# کانال لاگ: رویدادهای مهم ربات (روشن/خاموش، گروه جدید، خطا).
LOG_CHANNEL = _int("LOG_CHANNEL")
# کانال آرشیو آهنگ: هر آهنگ دانلودشده اینجا ذخیره می‌شود تا دفعه بعد بدون
# دانلود از یوتیوب، مستقیم از تلگرام بازیابی شود. (بهتر است خصوصی باشد.)
ARCHIVE_CHANNEL = _int("ARCHIVE_CHANNEL")
# کانال پرداخت‌ها: رسید هر سفارش با دکمه‌های تأیید/لغو اینجا می‌آید و مالک
# همان‌جا تصمیم می‌گیرد. (باید خصوصی باشد و ربات در آن ادمین باشد.)
PAYMENT_CHANNEL = _int("PAYMENT_CHANNEL")

# --- مسیر دیتابیس ---
# روی ریلوی یک Volume به /data وصل می‌شود تا فایل دیتابیس پایدار بماند.
DB_PATH = os.environ.get("DB_PATH", "/data/musicbot.db").strip() or "/data/musicbot.db"

# --- کوکی یوتیوب (اختیاری) ---
# دو راه: (۱) COOKIES_B64 = محتوای cookies.txt به‌صورت base64 (امن برای env)
#         (۲) فایل cookies.txt در کنار کد.
# مقدار COOKIES_B64 هنگام اجرا به فایل COOKIES_FILE نوشته می‌شود.
COOKIES_FILE = os.environ.get("COOKIES_FILE", "/data/cookies.txt").strip() or "/data/cookies.txt"
COOKIES_B64 = os.environ.get("COOKIES_B64", "").strip()


def materialize_cookies() -> bool:
    """اگر COOKIES_B64 تنظیم شده باشد، آن را رمزگشایی و در COOKIES_FILE می‌نویسد.

    خروجی: True اگر فایل کوکی معتبری در دسترس باشد.
    """
    import base64

    if COOKIES_B64:
        try:
            data = base64.b64decode(COOKIES_B64)
            d = os.path.dirname(COOKIES_FILE)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(COOKIES_FILE, "wb") as f:
                f.write(data)
        except Exception:
            return os.path.isfile(COOKIES_FILE)
    return os.path.isfile(COOKIES_FILE)

# --- حداکثر طول مجاز محتوا (ثانیه) — جلوگیری از پخش استریم‌های خیلی طولانی ---
DURATION_LIMIT = _int("DURATION_LIMIT", 3 * 60 * 60)  # پیش‌فرض ۳ ساعت
