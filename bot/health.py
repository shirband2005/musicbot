"""سرور سلامت (health-check) سبک برای Railway/مانیتورینگ.

یک سرور HTTP کوچک روی PORT (پیش‌فرض 8080) که به /health و / پاسخ می‌دهد.
اگر ربات زنده باشد 200 و در غیر این صورت 503 برمی‌گرداند. این‌طور Railway
می‌فهمد ربات سالم است و در کرش‌لوپ گیر نمی‌کند بدون اطلاع.
"""
import json
import logging
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

LOGGER = logging.getLogger("musicbot.health")

# وضعیت مشترک که main هنگام آماده‌شدن ست می‌کند
_state = {"ready": False, "started_at": time.time(), "bot": ""}


def mark_ready(bot_username: str = "") -> None:
    _state["ready"] = True
    _state["bot"] = bot_username


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        ok = _state["ready"]
        body = json.dumps({
            "status": "ok" if ok else "starting",
            "bot": _state["bot"],
            "uptime_s": int(time.time() - _state["started_at"]),
        }).encode()
        self.send_response(200 if ok else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # ساکت — لاگ HTTP اضافی نده
        pass


def start_health_server(port: int) -> None:
    """سرور سلامت را در یک ترد جدا (daemon) اجرا می‌کند."""
    def _run():
        try:
            srv = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
            LOGGER.info("health server on :%s", port)
            srv.serve_forever()
        except Exception as e:  # noqa: BLE001
            LOGGER.warning("health server failed: %s", e)

    Thread(target=_run, daemon=True).start()
