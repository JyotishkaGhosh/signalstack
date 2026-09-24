import csv
import duckdb
import pandas as pd

from locations import parse_location

con = duckdb.connect("signalstack.duckdb")

# Direct company boards come first when the same job is listed in several places,
# so the Apply link goes straight to the employer
SOURCE_RANK = {"greenhouse": 1, "lever": 1, "ashby": 1, "workable": 1, "smartrecruiters": 1, "recruitee": 1,
               "adzuna": 2, "themuse": 2, "remotive": 2, "arbeitnow": 2}
BOARDS = ("remotive", "arbeitnow", "themuse", "adzuna")

# ---- 1. Clean locations: city, state, country and remote / hybrid / on-site ----
places = con.sql("""
    SELECT DISTINCT location, city, region, country, remote_hint FROM raw_jobs
""").df()
parsed = [parse_location(*[None if pd.isna(v) else v for v in r])
          for r in places.itertuples(index=False, name=None)]
places[["clean_city", "clean_state", "clean_country", "workplace"]] = pd.DataFrame(parsed, index=places.index)
con.execute("CREATE OR REPLACE TABLE location_map AS SELECT * FROM places")

# ---- 2. Role type and experience level from the title (plus hints from the source) ----
con.execute(r"""
CREATE OR REPLACE MACRO role_of(t) AS CASE
    WHEN t IS NULL THEN NULL
    WHEN regexp_matches(t, '\b(designer|design|ux|ui/ux|user research)') THEN 'Design'
    WHEN regexp_matches(t, '\b(product manager|product owner|product lead|head of product|director of product|vp,? product|product management|product director|product strategy)\b') THEN 'Product'
    WHEN regexp_matches(t, '\b(data|machine learning|ml|ai|analytics|analyst|scientist|research engineer|llm|nlp|computer vision|research)\b') THEN 'Data & AI'
    WHEN regexp_matches(t, '\b(engineer|engineering|developer|development engineer|sde|swe|devops|sre|programmer|software|frontend|front-end|backend|back-end|full[- ]?stack|ios|android|mobile|qa|tester|test automation|firmware|architect|security|infrastructure|it support|technical support|sysadmin|system administrator)') THEN 'Engineering'
    WHEN regexp_matches(t, '\b(sales|account executive|account exec|account director|business development|bdr|sdr|account manager|partnerships?|enablement|pre-?sales|solutions consultant)\b') THEN 'Sales'
    WHEN regexp_matches(t, '\b(marketing|growth|seo|content|brand|communications|social media|copywriter|public relations|pr manager|events?)\b') THEN 'Marketing'
    WHEN regexp_matches(t, '\b(customer|support|success|service desk|implementation|onboarding|client services)\b') THEN 'Customer Support'
    WHEN regexp_matches(t, '\b(recruit|recruiter|recruiting|talent|people|hr|human resources|hrbp|payroll)') THEN 'People & HR'
    WHEN regexp_matches(t, '\b(finance|financial|accountant|accounting|accounts|tax|audit|controller|fp&a|treasury|billing|credit)\b') THEN 'Finance'
    WHEN regexp_matches(t, '\b(legal|counsel|lawyer|attorney|paralegal|compliance|privacy|regulatory)\b') THEN 'Legal'
    WHEN regexp_matches(t, '\b(operations|ops|supply chain|logistics|procurement|program manager|project manager|programme|warehouse|fulfil+ment|administrative|office manager|executive assistant|strategy)\b') THEN 'Operations'
    ELSE 'Other'
END
""")

