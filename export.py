"""Export the final tables from DuckDB into site/data.json for the dashboard."""
import datetime
import json
import os

import duckdb

con = duckdb.connect("signalstack.duckdb", read_only=True)


def rows(sql):
    """Run a SQL query and return the result as a list of plain dictionaries."""
    df = con.sql(sql).df()
    return json.loads(df.to_json(orient="records", date_format="iso"))


# Final score table: one row per company
companies = rows("""
    SELECT company, source, hot_score, open_jobs, engineering_jobs,
           sales_jobs, india_jobs, remote_jobs
    FROM company_scores
    ORDER BY hot_score DESC
""")

# Every job from each company's most recent day of data
jobs = rows("""
    WITH latest AS (
        SELECT company, MAX(snapshot_date) AS latest_date
        FROM jobs_clean
        GROUP BY company
    )
    SELECT j.company, j.source, j.title, j.department, j.location, j.url,
           j.is_india, j.is_remote
    FROM jobs_clean j
    JOIN latest l
      ON j.company = l.company AND j.snapshot_date = l.latest_date
    ORDER BY j.company, j.department, j.title
""")

# Open jobs per company per day (powers the trend charts)
history = rows("""
    SELECT CAST(snapshot_date AS VARCHAR) AS date, company, COUNT(*) AS open_jobs
    FROM jobs_clean
    GROUP BY 1, 2
    ORDER BY 1, 2
""")

data_date = con.sql("SELECT CAST(MAX(snapshot_date) AS VARCHAR) FROM jobs_clean").fetchone()[0]
con.close()

output = {
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "data_date": data_date,
    "companies": companies,
    "jobs": jobs,
    "history": history,
}

os.makedirs("site", exist_ok=True)
with open("site/data.json", "w", encoding="utf-8") as f:
    json.dump(output, f)

print(f"Exported {len(companies)} companies, {len(jobs)} jobs, "
      f"{len(history)} history points -> site/data.json")
