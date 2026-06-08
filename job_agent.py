#!/usr/bin/env python3
"""
Job Search Agent — Wilhelmshaven region
Bundesagentur für Arbeit API + Telegram notifications
"""

import json
import os
import time
import requests
from datetime import datetime
from pathlib import Path

# ── Конфиг ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("JOB_TG_TOKEN", "")       # токен бота
TELEGRAM_CHAT_ID = os.getenv("JOB_TG_CHAT_ID", "")   # твой chat_id

SENT_IDS_FILE = Path(__file__).parent / "sent_ids.json"

# Радиус поиска в км от Wilhelmshaven (координаты: 53.5285, 8.1133)
# BA API принимает координаты + umkreis
SEARCH_CONFIG = {
    "latitude": 53.5285,
    "longitude": 8.1133,
    "umkreis": 50,          # км радиус (50 = WHV + Friesland + Ostfriesland)
    "angebotsart": 1,       # 1 = Arbeit (работа), 4 = Ausbildung
    "zeitarbeits_filter": False,  # True = исключить Zeitarbeit
}

# Ключевые слова для поиска (каждое — отдельный запрос к API)
SEARCH_KEYWORDS = [
    "Laborhilfe",
    "Laborassistent Quereinsteiger",
    "ZSVA Sterilisation",
    "Sterilisationsassistent",
    "Reinigungskraft Reinraum",
    "Pharmareinigung",
    "Reinraummitarbeiter",
    "Reinraum Mitarbeiter",
    "Laborhelfer",
]

# ── BA API ───────────────────────────────────────────────────────────────────
BA_API_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"

BA_HEADERS = {
    "User-Agent": "Jobsuche/2.9.2 (de.arbeitsagentur.app.android)",
    "OAuthAccessToken": "anonymousKey",
    "X-API-Key": "jobboerse-jobsuche-ui",
}

def search_jobs(keyword: str) -> list[dict]:
    """Запрос к BA API по одному ключевому слову."""
    params = {
        "was": keyword,
        "wo": "Wilhelmshaven",
        "umkreis": SEARCH_CONFIG["umkreis"],
        "angebotsart": SEARCH_CONFIG["angebotsart"],
        "size": 50,
        "page": 1,
        "pav": "false",   # включая befristet
        "ban": "false",
    }
    try:
        r = requests.get(BA_API_URL, headers=BA_HEADERS, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("stellenangebote") or []
    except Exception as e:
        print(f"[{keyword}] Ошибка API: {e}")
        return []

# ── Хранилище отправленных ID ─────────────────────────────────────────────
def load_sent_ids() -> set:
    if SENT_IDS_FILE.exists():
        with open(SENT_IDS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_sent_ids(ids: set):
    with open(SENT_IDS_FILE, "w") as f:
        json.dump(list(ids), f)

# ── Telegram ──────────────────────────────────────────────────────────────
def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Telegram не настроен — вывожу в консоль:\n" + text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"Telegram ошибка: {e}")

def format_job_message(job: dict, keyword: str) -> str:
    title = job.get("titel", "—")
    company = job.get("arbeitgeber", "—")
    location = job.get("arbeitsort", {})
    city = location.get("ort", "—")
    plz = location.get("plz", "")
    date_str = job.get("eintrittsdatum") or job.get("aktuelleVeroeffentlichungsdatum", "")
    ref_nr = job.get("refnr", "")
    url = f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref_nr}" if ref_nr else ""

    # Тип занятости
    arbeit_types = job.get("arbeitszeitmodelle") or []
    zeit = ", ".join(arbeit_types) if arbeit_types else "—"

    msg = (
        f"🔔 <b>Новая вакансия</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{title}</b>\n"
        f"🏢 {company}\n"
        f"📍 {plz} {city}\n"
        f"🕐 {zeit}\n"
        f"📅 {date_str or '—'}\n"
        f"🔍 Найдено по: <i>{keyword}</i>\n"
    )
    if url:
        msg += f"🔗 <a href=\"{url}\">Открыть вакансию</a>"
    return msg

# ── Главный цикл ─────────────────────────────────────────────────────────
def run():
    print(f"\n{'='*50}")
    print(f"Job Agent запущен: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    sent_ids = load_sent_ids()
    new_count = 0
    all_jobs: list[tuple[dict, str]] = []  # (job, keyword)

    # Собираем вакансии по всем ключевым словам
    seen_in_run = set()
    for kw in SEARCH_KEYWORDS:
        jobs = search_jobs(kw)
        print(f"[{kw}]: найдено {len(jobs)} вакансий")
        for job in jobs:
            ref = job.get("refnr")
            if ref and ref not in seen_in_run:
                seen_in_run.add(ref)
                all_jobs.append((job, kw))
        time.sleep(1)  # вежливая пауза между запросами

    print(f"\nУникальных вакансий всего: {len(all_jobs)}")

    # Отправляем только новые
    for job, kw in all_jobs:
        ref = job.get("refnr")
        if not ref:
            continue
        if ref not in sent_ids:
            msg = format_job_message(job, kw)
            send_telegram(msg)
            sent_ids.add(ref)
            new_count += 1
            time.sleep(0.5)

    save_sent_ids(sent_ids)

    summary = f"✅ Проверка завершена: {datetime.now().strftime('%H:%M')} — новых вакансий: {new_count}"
    print(summary)

    # Отправляем сводку только если есть новые вакансии (не спамим)
    if new_count > 0:
        send_telegram(f"\n📊 <b>Итог проверки:</b> найдено <b>{new_count}</b> новых вакансий")

if __name__ == "__main__":
    run()
