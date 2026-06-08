import os
import requests

TOKEN = os.getenv("JOB_TG_TOKEN")
CHAT_ID = os.getenv("JOB_TG_CHAT_ID")

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

r = requests.post(
    url,
    json={
        "chat_id": CHAT_ID,
        "text": "Railway job bot works"
    }
)

print(r.status_code)
print(r.text)
