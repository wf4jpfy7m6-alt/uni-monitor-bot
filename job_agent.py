```python
#!/usr/bin/env python3

import os
import requests
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("JOB_TG_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("JOB_TG_CHAT_ID", "")

def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Ошибка: JOB_TG_TOKEN или JOB_TG_CHAT_ID не заданы")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        r = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
            },
            timeout=15,
        )

        print("Telegram status:", r.status_code)
        print("Telegram response:", r.text)

    except Exception as e:
        print("Telegram error:", e)

def run():
    print("=" * 50)
    print("JOB AGENT TEST")
    print(datetime.now())
    print("=" * 50)

    send_telegram(
        f"✅ Тестовое сообщение\n\n"
        f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

if __name__ == "__main__":
    run()
```
