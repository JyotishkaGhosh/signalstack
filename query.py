import duckdb

con = duckdb.connect("signalstack.duckdb")

print("Jobs per company:")
print(con.sql("""
    SELECT company, COUNT(*) AS total_jobs
    FROM raw_jobs
    GROUP BY company
    ORDER BY total_jobs DESC
"""))

print("Engineering jobs per company:")
print(con.sql("""
    SELECT company, COUNT(*) AS engineering_jobs
    FROM raw_jobs
    WHERE title ILIKE '%engineer%'
    GROUP BY company
    ORDER BY engineering_jobs DESC
"""))

print("Companies hiring in India:")
print(con.sql("""
    SELECT company, COUNT(*) AS india_jobs
    FROM raw_jobs
    WHERE location ILIKE '%india%'
       OR location ILIKE '%bengaluru%'
       OR location ILIKE '%bangalore%'
    GROUP BY company
    ORDER BY india_jobs DESC
"""))
print("Jobs per source:")
print(con.sql("""
    SELECT source, COUNT(DISTINCT company) AS companies, COUNT(*) AS jobs
    FROM raw_jobs
    GROUP BY source
    ORDER BY jobs DESC
"""))
con.close()