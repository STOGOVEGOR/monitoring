import datetime
import os
import ssl
import time

import requests
import telebot
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
    except requests.RequestException as e:
        return False, None


def check_ssl_days(host):
    try:
        cert = ssl.get_server_certificate((host, 443))
        info = ssl._ssl._test_decode_cert(cert)
        exp = datetime.datetime.strptime(info['notAfter'], "%b %d %H:%M:%S %Y %Z")
        return (exp - datetime.datetime.utcnow()).days
    except Exception:
        return None


def monitor():
    global state
    # 1) сайт
    up, lat = check_url(SITE)
    if state["site_up"] is None or up != state["site_up"]:
        state["site_up"] = up
        send_alert("✅ WEB is up" if up else "🚨 WEB is down")
    if not up:
        print(f"WEB down, latency was {lat}")

    # 2) бэкенд
    up, lat = check_url(API, path="/public/offers")
    if up != state["api_up"]:
        state["api_up"] = up
        send_alert("✅ API is up" if up else "🚨 API is down")

    # 3) SSL
    days = check_ssl_days(SITE.replace("https://", ""))
    if days is not None and days < 7:
        send_alert(f"⚠️ SSL expires in {days} days")


if __name__ == "__main__":
    sched = BlockingScheduler()
    sched.add_job(monitor, 'interval', minutes=5)
    sched.start()
