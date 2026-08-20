# ---- ربات موزیک‌پلیر فارسی + سرویس PO Token (bgutil) ----
FROM python:3.11-slim

# نسخه‌ی سرویس PO Token
ARG BGUTIL_VERSION=1.3.1
# نسخه Node (۲۲ برای حل چالش nsig یوتیوب — نسخه ۲۰ گاهی «page needs to be reloaded» می‌داد)
ARG NODE_MAJOR=22

# ابزارهای لازم: ffmpeg (پردازش رسانه) + git/curl (کلون) + Node.js
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg git curl ca-certificates gnupg && \
    # نصب Node.js (برای سرویس bgutil و حل چالش JS یوتیوب)
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- ساخت سرویس PO Token (bgutil) ---
# سرور Node که هر بار توکن BotGuard تازه تولید می‌کند (پورت 4416).
RUN git clone --depth 1 --branch ${BGUTIL_VERSION} \
        https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /app/bgutil && \
    cd /app/bgutil/server && \
    npm ci && \
    npx tsc && \
    npm cache clean --force

# --- نصب وابستگی‌های پایتون (شامل پلاگین bgutil برای yt-dlp) ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# اجرای هم‌زمان سرویس توکن + ربات
RUN chmod +x /app/start.sh
CMD ["/app/start.sh"]
