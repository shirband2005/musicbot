"""بازیابی متغیرهای env از فایل بکاپ رمزنگاری‌شده (env.bak).

استفاده روی سرور جدید:
    BACKUP_KEY=<همان رمز> python restore_env.py env.bak

خروجی: یک فایل .env با مقادیر بازیابی‌شده که می‌توانی در Railway/سرور جدید paste کنی.
"""
import base64
import hashlib
import json
import os
import sys


def main():
    if len(sys.argv) < 2:
        print("usage: BACKUP_KEY=<key> python restore_env.py env.bak")
        sys.exit(1)
    path = sys.argv[1]
    key = os.environ.get("BACKUP_KEY", "").strip()
    if not key:
        print("خطا: متغیر BACKUP_KEY تنظیم نشده (همان رمزی که موقع بکاپ استفاده شد).")
        sys.exit(1)
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("خطا: کتابخانه cryptography نصب نیست. اجرا کن: pip install cryptography")
        sys.exit(1)

    digest = hashlib.sha256(key.encode()).digest()
    f = Fernet(base64.urlsafe_b64encode(digest))
    with open(path, "rb") as fh:
        blob = fh.read()
    try:
        data = json.loads(f.decrypt(blob).decode())
    except Exception as e:  # noqa: BLE001
        print(f"خطا در رمزگشایی (رمز اشتباه؟): {e}")
        sys.exit(1)

    out = ".env"
    with open(out, "w", encoding="utf-8") as fh:
        for k, v in data.items():
            fh.write(f"{k}={v}\n")
    print(f"✅ {len(data)} متغیر در {out} بازیابی شد.")
    print("این‌ها را در تنظیمات env سرور/Railway جدید وارد کن.")


if __name__ == "__main__":
    main()
