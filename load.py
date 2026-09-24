import json
import glob
import os
import re
import csv
import datetime
import pandas as pd
import duckdb

# ---- Small helpers shared by the parsers ----

def to_date(value):
    """Turn the many date formats sources use into 'YYYY-MM-DD' (or None)."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):               # Unix time: Lever uses ms, Arbeitnow seconds
        seconds = value / 1000 if value > 1e11 else value
        return datetime.datetime.fromtimestamp(seconds, tz=datetime.timezone.utc).date().isoformat()
    match = re.match(r"\d{4}-\d{2}-\d{2}", str(value))
    return match.group(0) if match else None

YEARS = re.compile(r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to)?\s*(?:\d{1,2})?\s*\+?\s*(?:years?|yrs?)\b[^.\n]{0,40}?\bexperience", re.I)

def min_years(text):
    """Smallest 'N years ... experience' mentioned in a description, if any."""
    if not text:
        return None
    text = re.sub(r"<[^>]+>", " ", str(text))
    found = [int(m.group(1)) for m in YEARS.finditer(text) if int(m.group(1)) <= 20]
    return min(found) if found else None

def job(**fields):
    """One row in our standard columns. Anything a source doesn't provide stays empty."""
    row = {
        "job_id": None, "title": None, "company": None, "location": None, "job_date": None, "url": None,
        # Optional hints some sources give us; transform.py uses them for better labels
        "city": None, "region": None, "country": None, "remote_hint": None,
        "level_hint": None, "department_hint": None, "min_years": None,
    }
    row.update(fields)
    row["job_id"] = None if row["job_id"] is None else str(row["job_id"])
    row["title"] = (row["title"] or "").strip() or None
    return row


# ---- One "translator" per source: turns its format into our standard columns ----

def parse_greenhouse(data, company):
    for j in data.get("jobs", []):
        yield job(job_id=j["id"], title=j.get("title"), company=j.get("company_name") or company,
                  location=(j.get("location") or {}).get("name"),
                  job_date=to_date(j.get("first_published") or j.get("updated_at")),
                  url=j.get("absolute_url"))

def parse_lever(data, company):
    for j in data:
        cats = j.get("categories") or {}
        workplace = j.get("workplaceType")
        yield job(job_id=j.get("id"), title=j.get("text"), company=company,
                  location=cats.get("location"), job_date=to_date(j.get("createdAt")), url=j.get("hostedUrl"),
                  country=j.get("country"),
                  remote_hint=workplace if workplace in ("remote", "hybrid", "onsite") else None,
                  level_hint=cats.get("commitment"), department_hint=cats.get("department") or cats.get("team"),
                  min_years=min_years(j.get("descriptionPlain")))

def parse_ashby(data, company):
    for j in data.get("jobs", []):
        address = ((j.get("address") or {}).get("postalAddress")) or {}
        workplace = (j.get("workplaceType") or "").lower()      # "Remote", "Hybrid" or "OnSite"
        yield job(job_id=j.get("id") or j.get("jobUrl"), title=j.get("title"), company=company,
                  location=j.get("location"), job_date=to_date(j.get("publishedAt")), url=j.get("jobUrl"),
                  city=address.get("addressLocality"), region=address.get("addressRegion"),
                  country=address.get("addressCountry"),
                  remote_hint=workplace if workplace in ("remote", "hybrid", "onsite") else ("remote" if j.get("isRemote") else None),
                  level_hint=j.get("employmentType"), department_hint=j.get("department"),
                  min_years=min_years(j.get("descriptionPlain")))

def parse_workable(data, company):
    for j in data.get("jobs", []):
        parts = [j.get("city"), j.get("state"), j.get("country")]
        yield job(job_id=j.get("shortcode"), title=j.get("title"), company=data.get("name") or company,
                  location=", ".join(p for p in parts if p) or None,
                  job_date=to_date(j.get("published_on") or j.get("created_at")), url=j.get("url"),
                  city=j.get("city"), region=j.get("state"), country=j.get("country"),
                  remote_hint="remote" if j.get("telecommuting") else None,
                  level_hint=j.get("experience"), department_hint=j.get("function") or j.get("department"))

def parse_smartrecruiters(data, company):
    for j in data.get("content", []):
        loc = j.get("location") or {}
        ident = (j.get("company") or {}).get("identifier") or company
        parts = [loc.get("city"), loc.get("region"), loc.get("country", "").upper() or None]
        yield job(job_id=j.get("id"), title=j.get("name"), company=(j.get("company") or {}).get("name") or company,
                  location=", ".join(p for p in parts if p) or None,
                  job_date=to_date(j.get("releasedDate")),
                  url=f"https://jobs.smartrecruiters.com/{ident}/{j.get('id')}",
                  city=loc.get("city"), region=loc.get("region"), country=loc.get("country"),
                  remote_hint="remote" if loc.get("remote") else ("hybrid" if loc.get("hybrid") else None),
                  level_hint=(j.get("experienceLevel") or {}).get("id"),
                  department_hint=(j.get("function") or {}).get("label"))

