import requests
import json
import datetime
import os
import csv
import time

# Identify ourselves politely to every API we call
HEADERS = {"User-Agent": "SignalStack job tracker (https://github.com/JyotishkaGhosh/signalstack)"}


def load_env(path=".env"):
    """Read KEY=value lines from a local .env file (GitHub Actions uses secrets instead)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_json(url, params=None):
    response = requests.get(url, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


# ---- Company job boards: one small function per source, called once per company ----

def fetch_greenhouse(company):
    return get_json(f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs")

def fetch_lever(company):
    return get_json(f"https://api.lever.co/v0/postings/{company}?mode=json")

def fetch_ashby(company):
    return get_json(f"https://api.ashbyhq.com/posting-api/job-board/{company}")

def fetch_workable(company):
    # Public widget API that Workable offers for embedding job lists
    return get_json(f"https://apply.workable.com/api/v1/widget/accounts/{company}")

def fetch_smartrecruiters(company, max_pages=5):
    # Posting API returns 100 jobs per page; big employers are capped at max_pages
    jobs = []
    for page in range(max_pages):
        data = get_json(f"https://api.smartrecruiters.com/v1/companies/{company}/postings",
                        {"limit": 100, "offset": page * 100})
        jobs += data.get("content", [])
        if len(jobs) >= data.get("totalFound", 0) or not data.get("content"):
            break
        time.sleep(0.5)
    return {"content": jobs}

def fetch_recruitee(company):
    return get_json(f"https://{company}.recruitee.com/api/offers/")


# ---- Job boards that cover many companies: called once per run ----

def fetch_remotive():
    # Remotive asks for at most 4 calls a day, a link back to each job and credit as the source
    return get_json("https://remotive.com/api/remote-jobs")

def fetch_arbeitnow(max_pages=2):
    # Free public API, 250 jobs per page; they ask for a link back
    jobs = []
    for page in range(1, max_pages + 1):
        data = get_json("https://www.arbeitnow.com/api/job-board-api", {"page": page})
        jobs += data.get("data", [])
        if not data.get("links", {}).get("next"):
            break
        time.sleep(1)
    return {"data": jobs}

def fetch_themuse():
    # No key needed for up to 500 calls an hour; we make about 15
    searches = [("India", 10), ("Flexible / Remote", 5)]
    jobs = []
    for location, pages in searches:
        for page in range(pages):
            data = get_json("https://www.themuse.com/api/public/jobs", {"location": location, "page": page})
            jobs += data.get("results", [])
            if page + 1 >= data.get("page_count", 0):
                break
            time.sleep(1)
    return {"results": jobs}

def fetch_adzuna(max_pages=5):
    # Needs a free key from developer.adzuna.com, stored in .env or GitHub secrets
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise RuntimeError("ADZUNA_APP_ID / ADZUNA_APP_KEY not set")
    jobs = []
    for page in range(1, max_pages + 1):
        data = get_json(f"https://api.adzuna.com/v1/api/jobs/in/search/{page}", {
            "app_id": app_id, "app_key": app_key, "results_per_page": 50,
            "sort_by": "date", "max_days_old": 30, "content-type": "application/json",
        })
        jobs += data.get("results", [])
        if len(data.get("results", [])) < 50:
            break
        time.sleep(3)  # free plan allows 25 calls a minute
    return {"results": jobs}


COMPANY_FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "workable": fetch_workable,
    "smartrecruiters": fetch_smartrecruiters,
    "recruitee": fetch_recruitee,
}

BOARD_FETCHERS = {
    "remotive": fetch_remotive,
    "arbeitnow": fetch_arbeitnow,
    "themuse": fetch_themuse,
    "adzuna": fetch_adzuna,
}

def count_jobs(data):
    if isinstance(data, list):            # Lever sends a plain list
        return len(data)
    for key in ("jobs", "content", "offers", "data", "results"):
        if isinstance(data.get(key), list):
            return len(data[key])
    return 0

# ---- Main program ----

load_env()

with open("companies.csv", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

today = datetime.date.today().isoformat()
folder = f"data/raw/jobs/{today}"
os.makedirs(folder, exist_ok=True)

# Every task is (source, name, fetch function). Boards are saved as e.g. remotive__all.json
tasks = []
for row in rows:
    company = row["company"].strip()
    ats = row["ats"].strip().lower()
    if not company:
        continue
    fetch = COMPANY_FETCHERS.get(ats)
    if fetch is None:
        print(f"Skipping {company}: unknown source '{ats}'")
        continue
    tasks.append((ats, company, lambda fetch=fetch, company=company: fetch(company)))
for source, fetch in BOARD_FETCHERS.items():
    tasks.append((source, "all", fetch))

success, failed = 0, []
per_source = {}

for source, name, fetch in tasks:
    try:
        data = fetch()
    except Exception as e:                # one broken source should never stop the run
        failed.append(f"{source}/{name} ({e})")
        print(f"{source}/{name}: FAILED - {e}")
        continue

    # File name includes the source, e.g. lever__spotify.json
    with open(f"{folder}/{source}__{name}.json", "w", encoding="utf-8") as f:
        json.dump(data, f)
    n = count_jobs(data)
    per_source[source] = per_source.get(source, 0) + n
    print(f"{source}/{name}: {n} jobs saved")
    success += 1
    time.sleep(0.5)

print(f"\nDone: {success} feeds saved, {len(failed)} failed")
for source, n in sorted(per_source.items(), key=lambda x: -x[1]):
    print(f"  {source:16} {n:6} jobs")
if failed:
    print("Failed:\n  " + "\n  ".join(failed))
