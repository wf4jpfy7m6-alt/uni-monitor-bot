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
