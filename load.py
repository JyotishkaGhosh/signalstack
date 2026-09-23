import json
import glob
import os
import pandas as pd
import duckdb

rows = []

# Go through every saved JSON file, from every day
for path in glob.glob("data/raw/jobs/*/*.json"):
    snapshot_date = os.path.basename(os.path.dirname(path))   # folder name = date
    company = os.path.basename(path).replace(".json", "")     # file name = company

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # Keep only the useful fields from each job
    for job in data.get("jobs", []):
        rows.append({
            "job_id": job["id"],
            "company": company,
            "title": job.get("title"),
            "location": (job.get("location") or {}).get("name"),
            "updated_at": job.get("updated_at"),
            "url": job.get("absolute_url"),
            "snapshot_date": snapshot_date,
        })

df = pd.DataFrame(rows)

con = duckdb.connect("signalstack.duckdb")      # creates the database file
con.execute("CREATE OR REPLACE TABLE raw_jobs AS SELECT * FROM df")
count = con.execute("SELECT COUNT(*) FROM raw_jobs").fetchone()[0]
print(f"{count} rows loaded into raw_jobs")
con.close()