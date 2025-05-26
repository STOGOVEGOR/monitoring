import os
import time
import ssl
import datetime
import threading
import socket, ssl, datetime

import requests
import telebot
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse

load_dotenv()
BOT = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))
CHAT = os.getenv("CHAT_ID")
SITE = os.getenv("WEBSITE_URL")
API = os.getenv("BACKEND_HOST")

# Настраиваем сессию с retry/backoff
session = requests.Session()
session.headers.update({"User-Agent": "WebsiteChecker/1.0"})
retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retry))
session.mount("http://", HTTPAdapter(max_retries=retry))

state = {"site_up": None, "api_up": None}


def send_alert(msg):
    BOT.send_message(CHAT, msg)


def check_url(url, path="", keyword=None):
    start = time.perf_counter()
    try:
        r = session.get(f"{url}{path}", timeout=(3, 5), verify=False)
        ok = (r.status_code == 200) and (keyword in r.text if keyword else True)
        latency = time.perf_counter() - start
        return ok, latency
    except requests.RequestException:
        return False, None


def check_ssl_days(host):
    try:
        ctx = ssl.create_default_context()
        # соединяемся и сразу получаем cert как dict
        with socket.create_connection((host, 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        # cert['notAfter'] выглядит как "Jul 12 23:59:59 2025 GMT"
        exp_str = cert.get('notAfter')
        exp_dt = datetime.datetime.strptime(exp_str, "%b %d %H:%M:%S %Y %Z")
        return (exp_dt - datetime.datetime.utcnow()).days
    except Exception as e:
        print(f"[SSL CHECK ERROR] host={host!r}, exception={e!r}")
        return None


def monitor():
    global state
    # 1) сайт
    up, lat = check_url(SITE)
    if state["site_up"] is None or up != state["site_up"]:
        state["site_up"] = up
        send_alert("✅ WEB is up" if up else "🚨 WEB is down")

    # 2) бэкенд
    up, lat = check_url(API, path="/public/offers")
    if state["api_up"] is None or up != state["api_up"]:
        state["api_up"] = up
        send_alert("✅ API is up" if up else "🚨 API is down")

    # 3) SSL
    # days = check_ssl_days(SITE.replace("https://", ""))
    host = get_host_from_url(SITE)
    days = check_ssl_days(host)
    if days is not None and days < 7:
        send_alert(f"⚠️ SSL expires in {days} days")


def get_host_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname or url  # на всякий случай fallback


# 1) Хэндлер для команды /status
@BOT.message_handler(commands=["status"])
def status_handler(message):
    site = (
        "unknown"
        if state["site_up"] is None
        else "up" if state["site_up"]
        else "down"
    )
    api = (
        "unknown"
        if state["api_up"] is None
        else "up" if state["api_up"]
        else "down"
    )
    days = check_ssl_days(SITE.replace("https://", ""))
    ssl_info = f"{days} days" if days is not None else "N/A"
    text = (
        f"🌐 Site: *{site}*\n"
        f"🔗 API: *{api}*\n"
        f"🔒 SSL: *{ssl_info}*\n"
    )
    BOT.send_message(message.chat.id, text, parse_mode="Markdown")


@BOT.message_handler(commands=["chat_id"])
def echo_chat_id(message):
    BOT.send_message(message.chat.id, f"Your chat_id: {message.chat.id}")


if __name__ == "__main__":
    # 2) Шлём стартовое сообщение
    send_alert("🤖 Monitoring bot started and scheduling checks every 5 minutes.")
    monitor()
    # 3) Запускаем планировщик в фоне
    sched = BackgroundScheduler()
    sched.add_job(monitor, "interval", minutes=5)
    sched.start()

    # 4) Стартуем приём команд
    BOT.infinity_polling()
