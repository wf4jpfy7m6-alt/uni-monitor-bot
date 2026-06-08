#!/usr/bin/env python3

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
# Storage
# ==========================================

DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

SENT_FILE = DATA_DIR / "sent_jobs.json"

# ==========================================
# Search settings
# ==========================================

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

RADIUS_KM = 40
LOCATION = "Wilhelmshaven"

# ==========================================
# Helpers
# ==========================================

def load_sent():
    if not SENT_FILE.exists():
        return set()

    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_sent(ids_set):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids_set), f)


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram variables missing")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        r = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "disable_web_page_preview": False
            },
            timeout=30
        )

        print("Telegram:", r.status_code)

    except Exception as e:
        print("Telegram error:", e)


# ==========================================
# Arbeitsagentur API
# ==========================================

def search_jobs(keyword):

    url = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    params = {
        "was": keyword,
        "wo": LOCATION,
        "umkreis": RADIUS_KM,
        "page": 1
    }

    try:
        r = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30
        )

        print(keyword, "status:", r.status_code)

        if r.status_code != 200:
            return []

        data = r.json()

        jobs = []

        for item in data.get("stellenangebote", []):

            job_id = str(item.get("refnr", ""))

            title = item.get("titel", "Ohne Titel")

            company = item.get("arbeitgeber", "Unbekannt")

            location = item.get("arbeitsort", {}).get(
                "ort", "Unbekannt"
            )

            jobs.append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": location
            })

        return jobs

    except Exception as e:
        print("Search error:", keyword, e)
        return []


# ==========================================
# Main
# ==========================================

def run():

    print("=" * 50)
    print("JOB AGENT START")
    print(datetime.now())
    print("=" * 50)

    send_telegram(
        f"🔎 Проверка вакансий\n{datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

    sent_ids = load_sent()

    total_found = 0
    new_found = 0

    for keyword in SEARCH_TERMS:

        jobs = search_jobs(keyword)

        total_found += len(jobs)

        for job in jobs:

            if not job["id"]:
                continue

            if job["id"] in sent_ids:
                continue

            message = (
                f"🔔 Новая вакансия\n\n"
                f"📌 {job['title']}\n"
                f"🏢 {job['company']}\n"
                f"📍 {job['location']}\n\n"
                f"🔎 {keyword}"
            )

            send_telegram(message)

            sent_ids.add(job["id"])

            new_found += 1

    save_sent(sent_ids)

    send_telegram(
        f"📊 Отчёт\n\n"
        f"Всего найдено: {total_found}\n"
        f"Новых: {new_found}\n"
        f"Проверка завершена."
    )

    print("Total:", total_found)
    print("New:", new_found)


if __name__ == "__main__":
    run()
