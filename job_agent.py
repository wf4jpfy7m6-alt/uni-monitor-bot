import os
import json
import requests
from pathlib import Path
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("JOB_TG_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("JOB_TG_CHAT_ID", "")

DATA_FILE = Path("sent_jobs.json")

SEARCH_TERMS = [
"Reinigungskraft",
"Gebäudereiniger",
"Mitarbeiter Reinigung",
"Laborhilfe",
"Laborhelfer",
"Laborassistent",
"Sterilisationsassistent",
"ZSVA",
"Reinraum",
"Reinraumreinigung",
"Pharmareinigung",
"Produktionshelfer",
"Produktionsmitarbeiter",
"Lagerhelfer",
"Lagermitarbeiter",
"Kommissionierer",
"Versandmitarbeiter",
"Logistikmitarbeiter",
"Logistikhelfer",
"Quereinsteiger"
]

API_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"

HEADERS = {
"User-Agent": "Mozilla/5.0",
"Accept": "application/json",
"X-API-Key": "jobboerse-jobsuche"
}

def send_telegram(text):
if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
print("Telegram variables missing")
return

```
try:
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": False
        },
        timeout=30
    )

    print("Telegram:", response.status_code)

except Exception as e:
    print("Telegram error:", str(e))
```

def load_sent_jobs():
if not DATA_FILE.exists():
return set()

```
try:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))
except Exception:
    return set()
```

def save_sent_jobs(job_ids):
with open(DATA_FILE, "w", encoding="utf-8") as f:
json.dump(list(job_ids), f)

def search_jobs(keyword):
params = {
"was": keyword,
"wo": "Wilhelmshaven",
"umkreis": 40
}

```
try:
    response = requests.get(
        API_URL,
        headers=HEADERS,
        params=params,
        timeout=30
    )

    if response.status_code != 200:
        print(keyword, response.status_code)
        return []

    data = response.json()

    return data.get("stellenangebote", [])

except Exception as e:
    print("Search error:", keyword, str(e))
    return []
```

def format_job(job, keyword):
title = job.get("titel", "Без названия")
company = job.get("arbeitgeber", "Не указан")

```
location = (
    job.get("arbeitsort", {})
    .get("ort", "Не указан")
)

date = job.get(
    "aktuelleVeroeffentlichungsdatum",
    "-"
)

url = job.get("externeUrl", "")

text = (
    f"🔔 Новая вакансия\n\n"
    f"📌 {title}\n"
    f"🏢 {company}\n"
    f"📍 {location}\n"
    f"📅 {date}\n"
    f"🔎 {keyword}"
)

if url:
    text += f"\n\n🔗 {url}"

return text
```

def run():
print("=" * 50)
print("JOB AGENT START")
print(datetime.now())
print("=" * 50)

```
sent_jobs = load_sent_jobs()

total_found = 0
new_found = 0

for keyword in SEARCH_TERMS:

    jobs = search_jobs(keyword)

    total_found += len(jobs)

    print(
        f"{keyword}: {len(jobs)} jobs"
    )

    for job in jobs:

        job_id = job.get("refnr")

        if not job_id:
            continue

        if job_id in sent_jobs:
            continue

        send_telegram(
            format_job(job, keyword)
        )

        sent_jobs.add(job_id)

        new_found += 1

save_sent_jobs(sent_jobs)

send_telegram(
    f"📊 Отчёт\n\n"
    f"Всего найдено: {total_found}\n"
    f"Новых: {new_found}\n"
    f"Проверка завершена."
)

print("Total:", total_found)
print("New:", new_found)
```

if **name** == "**main**":
run()