def parse_recruitee(data, company):
    for j in data.get("offers", []):
        remote = "remote" if j.get("remote") else "hybrid" if j.get("hybrid") else "onsite" if j.get("on_site") else None
        yield job(job_id=j.get("id"), title=j.get("title"), company=j.get("company_name") or company,
                  location=j.get("location"), job_date=to_date(j.get("published_at") or j.get("created_at")),
                  url=j.get("careers_url"),
                  city=j.get("city"), region=j.get("state_name"), country=j.get("country"),
                  remote_hint=remote, level_hint=j.get("experience_code"), department_hint=j.get("department"),
                  min_years=min_years(j.get("requirements")) or min_years(j.get("description")))

def parse_remotive(data, _):
    for j in data.get("jobs", []):
        yield job(job_id=j.get("id"), title=j.get("title"), company=j.get("company_name"),
                  location=j.get("candidate_required_location"), job_date=to_date(j.get("publication_date")),
                  url=j.get("url"), remote_hint="remote", department_hint=j.get("category"),
                  min_years=min_years(j.get("description")))

def parse_arbeitnow(data, _):
    for j in data.get("data", []):
        yield job(job_id=j.get("slug"), title=j.get("title"), company=j.get("company_name"),
                  location=j.get("location"), job_date=to_date(j.get("created_at")), url=j.get("url"),
                  remote_hint="remote" if j.get("remote") else None,
                  department_hint=(j.get("tags") or [None])[0], min_years=min_years(j.get("description")))

def parse_themuse(data, _):
    for j in data.get("results", []):
        names = [l.get("name") for l in j.get("locations") or [] if l.get("name")]
        yield job(job_id=j.get("id"), title=j.get("name"), company=(j.get("company") or {}).get("name"),
                  location="; ".join(names) or None, job_date=to_date(j.get("publication_date")),
                  url=(j.get("refs") or {}).get("landing_page"),
                  level_hint=((j.get("levels") or [{}])[0]).get("name"),
                  department_hint=((j.get("categories") or [{}])[0]).get("name"),
                  min_years=min_years(j.get("contents")))

def parse_adzuna(data, _):
    for j in data.get("results", []):
        loc = j.get("location") or {}
        area = loc.get("area") or []       # e.g. ["India", "Karnataka", "Bangalore"]
        yield job(job_id=j.get("id"), title=j.get("title"), company=(j.get("company") or {}).get("display_name"),
                  location=loc.get("display_name"), job_date=to_date(j.get("created")), url=j.get("redirect_url"),
                  country=area[0] if area else None, region=area[1] if len(area) > 1 else None,
                  city=area[-1] if len(area) > 2 else None,
                  department_hint=(j.get("category") or {}).get("label"), min_years=min_years(j.get("description")))

PARSERS = {
    "greenhouse": parse_greenhouse, "lever": parse_lever, "ashby": parse_ashby,
    "workable": parse_workable, "smartrecruiters": parse_smartrecruiters, "recruitee": parse_recruitee,
    "remotive": parse_remotive, "arbeitnow": parse_arbeitnow, "themuse": parse_themuse, "adzuna": parse_adzuna,
}

# ---- Main program ----

# Display names for company boards (Lever and Ashby don't send one)
with open("companies.csv", encoding="utf-8") as f:
    names = {r["company"].strip(): (r.get("name") or "").strip() for r in csv.DictReader(f)}

rows = []

for path in glob.glob("data/raw/jobs/*/*.json"):
    snapshot_date = os.path.basename(os.path.dirname(path))
    name = os.path.basename(path).replace(".json", "")

    # New files look like "lever__spotify" or "remotive__all"; old files are just "stripe" (Greenhouse)
    if "__" in name:
        source, feed = name.split("__", 1)
    else:
        source, feed = "greenhouse", name

    parse = PARSERS.get(source)
    if parse is None:
        print(f"Skipping {path}: no parser for '{source}'")
        continue

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        company = names.get(feed) or feed.replace("-", " ").title()
        for r in parse(data, company):
            if not r["title"]:
                continue
            r["source"] = source
            r["feed"] = feed
            r["snapshot_date"] = snapshot_date
            rows.append(r)
    except Exception as e:                    # a broken file should not stop the load
        print(f"Could not read {path}: {e}")

df = pd.DataFrame(rows)
text_cols = [c for c in df.columns if c != "min_years"]
df[text_cols] = df[text_cols].astype("string")
df["min_years"] = df["min_years"].astype("Int64")

# Some days have both old-style and new-style files for the same board, so remove duplicate jobs
before = len(df)
df = df.drop_duplicates(subset=["source", "feed", "job_id", "snapshot_date"])
print(f"Removed {before - len(df)} duplicate rows")

con = duckdb.connect("signalstack.duckdb")
con.execute("CREATE OR REPLACE TABLE raw_jobs AS SELECT * FROM df")
count = con.execute("SELECT COUNT(*) FROM raw_jobs").fetchone()[0]
print(f"{count} rows loaded into raw_jobs")
print(con.sql("SELECT source, COUNT(*) AS rows FROM raw_jobs GROUP BY 1 ORDER BY 2 DESC"))
con.close()
