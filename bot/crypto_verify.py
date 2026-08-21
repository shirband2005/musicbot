"""تأیید خودکار پرداخت USDT-TRC20 (TRON) با TronGrid API.

کاربر مبلغ USDT را به آدرس ما می‌فرستد و TxID را می‌فرستد؛ این ماژول سرور-به-سرور
بررسی می‌کند: تراکنش موفق، مقصد آدرس ما، توکن USDT، مبلغ کافی، و تأییدشده.
منبع API تأییدشده (تست زنده): api.trongrid.io — بدون کلید کار می‌کند، ولی کلید
رایگان (هدر TRON-PRO-API-KEY) برای پایداری روی سرور توصیه می‌شود.
"""
import logging
import os
from decimal import Decimal

import aiohttp

LOGGER = logging.getLogger("musicbot.crypto")

USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
TRONGRID = os.environ.get("TRONGRID_URL", "https://api.trongrid.io").rstrip("/")
MIN_CONFIRMATIONS = int(os.environ.get("TRON_MIN_CONF", "19"))
# tolerance مبلغ: کاربر ممکن است چند سنت کمتر بفرستد (کارمزد/گِرد کردن)
AMOUNT_TOLERANCE = Decimal(os.environ.get("USDT_TOLERANCE", "0.5"))


def _headers() -> dict:
    key = os.environ.get("TRONGRID_API_KEY", "").strip()
    return {"TRON-PRO-API-KEY": key} if key else {}


async def verify_usdt(txid: str, wallet: str, min_usdt: Decimal) -> tuple[bool, str]:
    """آیا `wallet` حداقل `min_usdt` تتر در تراکنش `txid` دریافت کرده (موفق و تأییدشده)؟

    برمی‌گرداند (ok, reason). ok=True یعنی پرداخت معتبر است.
    """
    txid = (txid or "").strip().lower().replace("0x", "")
    if len(txid) < 60:
        return False, "شناسه تراکنش (TxID) نامعتبر است."
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=_headers()) as s:
            # الف) موفقیت روی زنجیره + بلاک
            async with s.post(f"{TRONGRID}/wallet/gettransactioninfobyid",
                              json={"value": txid}) as r:
                info = await r.json()
            if not info or "blockNumber" not in info:
                return False, "تراکنش پیدا نشد یا هنوز در بلاک ثبت نشده."
            if info.get("receipt", {}).get("result") != "SUCCESS":
                return False, "تراکنش ناموفق/برگشت‌خورده است."
            # ب) تعداد تأییدها = سر زنجیره - بلاک تراکنش
            async with s.post(f"{TRONGRID}/wallet/getnowblock") as r:
                head = (await r.json())["block_header"]["raw_data"]["number"]
            confs = head - info["blockNumber"]
            if confs < MIN_CONFIRMATIONS:
                return False, f"هنوز کافی تأیید نشده ({confs}/{MIN_CONFIRMATIONS}). کمی صبر کن."
            # ج) انتقال واقعی USDT به آدرس ما در این تراکنش
            async with s.get(f"{TRONGRID}/v1/accounts/{wallet}/transactions/trc20",
                             params={"only_to": "true", "contract_address": USDT_CONTRACT,
                                     "limit": "50"}) as r:
                rows = (await r.json()).get("data", [])
            m = next((t for t in rows if t.get("transaction_id") == txid), None)
            if not m:
                return False, "انتقال USDT به آدرس ما در این تراکنش نیست."
            if m.get("to") != wallet or m.get("token_info", {}).get("address") != USDT_CONTRACT:
                return False, "گیرنده یا توکن اشتباه است."
            decimals = int(m["token_info"].get("decimals", 6))
            amount = Decimal(m["value"]) / (Decimal(10) ** decimals)
            if amount + AMOUNT_TOLERANCE < min_usdt:
                return False, f"مبلغ کم است: {amount} USDT (نیاز: {min_usdt})."
            return True, f"✅ {amount} USDT دریافت شد."
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("verify_usdt: %s", e)
        return False, "خطا در بررسی تراکنش. بعداً دوباره تلاش کن یا با پشتیبانی تماس بگیر."


def toman_to_usdt(toman: int, rate_toman_per_usdt: int) -> Decimal:
    """مبلغ تومان را به USDT تبدیل می‌کند طبق نرخ تنظیم‌شده."""
    if rate_toman_per_usdt <= 0:
        return Decimal("0")
    return (Decimal(toman) / Decimal(rate_toman_per_usdt)).quantize(Decimal("0.01"))
