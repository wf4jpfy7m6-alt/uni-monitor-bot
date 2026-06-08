import os
import requests

token = os.getenv("JOB_TG_TOKEN")
chat_id = os.getenv("JOB_TG_CHAT_ID")

url = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "X-API-Key": "jobboerse-jobsuche"
}

params = {
    "was": "Reinigungskraft",
    "wo": "Wilhelmshaven",
    "umkreis": 40
}

r = requests.get(url, headers=headers, params=params)

data = r.json()

jobs = data.get("stellenangebote", [])

if jobs:
    job = jobs[0]

    title = job.get("titel", "")
    company = job.get("arbeitgeber", "")
    city = job.get("arbeitsort", {}).get("ort", "")

    text = f"ТЕСТ ВАКАНСИИ\n\n{title}\n{company}\n{city}"

else:
    text = "Вакансии не найдены"

requests.post(
    f"https://api.telegram.org/bot{token}/sendMessage",
    json={
        "chat_id": chat_id,
        "text": text
    }
)

print("Jobs:", len(jobs))
