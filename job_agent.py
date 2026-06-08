import os
import requests

token = os.getenv("JOB_TG_TOKEN")
chat_id = os.getenv("JOB_TG_CHAT_ID")

r = requests.post(
    f"https://api.telegram.org/bot{token}/sendMessage",
    json={
        "chat_id": chat_id,
        "text": "Railway test"
    }
)

print(r.status_code)
print(r.text)
