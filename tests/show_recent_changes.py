import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("SUPABASE_HOST"),
    port=os.getenv("SUPABASE_PORT"),
    dbname=os.getenv("SUPABASE_DB"),
    user=os.getenv("SUPABASE_USER"),
    password=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_PASSWORD"),
    sslmode="require",
    cursor_factory=RealDictCursor,
)
cur = conn.cursor()
cur.execute(
    "SELECT id, portal, url, diff_type, screenshot_url, html_url, timestamp "
    "FROM public.changes WHERE portal=%s ORDER BY timestamp DESC LIMIT 6",
    ("EPR PLASTIC",),
)
rows = cur.fetchall()
if not rows:
    print("No recent changes found for EPR PLASTIC.")
else:
    for r in rows:
        print("ID:", r["id"])
        print(" URL:", r["url"])
        print(" Type:", r["diff_type"])
        print(" Screenshot:", r.get("screenshot_url"))
        print(" HTML:", r.get("html_url"))
        print(" Timestamp:", r.get("timestamp"))
        print("-" * 60)
cur.close()
conn.close()

