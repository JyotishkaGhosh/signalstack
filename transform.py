import duckdb

con = duckdb.connect("signalstack.duckdb")

# ---- 1. Clean jobs: add department, India and remote flags ----
con.execute("""
CREATE OR REPLACE TABLE jobs_clean AS
SELECT DISTINCT
    source,
    company,
    job_id,
    title,
    location,
    url,
    CAST(snapshot_date AS DATE) AS snapshot_date,
    CASE
        WHEN title ILIKE '%engineer%' OR title ILIKE '%developer%'
          OR title ILIKE '%data scien%' OR title ILIKE '%machine learning%' THEN 'Engineering'
        WHEN title ILIKE '%sales%' OR title ILIKE '%account executive%'
          OR title ILIKE '%business development%' THEN 'Sales'
        WHEN title ILIKE '%marketing%' THEN 'Marketing'
        WHEN title ILIKE '%product manager%' OR title ILIKE '%designer%' THEN 'Product & Design'
        ELSE 'Other'
    END AS department,
    COALESCE(location, '') ILIKE '%remote%' AS is_remote,
    (COALESCE(location, '') ILIKE '%india%'
      OR COALESCE(location, '') ILIKE '%bengaluru%'
      OR COALESCE(location, '') ILIKE '%bangalore%'
      OR COALESCE(location, '') ILIKE '%mumbai%'
      OR COALESCE(location, '') ILIKE '%delhi%'
      OR COALESCE(location, '') ILIKE '%gurugram%'
      OR COALESCE(location, '') ILIKE '%hyderabad%'
      OR COALESCE(location, '') ILIKE '%pune%'
      OR COALESCE(location, '') ILIKE '%chennai%') AS is_india
FROM raw_jobs
WHERE title IS NOT NULL
""")

# ---- 2. One row per company, using its most recent day of data ----
con.execute("""
CREATE OR REPLACE TABLE company_signals AS
WITH latest AS (
    SELECT company, MAX(snapshot_date) AS latest_date
    FROM jobs_clean
    GROUP BY company
),
current_jobs AS (
    SELECT j.*
    FROM jobs_clean j
    JOIN latest l
      ON j.company = l.company AND j.snapshot_date = l.latest_date
)
SELECT
    company,
    ANY_VALUE(source)                                  AS source,
    COUNT(*)                                           AS open_jobs,
    COUNT(*) FILTER (WHERE department = 'Engineering') AS engineering_jobs,
    COUNT(*) FILTER (WHERE department = 'Sales')       AS sales_jobs,
    COUNT(*) FILTER (WHERE is_india)                   AS india_jobs,
    COUNT(*) FILTER (WHERE is_remote)                  AS remote_jobs
FROM current_jobs
GROUP BY company
""")

# ---- 3. Hot score out of 100 (compared to the biggest company in each category) ----
con.execute("""
CREATE OR REPLACE TABLE company_scores AS
SELECT
    *,
    ROUND(100 * (
          0.4 * COALESCE(open_jobs        / NULLIF(MAX(open_jobs)        OVER (), 0), 0)
        + 0.4 * COALESCE(engineering_jobs / NULLIF(MAX(engineering_jobs) OVER (), 0), 0)
        + 0.2 * COALESCE(sales_jobs       / NULLIF(MAX(sales_jobs)       OVER (), 0), 0)
    ), 1) AS hot_score
FROM company_signals
""")

print("Top 10 hottest companies right now:")
print(con.sql("""
    SELECT company, source, open_jobs, engineering_jobs, sales_jobs, india_jobs, hot_score
    FROM company_scores
    ORDER BY hot_score DESC
    LIMIT 10
"""))

con.close()