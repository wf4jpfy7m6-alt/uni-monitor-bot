import os
import json
import requests
from pathlib import Path
from datetime import datetime

# ==========================================
# Telegram
# ==========================================

TELEGRAM_TOKEN = os.getenv("JOB_TG_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("JOB_TG_CHAT_ID", "")

# ==========================================
# Files
# ==========================================

DATA_FILE = Path("sent_jobs.json")

# ==========================================
# Arbeitsagentur API
# ==========================================

API_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "X-API-Key": "jobboerse-jobsuche"
}

# ==========================================
# Keywords
# ==========================================

SEARCH_TERMS = [
    "Reinigungskraft",
    "Gebäudereiniger",

    "Reinraum",
    "ZSVA",
    "Sterilisationsassistent",

    "Produktionshelfer",
    "Produktionsmitarbeiter",

    "Lagerhelfer",
    "Kommissionierer",

    "Quereinsteiger"
]
# ==========================================
# Telegram
# ==========================================

def send_telegram(text):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram variables missing")
        return

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


# ==========================================
# Storage
# ==========================================

def load_sent_jobs():

    if not DATA_FILE.exists():
        return set()

    try:

        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))

    except Exception:

        return set()


def save_sent_jobs(job_ids):

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(list(job_ids), f)


# ==========================================
# Search
# ==========================================

def search_jobs(keyword):

    params = {
        "was": keyword,
        "wo": "Wilhelmshaven",
        "umkreis": 15
    }

    try:

        response = requests.get(
            API_URL,
            headers=HEADERS,
            params=params,
            timeout=30
        )

        if response.status_code != 200:

            print(
                keyword,
                "status:",
                response.status_code
            )

            return []

        data = response.json()

        return data.get(
            "stellenangebote",
            []
        )

    except Exception as e:

        print(
            "Search error:",
            keyword,
            str(e)
        )

        return []
# ==========================================
# Formatting
# ==========================================

def format_job(job, keyword):

    title = job.get("titel", "Без названия")

    company = job.get(
        "arbeitgeber",
        "Не указан"
    )

    city = (
        job.get("arbeitsort", {})
        .get("ort", "Не указан")
    )

    date = job.get(
        "aktuelleVeroeffentlichungsdatum",
        "-"
    )

    link = (
        job.get("externeUrl")
        or f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{job.get('refnr')}"
    )

    return (
        f"🔔 Новая вакансия\n\n"
        f"📌 {title}\n"
        f"🏢 {company}\n"
        f"📍 {city}\n"
        f"📅 {date}\n"
        f"🔎 {keyword}\n\n"
        f"🔗 {link}"
    )


# ==========================================
# Main
# ==========================================

def run():

    print("=" * 50)
    print("JOB AGENT START")
    print(datetime.now())
    print("=" * 50)

    sent_jobs = load_sent_jobs()

    total_found = 0
    new_found = 0

    for keyword in SEARCH_TERMS:

        jobs = search_jobs(keyword)

        print(
            f"{keyword}: {len(jobs)} jobs"
        )

        total_found += len(jobs)

        for job in jobs:

            job_id = job.get("refnr")

            if not job_id:
                continue

            if job_id in sent_jobs:
                continue

            send_telegram(
                format_job(
                    job,
                    keyword
                )
            )

            sent_jobs.add(job_id)

            new_found += 1

    save_sent_jobs(sent_jobs)

    report = (
        f"📊 Отчёт\n\n"
        f"Всего найдено: {total_found}\n"
        f"Новых вакансий: {new_found}\n"
        f"Проверка завершена."
    )

    send_telegram(report)

    print("Total:", total_found)
    print("New:", new_found)


if __name__ == "__main__":
    run()
