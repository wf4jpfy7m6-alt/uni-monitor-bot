#!/usr/bin/env python3

import os
import requests
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("JOB_TG_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("JOB_TG_CHAT_ID", "")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    response = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text
        },
        timeout=15
    )

    print("Status:", response.status_code)
    print("Response:", response.text)

def run():
    print("JOB AGENT TEST")
    send_telegram(
        f"Тест Railway {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

if __name__ == "__main__":
    run()
