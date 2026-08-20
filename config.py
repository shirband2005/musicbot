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
OWNER_ID = _int("OWNER_ID")

# --- مسیر دیتابیس ---
# روی ریلوی یک Volume به /data وصل می‌شود تا فایل دیتابیس پایدار بماند.
DB_PATH = os.environ.get("DB_PATH", "/data/musicbot.db").strip() or "/data/musicbot.db"

# --- کوکی یوتیوب (اختیاری) ---
# در صورت خطای «Sign in to confirm you're not a bot» می‌توان محتوای cookies.txt را داد.
COOKIES_FILE = os.environ.get("COOKIES_FILE", "cookies.txt").strip()

# --- حداکثر طول مجاز محتوا (ثانیه) — جلوگیری از پخش استریم‌های خیلی طولانی ---
DURATION_LIMIT = _int("DURATION_LIMIT", 3 * 60 * 60)  # پیش‌فرض ۳ ساعت
