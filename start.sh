#!/usr/bin/env bash
# اجرای هم‌زمان سرویس PO Token (bgutil) و سپس ربات.
set -e

# --- تنظیم مصرف حافظه (کاهش رم روی سقف ۱ گیگ ریلوی) ---
# glibc malloc: حافظه‌ی آزادشده را زودتر به سیستم‌عامل برگردان (به‌جای نگه‌داشتن).
export MALLOC_TRIM_THRESHOLD_=100000
export MALLOC_ARENA_MAX=2
export PYTHONMALLOC=malloc

echo "[start] راه‌اندازی سرویس PO Token روی پورت 4416..."
# سرویس bgutil را در پس‌زمینه اجرا کن — با محدودیت حافظه‌ی Node (کاهش مصرف رم).
node --max-old-space-size=64 /app/bgutil/server/build/main.js --port 4416 &
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
