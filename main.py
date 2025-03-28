import os
import time
# import pytz
# import sqlite3
import telebot
import requests
import socket

# from datetime import date, timedelta, datetime, time, timezone
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
WEBSITE_URL = os.getenv("WEBSITE_URL")
BACKEND_HOST = os.getenv("BACKEND_HOST")
# BACKEND_PORT = int(os.getenv("BACKEND_PORT", 8081))  # значение по умолчанию

bot = telebot.TeleBot(TELEGRAM_TOKEN)
# con = sqlite3.connect('/home/MonteBus/bus_bot.db', check_same_thread=False)
# cur = con.cursor()
# cur.execute("""
#         CREATE TABLE USERS (
#             id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
#             user_id INTEGER,
#             user_name TEXT,
#             lang TEXT,
#             counter INTEGER
#         );
#     """)


# Функция проверки вебсайта
def check_website(url):
    try:
        # Добавляем User-Agent для избегания блокировок
        headers = {"User-Agent": "WebsiteChecker/1.0"}
        response = requests.get(url, headers=headers, timeout=5, verify=False)
        return response.status_code == 200
    except requests.exceptions.SSLError as e:
        print(f"SSL error: {e}")
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error: {e}")
    except requests.exceptions.Timeout as e:
        print(f"Timeout error: {e}")
    except requests.exceptions.RequestException as e:
        print(f"General error: {e}")
    return False


# Функция проверки порта
def check_backend(url):
    try:
        response = requests.get(f"{url}/swagger", timeout=5)
        if response.status_code == 200:
            return True
        else:
            print(f"Backend returned status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Backend check failed: {e}")
        return False


# Уведомление в Telegram
def send_telegram_message(message):
    bot.send_message(chat_id=CHAT_ID, text=message)


# Основной процесс
def monitor():
    if not check_website(WEBSITE_URL):
        send_telegram_message("🚨 HSC web down.")
    if not check_backend(BACKEND_HOST):
        send_telegram_message("🚨 HSC back down.")


# Запуск мониторинга каждые 5 минут
if __name__ == "__main__":
    while True:
        monitor()
        time.sleep(300)  # 300 секунд = 5 минут
