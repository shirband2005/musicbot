#!/usr/bin/env bash
# اجرای هم‌زمان سرویس PO Token (bgutil) و سپس ربات.
set -e

echo "[start] راه‌اندازی سرویس PO Token روی پورت 4416..."
# سرویس bgutil را در پس‌زمینه اجرا کن
node /app/bgutil/server/build/main.js --port 4416 &
BGUTIL_PID=$!

# صبر کوتاه تا سرویس بالا بیاید
sleep 4

# اگر سرویس زنده نماند، فقط هشدار بده (ربات باید بدون آن هم اجرا شود)
if ! kill -0 "$BGUTIL_PID" 2>/dev/null; then
    echo "[start] ⚠️ سرویس PO Token بالا نیامد — ربات بدون آن ادامه می‌دهد."
else
    echo "[start] ✅ سرویس PO Token فعال شد (pid=$BGUTIL_PID)."
fi

echo "[start] راه‌اندازی ربات..."
exec python -m main
