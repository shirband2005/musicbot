"""تنظیمات مشترک تست‌ها.

`bot/__init__.py` اگر متغیرهای محیطی تلگرام نباشند `sys.exit(1)` می‌زند — پس
باید **پیش از import هر ماژول ربات** مقدار بگیرند. conftest زودتر از فایل‌های
تست بارگذاری می‌شود، بنابراین اینجا جای درست این کار است (قبلاً در ابتدای
test_core.py بود و هر فایل تست جدید باید تکرارش می‌کرد).
"""
import os

os.environ.setdefault("API_ID", "1")
os.environ.setdefault("API_HASH", "x")
os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("STRING_SESSION", "x")
os.environ.setdefault("OWNER_ID", "8406519786")