con.execute(r"""
CREATE OR REPLACE MACRO level_of(t, hint, years) AS CASE
    WHEN regexp_matches(t, '\b(intern|interns|internship|trainee|apprentice|apprenticeship|co-op|working student|werkstudent|praktikum|praktikant|summer analyst)\b') THEN 'Intern'
    WHEN regexp_matches(t, '\b(director|vp|svp|evp|vice president|head of|chief|cto|ceo|cfo|coo|cmo|cpo|president)\b') THEN 'Director / Executive'
    WHEN regexp_matches(t, '\b(principal|staff|distinguished|fellow|architect)\b') THEN 'Lead / Staff'
    WHEN regexp_matches(t, '\b(engineering manager|manager,? engineering|general manager|country manager|people manager|team manager|manager of)\b') THEN 'Manager'
    WHEN regexp_matches(t, '\b(senior|sr|snr|iii|iv)\b') THEN 'Senior'
    WHEN regexp_matches(t, '\b(lead|tech lead|team lead)\b') THEN 'Lead / Staff'
    WHEN regexp_matches(t, '\b(junior|jr|entry[- ]level|new grad|new graduate|graduate|grad|fresher|freshers|early career|campus|university|associate|0-[12] years?)\b')
      OR regexp_matches(t, '\b(engineer|developer|analyst|scientist|sde|swe)\s*(i|1)\b') THEN 'Entry level'
    WHEN regexp_matches(t, '\b(mid[- ]?level|intermediate)\b')
      OR regexp_matches(t, '\b(engineer|developer|analyst|scientist|sde|swe)\s*(ii|2)\b') THEN 'Mid level'
    WHEN regexp_matches(hint, '(intern|student)') THEN 'Intern'
    WHEN regexp_matches(hint, '(entry|graduate|junior|associate)') THEN 'Entry level'
    WHEN regexp_matches(hint, '(director|executive)') THEN 'Director / Executive'
    WHEN regexp_matches(hint, '(manag)') THEN 'Manager'
    WHEN regexp_matches(hint, '(senior)') AND NOT regexp_matches(hint, 'mid') THEN 'Senior'
    WHEN regexp_matches(hint, '(mid|experienced)') THEN 'Mid level'
    WHEN years IS NOT NULL AND years <= 2 THEN 'Entry level'
    WHEN years IS NOT NULL AND years <= 4 THEN 'Mid level'
    WHEN years IS NOT NULL THEN 'Senior'
    ELSE 'Not specified'
END
""")

con.execute("""
CREATE OR REPLACE TABLE jobs_clean AS
SELECT DISTINCT
    r.source,
    r.feed,
    r.job_id,
    substr(md5(r.source || '|' || r.feed || '|' || r.job_id), 1, 12)  AS uid,
    trim(r.title)                                                     AS title,
    trim(r.company)                                                   AS company,
    r.location,
    r.url,
    CAST(r.snapshot_date AS DATE)                                     AS snapshot_date,
    TRY_CAST(r.job_date AS DATE)                                      AS job_date,
    COALESCE(NULLIF(role_of(lower(r.title)), 'Other'),
             role_of(lower(r.department_hint)), 'Other')              AS role_type,
    level_of(lower(r.title), COALESCE(lower(r.level_hint), ''), r.min_years) AS level,
    m.clean_city                                                      AS city,
    m.clean_state                                                     AS state,
    m.clean_country                                                   AS country,
    m.workplace
FROM raw_jobs r
LEFT JOIN location_map m
  ON  m.location    IS NOT DISTINCT FROM r.location
  AND m.city        IS NOT DISTINCT FROM r.city
  AND m.region      IS NOT DISTINCT FROM r.region
  AND m.country     IS NOT DISTINCT FROM r.country
  AND m.remote_hint IS NOT DISTINCT FROM r.remote_hint
WHERE r.title IS NOT NULL AND r.job_id IS NOT NULL
""")

# Fresher = intern, new grad, entry level or 0-2 years. Everyone else is Experienced.
con.execute("""
CREATE OR REPLACE TABLE jobs_clean AS
SELECT *, CASE WHEN level IN ('Intern', 'Entry level') THEN 'Fresher' ELSE 'Experienced' END AS experience_group
FROM jobs_clean
""")

# ---- 3. Current jobs: each board's latest day of data, with the first day we saw each job ----
with open("companies.csv", encoding="utf-8") as f:
    configured = pd.DataFrame([{"source": r["ats"].strip().lower(), "feed": r["company"].strip()}
                               for r in csv.DictReader(f) if r["company"].strip()])
configured = pd.concat([configured, pd.DataFrame([{"source": b, "feed": "all"} for b in BOARDS])])
con.execute("CREATE OR REPLACE TABLE configured_feeds AS SELECT * FROM configured")

