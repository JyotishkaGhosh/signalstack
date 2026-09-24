"""Export the current job list from DuckDB into site/data.json for the website."""
import datetime
import json
import os
import re

import duckdb

# Display name and home page for each source, used for the credits in the site footer
SOURCES = {
    "greenhouse": ("Greenhouse", "https://www.greenhouse.com"),
    "lever": ("Lever", "https://www.lever.co"),
    "ashby": ("Ashby", "https://www.ashbyhq.com"),
    "workable": ("Workable", "https://www.workable.com"),
    "smartrecruiters": ("SmartRecruiters", "https://www.smartrecruiters.com"),
    "recruitee": ("Recruitee", "https://recruitee.com"),
    "remotive": ("Remotive", "https://remotive.com"),
    "arbeitnow": ("Arbeitnow", "https://www.arbeitnow.com"),
    "themuse": ("The Muse", "https://www.themuse.com"),
    "adzuna": ("Adzuna", "https://www.adzuna.in"),
}

con = duckdb.connect("signalstack.duckdb", read_only=True)

# Short field names keep the file small; the site maps them back
FIELDS = ["id", "title", "company", "location", "city", "state", "country", "workplace",
          "role", "level", "group", "source", "posted", "first_seen", "new", "url"]

result = con.sql("""
    SELECT uid, title, company,
           -- Sources that send separate city/state/country fields get the cleaned names;
           -- the rest keep their own wording, which can list several cities
           CASE WHEN source IN ('smartrecruiters', 'workable', 'recruitee', 'adzuna')
                     AND (city IS NOT NULL OR country IS NOT NULL)
                THEN concat_ws(', ', city, state, country)
                ELSE COALESCE(NULLIF(trim(location), ''), concat_ws(', ', city, state, country))
           END AS location,
           city, state, country, workplace, role_type, level, experience_group, source,
           CAST(posted_date AS VARCHAR), CAST(first_seen AS VARCHAR), is_new, url
    FROM jobs_listed
    WHERE url ILIKE 'http%'
    -- Same-day ties: direct company boards before aggregators
    ORDER BY posted_date DESC,
             source IN ('remotive', 'arbeitnow', 'themuse', 'adzuna'),
             company, title
""").fetchall()
jobs = [list(r) for r in result]

counts = dict(con.sql("SELECT source, COUNT(*) FROM jobs_listed WHERE url ILIKE 'http%' GROUP BY 1").fetchall())
data_date = con.sql("SELECT CAST(MAX(snapshot_date) AS VARCHAR) FROM jobs_clean").fetchone()[0]
history_start, history_end, history_days = con.sql("""
    SELECT CAST(MIN(first_seen) AS VARCHAR), CAST(MAX(last_seen) AS VARCHAR),
           date_diff('day', MIN(first_seen), MAX(last_seen)) + 1
    FROM job_history
""").fetchone()
con.close()

output = {
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "data_date": data_date,
    "sources": [{"id": k, "name": n, "url": u, "jobs": counts.get(k, 0)} for k, (n, u) in SOURCES.items()],
    "fields": FIELDS,
    "jobs": jobs,
}

os.makedirs("site", exist_ok=True)
with open("site/data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

# ---- Refresh the stats line in README.md (between the stats markers) ----
active = sum(1 for v in counts.values() if v)
companies = len({j[FIELDS.index("company")] for j in jobs})
sources_note = f" ({active} returned jobs in that run)" if active < len(SOURCES) else ""
stats = (f"As of the {data_date} run: {len(jobs):,} open jobs from {companies:,} companies, "
         f"collected from {len(SOURCES)} configured sources{sources_note}, "
         f"with {history_days} day{'s' if history_days != 1 else ''} of history ({history_start} to {history_end}).")
if os.path.exists("README.md"):
    with open("README.md", encoding="utf-8") as f:
        readme = f.read()
    updated = re.sub(r"(<!-- stats:start -->\n).*?(\n<!-- stats:end -->)",
                     lambda m: m.group(1) + stats + m.group(2), readme, flags=re.S)
    if updated == readme and stats not in readme:
        print("README.md has no stats markers, stats line not updated")
    elif updated != readme:
        with open("README.md", "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)
        print("Updated README.md stats line")

size = os.path.getsize("site/data.json") / 1e6
print(f"Exported {len(jobs)} jobs from {sum(1 for v in counts.values() if v)} sources "
      f"-> site/data.json ({size:.1f} MB)")
