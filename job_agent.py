import os
import requests

token = os.getenv("JOB_TG_TOKEN")
chat_id = os.getenv("JOB_TG_CHAT_ID")

SEARCH_TERMS = [
    "Reinigungskraft",
    "Laborhilfe"
]

url = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "X-API-Key": "jobboerse-jobsuche"
}

messages = []

for keyword in SEARCH_TERMS:

    params = {
        "was": keyword,
        "wo": "Wilhelmshaven",
        "umkreis": 40
    }

    r = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30
    )

    data = r.json()

    jobs = data.get("stellenangebote", [])

    messages.append(f"{keyword}: {len(jobs)} вакансий")

    for job in jobs[:3]:

        title = job.get("titel", "")
        company = job.get("arbeitgeber", "")
        city = job.get("arbeitsort", {}).get("ort", "")

        messages.append(
            f"{title}\n{company}\n{city}"
        )

text = "\n\n".join(messages)

requests.post(
    f"https://api.telegram.org/bot{token}/sendMessage",
    json={
        "chat_id": chat_id,
        "text": text
    },
    timeout=30
)

print("DONE")
