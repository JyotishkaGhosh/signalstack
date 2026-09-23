import json
import glob
import os
import datetime
import pandas as pd
import duckdb

# ---- One "translator" per source: turns its format into our standard columns ----

def parse_greenhouse(data):
    for job in data.get("jobs", []):
        yield {
            "job_id": str(job["id"]),
            "title": job.get("title"),
            "location": (job.get("location") or {}).get("name"),
            "job_date": job.get("updated_at"),
            "url": job.get("absolute_url"),
        }

def parse_lever(data):
    for job in data:
        created = job.get("createdAt")    # Lever gives time in milliseconds
        yield {
            "job_id": job.get("id"),
            "title": job.get("text"),
            "location": (job.get("categories") or {}).get("location"),
            "job_date": datetime.datetime.fromtimestamp(created / 1000, tz=datetime.timezone.utc).isoformat() if created else None,
            "url": job.get("hostedUrl"),
        }

def parse_ashby(data):
    for job in data.get("jobs", []):
        yield {
            "job_id": job.get("id") or job.get("jobUrl"),
            "title": job.get("title"),
            "location": job.get("location"),
            "job_date": job.get("publishedAt"),
            "url": job.get("jobUrl"),
        }

PARSERS = {"greenhouse": parse_greenhouse, "lever": parse_lever, "ashby": parse_ashby}

# ---- Main program ----

rows = []

for path in glob.glob("data/raw/jobs/*/*.json"):
    snapshot_date = os.path.basename(os.path.dirname(path))
    name = os.path.basename(path).replace(".json", "")

    # New files look like "lever__spotify"; old files are just "stripe" (Greenhouse)
    if "__" in name:
        source, company = name.split("__", 1)
    else:
        source, company = "greenhouse", name

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    for job in PARSERS[source](data):
        job["company"] = company
        job["source"] = source
        job["snapshot_date"] = snapshot_date
        rows.append(job)

df = pd.DataFrame(rows)

# Today's folder has both old-style and new-style files, so remove duplicate jobs
before = len(df)
df = df.drop_duplicates(subset=["source", "company", "job_id", "snapshot_date"])
print(f"Removed {before - len(df)} duplicate rows")

con = duckdb.connect("signalstack.duckdb")
con.execute("CREATE OR REPLACE TABLE raw_jobs AS SELECT * FROM df")
count = con.execute("SELECT COUNT(*) FROM raw_jobs").fetchone()[0]
print(f"{count} rows loaded into raw_jobs")
con.close()