import requests
import json
import datetime
import os
import csv
import time

# ---- One small function per source ----

def fetch_greenhouse(company):
    url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()

def fetch_lever(company):
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()

def fetch_ashby(company):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()

FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}

def count_jobs(data):
    if isinstance(data, list):            # Lever sends a plain list
        return len(data)
    return len(data.get("jobs", []))      # Greenhouse and Ashby send {"jobs": [...]}

# ---- Main program ----

with open("companies.csv", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

today = datetime.date.today().isoformat()
folder = f"data/raw/jobs/{today}"
os.makedirs(folder, exist_ok=True)

success, failed = 0, []

for row in rows:
    company = row["company"].strip()
    ats = row["ats"].strip().lower()
    if not company:
        continue

    fetch = FETCHERS.get(ats)
    if fetch is None:
        failed.append(f"{company} (unknown source '{ats}')")
        continue

    try:
        data = fetch(company)
    except requests.RequestException:
        failed.append(f"{ats}/{company}")
        continue

    # File name now includes the source, e.g. lever__spotify.json
    with open(f"{folder}/{ats}__{company}.json", "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"{ats}/{company}: {count_jobs(data)} jobs saved")
    success += 1
    time.sleep(0.5)

print(f"\nDone: {success} companies saved, {len(failed)} failed")
if failed:
    print("Failed:", ", ".join(failed))