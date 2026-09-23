import requests
import json
import datetime
import os
import csv
import time

# Read the company list from companies.csv
with open("companies.csv", encoding="utf-8") as f:
    COMPANIES = [row["company"].strip() for row in csv.DictReader(f) if row["company"].strip()]

today = datetime.date.today().isoformat()
folder = f"data/raw/jobs/{today}"
os.makedirs(folder, exist_ok=True)

success, failed = 0, []

for company in COMPANIES:
    url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        failed.append(company)
        continue

    data = response.json()
    with open(f"{folder}/{company}.json", "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"{company}: {len(data['jobs'])} jobs saved")
    success += 1
    time.sleep(0.5)   # wait half a second between requests, to be polite to the website

print(f"\nDone: {success} companies saved, {len(failed)} failed")
if failed:
    print("Failed:", ", ".join(failed))