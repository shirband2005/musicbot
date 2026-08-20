"""ابزار ساخت STRING_SESSION برای یوزربات کمکی.

این اسکریپت را **روی دستگاه خودت** اجرا کن (نه روی سرور).
با اکانت دومی که می‌خواهی وارد ویس‌چت شود لاگین کن.
خروجی یک رشته‌ی طولانی است که باید در متغیر محیطی STRING_SESSION قرار بگیرد.

نحوه اجرا:
    pip install pyrofork tgcrypto
    python generate_session.py
"""
from pyrogram import Client

print("=" * 55)
print(" ساخت STRING_SESSION برای یوزربات کمکی")
print("=" * 55)

api_id = int(input("API_ID را وارد کن: ").strip())
api_hash = input("API_HASH را وارد کن: ").strip()

with Client("gen", api_id=api_id, api_hash=api_hash, in_memory=True) as app:
    session = app.export_session_string()
    print("\n✅ رشته نشست تو (این را در STRING_SESSION قرار بده):\n")
    print(session)
    print("\n⚠️ این رشته مثل رمز عبور است؛ آن را با کسی به اشتراک نگذار.")