con.execute("""
CREATE OR REPLACE TABLE jobs_current AS
WITH feed_dates AS (
    SELECT source, feed, MIN(snapshot_date) AS feed_first_date, MAX(snapshot_date) AS feed_latest_date
    FROM jobs_clean
    GROUP BY source, feed
),
first_seen AS (
    SELECT source, feed, job_id, MIN(snapshot_date) AS first_seen
    FROM jobs_clean
    GROUP BY source, feed, job_id
)
SELECT
    j.*,
    s.first_seen,
    -- Posting date from the source when it has one, otherwise the day we first saw the job
    COALESCE(LEAST(j.job_date, j.snapshot_date), s.first_seen) AS posted_date,
    -- New = first seen in this run, on a board we were already following before today
    (s.first_seen = f.feed_latest_date AND s.first_seen > f.feed_first_date) AS is_new
FROM jobs_clean j
JOIN feed_dates f USING (source, feed)
JOIN first_seen s USING (source, feed, job_id)
JOIN configured_feeds c USING (source, feed)
WHERE j.snapshot_date = f.feed_latest_date
  -- A board that failed for a few days keeps its last jobs; after that they are dropped
  AND f.feed_latest_date >= (SELECT MAX(snapshot_date) FROM jobs_clean) - INTERVAL 3 DAY
""")

# ---- 4. Remove the same job listed on more than one site ----
# Same company, same place, same level and a near-identical title counts as one job
rank_sql = " ".join(f"WHEN '{s}' THEN {n}" for s, n in SOURCE_RANK.items())
con.execute(fr"""
CREATE OR REPLACE TABLE jobs_listed AS
WITH keyed AS (
    SELECT *,
        regexp_replace(lower(regexp_replace(company,
            '(?i)[,.]?\s*\b(inc|llc|ltd|limited|gmbh|pvt|private|corp|corporation|plc|ag|bv|b\.v|s\.a|technologies|india)\b\.?', '', 'g')),
            '[^a-z0-9]', '', 'g')                                                AS company_key,
        trim(regexp_replace(regexp_replace(lower(title),
            '\(.*?\)|\b(m/w/d|m/f/d|f/m/d|w/m/d|all genders|remote|hybrid)\b', ' ', 'g'),
            '[^a-z0-9]+', ' ', 'g'))                                             AS title_key,
        lower(COALESCE(city, '') || '|' || COALESCE(country, '') || '|' ||
              CASE WHEN city IS NULL THEN COALESCE(workplace, '') ELSE '' END)   AS place_key,
        CASE source {rank_sql} ELSE 3 END                                        AS source_rank
    FROM jobs_current
),
ranked AS (
    SELECT *, row_number() OVER (ORDER BY source_rank, posted_date DESC, uid) AS rn FROM keyed
)
SELECT a.* EXCLUDE (company_key, title_key, place_key, source_rank, rn)
FROM ranked a
WHERE NOT EXISTS (
    SELECT 1 FROM ranked b
    WHERE b.company_key = a.company_key
      AND b.place_key = a.place_key
      AND b.level = a.level
      AND b.source <> a.source
      AND b.rn < a.rn
      AND (b.title_key = a.title_key OR jaro_winkler_similarity(b.title_key, a.title_key) >= 0.95)
)
""")

current = con.execute("SELECT COUNT(*) FROM jobs_current").fetchone()[0]
listed = con.execute("SELECT COUNT(*) FROM jobs_listed").fetchone()[0]
print(f"{current} current jobs, {current - listed} duplicates across sites removed, {listed} listed")
print(con.sql("""
    SELECT source, COUNT(*) AS jobs,
           COUNT(*) FILTER (WHERE experience_group = 'Fresher') AS freshers,
           COUNT(*) FILTER (WHERE country IS NOT NULL) AS with_country,
           COUNT(*) FILTER (WHERE is_new) AS new_today
    FROM jobs_listed GROUP BY 1 ORDER BY 2 DESC
"""))
print(con.sql("SELECT level, COUNT(*) AS jobs FROM jobs_listed GROUP BY 1 ORDER BY 2 DESC"))

con.close()
