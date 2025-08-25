import datetime
import os
import socket
import ssl
import time
from urllib.parse import urlparse

import urllib3
import requests
import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()
BOT = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))
CHAT = os.getenv("CHAT_ID")
ADMIN = os.getenv("ADMIN_CHAT_ID")
SITE = os.getenv("WEBSITE_URL")
API = os.getenv("BACKEND_HOST")

# — Session with retry/backoff
session = requests.Session()
session.headers.update({"User-Agent": "WebsiteChecker/1.0"})
retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retry))
session.mount("http://", HTTPAdapter(max_retries=retry))

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# — Define targets once; add as many as you need
#   key: unique id for state tracking and messages
TARGETS = [
    # WEB targets
    {"key": "web_main", "name": "WEB main", "url": SITE, "path": "", "keyword": None, "verify": False},
    {"key": "web_larazon", "name": "WEB Larazon proxy", "url": "https://mioferton.larazon.es", "path": "", "keyword": None, "verify": False},

    # API targets
    {"key": "api_offers", "name": "API offers", "url": API, "path": "/public/offers", "keyword": None, "verify": False},
    # {"key": "api_health", "name": "API health", "url": API, "path": "/healthz", "keyword": "healthy", "verify": True},
]

# — Per-target state: {key: True|False|None}
STATE = {t["key"]: None for t in TARGETS}

SSL_THRESHOLD_DAYS = 7  # alert if below
# Optional: per-host override -> {"mioferton.com": 14}
SSL_PER_HOST_THRESHOLD = {}


def send_alert(msg: str):
    # keep it dead simple: send to both chats
    BOT.send_message(CHAT, msg)
    BOT.send_message(ADMIN, msg)


def check_url(url: str, path: str = "", keyword: str | None = None, verify: bool = False):
    """HTTP GET and simple content check; returns (ok, latency, status_code)."""
    start = time.perf_counter()
    try:
        r = session.get(f"{url}{path}", timeout=(3, 5), verify=verify)
        latency = time.perf_counter() - start
        ok_status = (200 <= r.status_code < 300)  # accept any 2xx
        ok_body = (keyword in r.text) if keyword else True
        return (ok_status and ok_body), latency, r.status_code
    except requests.RequestException:
        return False, None, None


def get_host_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname or url


def check_ssl_days(host: str) -> int | None:
    """Return days left until certificate expiration, or None on failure."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        exp_str = cert.get("notAfter")  # e.g. "Jul 12 23:59:59 2025 GMT"
        exp_dt = datetime.datetime.strptime(exp_str, "%b %d %H:%M:%S %Y %Z")
        return (exp_dt - datetime.datetime.utcnow()).days
    except Exception as e:
        print(f"[SSL CHECK ERROR] host={host!r}, exception={e!r}")
        return None


def monitor():
    """Run all checks once; alert on state changes and soon-expiring SSL."""
    global STATE

    # 1) HTTP checks (each target individually)
    for t in TARGETS:
        ok, lat, code = check_url(t["url"], t["path"], t["keyword"], t.get("verify", False))
        key = t["key"]
        prev = STATE.get(key)
        if ok != prev:
            STATE[key] = ok
            name = t["name"]
            # Small, human-readable message mentioning exactly what failed/recovered
            if ok:
                send_alert(f"✅ {name} is UP ({code}, {lat:.3f}s)")
            else:
                code_str = code if code is not None else "no response"
                lat_str = f"{lat:.3f}s" if lat is not None else "N/A"
                send_alert(f"🚨 {name} is DOWN ({code_str}, {lat_str})")

    # 2) SSL checks (per unique host among WEB/API base URLs)
    unique_hosts = {get_host_from_url(t["url"]) for t in TARGETS}
    for host in sorted(unique_hosts):
        days = check_ssl_days(host)
        if days is None:
            continue
        threshold = SSL_PER_HOST_THRESHOLD.get(host, SSL_THRESHOLD_DAYS)
        if days < threshold:
            send_alert(f"⚠️ SSL for *{host}* expires in {days} day(s)")

# — Telegram commands


@BOT.message_handler(commands=["status"])
def status_handler(message):
    # Build per-target status table
    lines = []
    for t in TARGETS:
        key = t["key"]
        st = STATE.get(key)
        status = "unknown" if st is None else ("up" if st else "down")
        lines.append(f"• {t['name']}: *{status}*")

    # SSL overview (show nearest expiry per host)
    unique_hosts = {get_host_from_url(t["url"]) for t in TARGETS}
    ssl_lines = []
    for host in sorted(unique_hosts):
        days = check_ssl_days(host)
        ssl_lines.append(f"• {host}: *{days} days*" if days is not None else f"• {host}: *N/A*")

    text = "🌐 Services:\n" + "\n".join(lines) + "\n\n🔒 SSL:\n" + "\n".join(ssl_lines)
    BOT.send_message(message.chat.id, text, parse_mode="Markdown")


@BOT.message_handler(commands=["chat_id"])
def echo_chat_id(message):
    BOT.send_message(message.chat.id, f"Your chat_id: {message.chat.id}")


if __name__ == "__main__":
    # Optional one-shot run on start:
    # monitor()
    sched = BackgroundScheduler()
    sched.add_job(monitor, "interval", minutes=5)
    sched.start()
    BOT.infinity_polling()
