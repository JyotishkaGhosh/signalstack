import json
import glob
import os
import re
import csv
import datetime
import shutil
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

HISTORY = "data/job_history.parquet"   # one row per job ever seen; committed to the repo
KEEP_RAW_DAYS = 3                      # raw JSON is only kept locally (it is not committed)

rows = []
snapshots = set()                     # (source, feed, date) for every raw file read in this run

# Usually just today's files: GitHub Actions starts with an empty data/raw/
for path in sorted(glob.glob("data/raw/jobs/*/*.json")):
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

    snapshots.add((source, feed, snapshot_date))
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

# Named columns so an empty data/raw/ still gives a table with the right shape
df = pd.DataFrame(rows, columns=list(job()) + ["source", "feed", "snapshot_date"])
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

# ---- Job history: first and last day we saw each job, plus its details from the last day ----
# prev_seen is the sighting before last_seen, so a board fetched twice on one day can be undone and redone
FIELDS = "title, company, location, job_date, url, city, region, country, remote_hint, level_hint, department_hint, min_years"
if os.path.exists(HISTORY):
    con.execute(f"CREATE OR REPLACE TABLE job_history AS SELECT * FROM read_parquet('{HISTORY}')")
else:
    print(f"No {HISTORY} yet, starting a new history")
    con.execute(f"""CREATE OR REPLACE TABLE job_history AS
        SELECT source, feed, job_id, {FIELDS},
               NULL::DATE AS first_seen, NULL::DATE AS last_seen, NULL::DATE AS prev_seen
        FROM raw_jobs LIMIT 0""")

for day in sorted({d for _, _, d in snapshots}):
    feeds = pd.DataFrame([(s, f) for s, f, d in snapshots if d == day], columns=["source", "feed"])
    con.execute("CREATE OR REPLACE TEMP TABLE day_feeds AS SELECT * FROM feeds")
    # Compare each board's file with the last day already in the history:
    # older -> already merged, skip; same day -> a re-run, undo that day first; newer -> merge
    con.execute("""
        CREATE OR REPLACE TEMP TABLE targets AS
        SELECT d.source, d.feed, h.latest = CAST(? AS DATE) AS rerun
        FROM day_feeds d
        LEFT JOIN (SELECT source, feed, MAX(last_seen) AS latest FROM job_history GROUP BY 1, 2) h USING (source, feed)
        WHERE h.latest IS NULL OR h.latest <= CAST(? AS DATE)
    """, [day, day])
    con.execute("""
        DELETE FROM job_history h USING targets t
        WHERE t.rerun AND h.source = t.source AND h.feed = t.feed AND h.first_seen = CAST(? AS DATE)
    """, [day])
    con.execute("""
        UPDATE job_history h SET last_seen = prev_seen, prev_seen = NULL FROM targets t
        WHERE t.rerun AND h.source = t.source AND h.feed = t.feed AND h.last_seen = CAST(? AS DATE)
    """, [day])
    con.execute(f"""
        CREATE OR REPLACE TABLE job_history AS
        WITH seen AS (
            SELECT r.* FROM raw_jobs r JOIN targets t USING (source, feed)
            WHERE r.snapshot_date = ? AND r.job_id IS NOT NULL
        )
        SELECT s.source, s.feed, s.job_id, {", ".join("s." + c for c in FIELDS.split(", "))},
               COALESCE(h.first_seen, CAST(? AS DATE)) AS first_seen,
               CAST(? AS DATE) AS last_seen,
               h.last_seen AS prev_seen
        FROM seen s LEFT JOIN job_history h USING (source, feed, job_id)
        UNION ALL
        SELECT h.* FROM job_history h ANTI JOIN seen s USING (source, feed, job_id)
    """, [day, day, day])

# Sorted and uncompressed so git can store each day's version as a small delta
# (git compresses it anyway; a compressed file would add its full size to the repo every day)
os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
con.execute(f"""COPY (SELECT * FROM job_history ORDER BY source, feed, job_id)
                TO '{HISTORY}' (FORMAT parquet, COMPRESSION uncompressed)""")
total, open_now = con.execute("""
    SELECT COUNT(*), COUNT(*) FILTER (WHERE last_seen = latest)
    FROM (SELECT last_seen, MAX(last_seen) OVER (PARTITION BY source, feed) AS latest FROM job_history)
""").fetchone()
print(f"{HISTORY}: {total} jobs tracked, {open_now} on their board's latest list "
      f"({os.path.getsize(HISTORY) / 1e6:.1f} MB)")
con.close()

# Raw files are only needed until they are in the history; keep a few days locally for debugging
cutoff = (datetime.date.today() - datetime.timedelta(days=KEEP_RAW_DAYS)).isoformat()
for folder in glob.glob("data/raw/jobs/*"):
    day = os.path.basename(folder)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) and day < cutoff:
        shutil.rmtree(folder)
        print(f"Deleted old raw folder {folder}")
