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

r = requests.get(
    url,
    headers=headers,
    params=params,
    timeout=30
)

data = r.json()

jobs = data.get("stellenangebote", [])

if jobs:

    job = jobs[0]

    title = job.get("titel", "")
    company = job.get("arbeitgeber", "")
    city = job.get("arbeitsort", {}).get("ort", "")
    date = job.get("aktuelleVeroeffentlichungsdatum", "")

    link = (
        job.get("externeUrl")
        or f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{job.get('refnr')}"
    )

    text = (
        f"🔔 Новая вакансия\n\n"
        f"📌 {title}\n"
        f"🏢 {company}\n"
        f"📍 {city}\n"
        f"📅 {date}\n\n"
        f"🔗 {link}"
    )

else:

    text = "Вакансии не найдены"

requests.post(
    f"https://api.telegram.org/bot{token}/sendMessage",
    json={
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": False
    },
    timeout=30
)

print("DONE")
