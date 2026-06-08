#!/usr/bin/env python3

import os
import requests
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("JOB_TG_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("JOB_TG_CHAT_ID", "")

def send_telegram(text):
if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
print("Telegram variables missing")
return

```
try:
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text
        },
        timeout=30
    )
except Exception as e:
    print("Telegram error:", e)
```

def run():

```
print("=" * 50)
print("ARBEITSAGENTUR API TEST")
print(datetime.now())
print("=" * 50)

send_telegram("🔎 Тест API Arbeitsagentur")

url = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

params = {
    "was": "Reinigungskraft",
    "wo": "Wilhelmshaven",
    "umkreis": 40,
    "page": 1
}

try:
    r = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30
    )

    print("STATUS:", r.status_code)

    print("\nHEADERS:")
    print(r.headers)

    print("\nBODY:")
    print(r.text[:5000])

except Exception as e:
    print("ERROR:", e)
```

if **name** == "**main**":
run()
