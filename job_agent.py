#!/usr/bin/env python3
"""
Job Search Agent — Wilhelmshaven region
Indeed RSS + arbeitsagentur.de web scraping
"""

import json
import os
import time
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

TELEGRAM_TOKEN = os.getenv("JOB_TG_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("JOB_TG_CHAT_ID", "")
SENT_IDS_FILE = Path(__file__).parent / "sent_ids.json"

# Ключевые слова
KEYWORDS = [
    "Laborhilfe",
    "Laborassistent",
    "Laborhelfer",
    "Sterilisationsassistent",
    "ZSVA",
    "Reinraum",
    "Pharmareinigung",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def search_indeed_rss(keyword: str) -> list[dict]:
    """Indeed RSS — публичный, не требует авторизации."""
    url = "https://de.indeed.com/rss"
    params = {
        "q": keyword,
        "l": "Wilhelmshaven",
        "radius": "50",
        "fromage": "14",  # последние 14 дней
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        jobs = []
        for item in root.findall(".//item"):
            title = item.findtext("title", "—")
            link = item.findtext("link", "")
            company = item.findtext("source", "—")
            location = item.findtext("{http://www.indeed.com/}city", "") or \
                       item.findtext("{http://www.indeed.com/}country", "")
            pub_date = item.findtext("pubDate", "")
            guid = item.findtext("guid", link)
            jobs.append({
                "id": guid,
                "title": title,
                "company": company,
                "location": location,
                "date": pub_date[:16] if pub_date else "",
                "url": link,
                "source": "Indeed",
                "keyword": keyword,
            })
        return jobs
    except Exception as e:
        print(f"[Indeed/{keyword}] Ошибка: {e}")
        return []

def search_stepstone(keyword: str) -> list[dict]:
    """StepStone — крупнейший немецкий job-сайт."""
    url = "https://www.stepstone.de/5/ergebnisliste.html"
    params = {
        "stf": keyword,
        "reg": "2056",  # Niedersachsen
        "radius": "50",
        "ke": "Wilhelmshaven",
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        # Извлекаем JSON из страницы
        match = re.search(r'"@type":"JobPosting".*?"url":"([^"]+)".*?"title":"([^"]+)".*?"hiringOrganization":\{"@type":"Organization","name":"([^"]+)"', r.text)
        jobs = []
        # Простой парсинг заголовков вакансий
        titles = re.findall(r'"jobTitle":"([^"]+)"', r.text)
        urls = re.findall(r'"jobUrl":"([^"]+)"', r.text)
        companies = re.findall(r'"companyName":"([^"]+)"', r.text)
        for i, title in enumerate(titles[:10]):
            job_url = urls[i] if i < len(urls) else ""
            company = companies[i] if i < len(companies) else "—"
            jobs.append({
                "id": f"stepstone_{keyword}_{i}_{title[:20]}",
                "title": title,
                "company": company,
                "location": "Wilhelmshaven / Umgebung",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "url": f"https://www.stepstone.de{job_url}" if job_url.startswith("/") else job_url,
                "source": "StepStone",
                "keyword": keyword,
            })
        return jobs
    except Exception as e:
        print(f"[StepStone/{keyword}] Ошибка: {e}")
        return []

def search_arbeitsagentur_web(keyword: str) -> list[dict]:
    """Arbeitsagentur через веб-интерфейс с браузерными заголовками."""
    url = "https://www.arbeitsagentur.de/jobsuche/suche"
    params = {
        "was": keyword,
        "wo": "Wilhelmshaven",
        "umkreis": "50",
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        # Пробуем извлечь данные из HTML
        jobs = []
        # Ищем JSON-LD разметку
        matches = re.findall(r'"title"\s*:\s*"([^"]+)".*?"employer"\s*:\s*\{"name"\s*:\s*"([^"]+)"', r.text, re.DOTALL)
        refnrs = re.findall(r'jobdetail/([A-Z0-9\-]+)', r.text)
        for i, (title, company) in enumerate(matches[:10]):
            refnr = refnrs[i] if i < len(refnrs) else f"{keyword}_{i}"
            jobs.append({
                "id": f"ba_{refnr}",
                "title": title,
                "company": company,
                "location": "Wilhelmshaven / Umgebung",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "url": f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}",
                "source": "Arbeitsagentur",
                "keyword": keyword,
            })
        return jobs
    except Exception as e:
        print(f"[BA-Web/{keyword}] Ошибка: {e}")
        return []

def load_sent_ids() -> set:
    if SENT_IDS_FILE.exists():
        with open(SENT_IDS_FILE) as f:
            return set(json.load(f))
    return set()

def save_sent_ids(ids: set):
    with open(SENT_IDS_FILE, "w") as f:
        json.dump(list(ids), f)

def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("TG не настроен:\n" + text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"TG ошибка: {e}")

def format_job(job: dict) -> str:
    source_emoji = {"Indeed": "🔵", "StepStone": "🟠", "Arbeitsagentur": "🟢"}.get(job["source"], "⚪")
    return (
        f"🔔 <b>Новая вакансия</b> {source_emoji} {job['source']}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{job['title']}</b>\n"
        f"🏢 {job['company']}\n"
        f"📍 {job['location']}\n"
        f"📅 {job['date']}\n"
        f"🔍 <i>{job['keyword']}</i>\n"
        f"🔗 <a href=\"{job['url']}\">Открыть вакансию</a>"
    )

def run():
    print(f"\n{'='*50}")
    print(f"Job Agent запущен: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    sent_ids = load_sent_ids()
    all_jobs = []
    seen = set()

    for kw in KEYWORDS:
        # Indeed RSS
        jobs = search_indeed_rss(kw)
        print(f"[Indeed/{kw}]: {len(jobs)} вакансий")
        for j in jobs:
            if j["id"] not in seen:
                seen.add(j["id"])
                all_jobs.append(j)
        time.sleep(1)

        # Arbeitsagentur web
        jobs2 = search_arbeitsagentur_web(kw)
        print(f"[BA-Web/{kw}]: {len(jobs2)} вакансий")
        for j in jobs2:
            if j["id"] not in seen:
                seen.add(j["id"])
                all_jobs.append(j)
        time.sleep(1)

    print(f"\nУникальных вакансий: {len(all_jobs)}")

    new_count = 0
    for job in all_jobs:
        if job["id"] not in sent_ids:
            msg = format_job(job)
            send_telegram(msg)
            sent_ids.add(job["id"])
            new_count += 1
            time.sleep(0.5)

    save_sent_ids(sent_ids)
    print(f"Новых отправлено: {new_count}")

    if new_count > 0:
        send_telegram(f"📊 <b>Итог:</b> найдено <b>{new_count}</b> новых вакансий")

if __name__ == "__main__":
    run()
