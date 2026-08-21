"""Bootstrap: بازیابی متغیرهای محیطی از یک رشته‌ی رمزنگاری‌شده‌ی خودکفا.

این ماژول باید **قبل از هر import دیگری از bot/** اجرا شود، چون config.py
مقادیر env را هنگام import می‌خواند. اگر متغیر RESTORE_BLOB تنظیم شده باشد،
آن را رمزگشایی می‌کند و متغیرهای غایب را در os.environ می‌گذارد.

قالب RESTORE_BLOB (خودکفا، تک‌فیلد):
    <urlsafe_key>.<fernet_token>
که <urlsafe_key> کلید Fernet و <fernet_token> داده‌ی رمزنگاری‌شده است.
پس همین یک رشته برای بازیابی کافی است (کلید هم داخلش است).
"""
import os


def _make_blob(data: dict) -> str:
    """dict را به رشته‌ی خودکفای رمزنگاری‌شده تبدیل می‌کند (کلید+توکن)."""
    import json
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()  # bytes، urlsafe base64
    token = Fernet(key).encrypt(json.dumps(data, ensure_ascii=False).encode())
    return key.decode() + "." + token.decode()


def _read_blob(blob: str) -> dict:
    """رشته‌ی خودکفا را رمزگشایی و به dict برمی‌گرداند."""
    import json
    from cryptography.fernet import Fernet
    key, _, token = blob.strip().partition(".")
    if not key or not token:
        raise ValueError("قالب RESTORE_BLOB نامعتبر است")
    data = Fernet(key.encode()).decrypt(token.encode())
    return json.loads(data.decode())


def apply() -> bool:
    """اگر RESTORE_BLOB تنظیم باشد، متغیرهای غایب را در محیط اعمال می‌کند.

    فقط متغیرهایی را می‌گذارد که از قبل تنظیم نشده‌اند (تا تنظیمات صریح کاربر
    اولویت داشته باشند). خروجی: True اگر بازیابی انجام شد.
    """
    blob = os.environ.get("RESTORE_BLOB", "").strip()
    if not blob:
        return False
    try:
        data = _read_blob(blob)
    except Exception as e:  # noqa: BLE001
        print(f"[bootstrap] RESTORE_BLOB رمزگشایی نشد: {e}")
        return False
    applied = 0
    for k, v in data.items():
        if k == "RESTORE_BLOB":
            continue
        if not os.environ.get(k):  # فقط متغیرهای غایب
            os.environ[k] = str(v)
            applied += 1
    print(f"[bootstrap] {applied} متغیر از RESTORE_BLOB بازیابی شد.")
    return True
