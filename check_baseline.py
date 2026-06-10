# check_baseline.py
import psycopg2, os, requests
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("SUPABASE_HOST"),
    port=os.getenv("SUPABASE_PORT"),
    dbname=os.getenv("SUPABASE_DB"),
    user=os.getenv("SUPABASE_USER"),
    password=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_PASSWORD"),
    sslmode="require"
)
cur = conn.cursor()

# Check baseline
cur.execute("""
    SELECT id, html_url, updated_at 
    FROM baselines 
    WHERE portal = 'EPR PLASTIC' 
    AND url LIKE '%SOP%'
    ORDER BY updated_at DESC LIMIT 1
""")
row = cur.fetchone()
print(f"ID: {row[0]}")
print(f"HTML URL: {row[1]}")
print(f"Updated at: {row[2]}")

html = requests.get(row[1]).text
if "Extended Deadline for EPR" in html:
    print("✅ Injected change still present")
else:
    print("❌ Crawler ne overwrite kar diya — yahi problem hai")

# Check changes table
cur.execute("""
    SELECT id, url, diff_type, timestamp 
    FROM changes 
    WHERE portal = 'EPR PLASTIC'
    AND url LIKE '%SOP%'
    ORDER BY timestamp DESC LIMIT 3
""")
rows = cur.fetchall()
if rows:
    print("\n✅ Changes detected:")
    for r in rows:
        print(f"  ID={r[0]} | Type={r[2]} | Time={r[3]}")
else:
    print("\n❌ No changes saved in DB for SOP page")