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
    "Mitarbeiter Reinigung",
    "ZSVA",
    "Sterilisationsassistent",
    "Reinraum",
    "Produktionshelfer",
    "Produktionsmitarbeiter",
    "Produktionskraft",
    "Mitarbeiter Produktion",
    "Helfer Produktion",
    "Lagerhelfer",
    "Lagermitarbeiter",
    "Kommissionierer",
    "Versandmitarbeiter",
    "Logistikmitarbeiter",
    "Logistikhelfer",
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
        "umkreis": 40
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
