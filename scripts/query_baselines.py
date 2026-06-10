from dotenv import load_dotenv
import os, psycopg2, json

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("SUPABASE_HOST"),
    port=os.getenv("SUPABASE_PORT"),
    dbname=os.getenv("SUPABASE_DB"),
    user=os.getenv("SUPABASE_USER"),
    password=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_PASSWORD"),
    sslmode="require",
)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM public.baselines")
cnt = cur.fetchone()[0]
print(f"Baselines count: {cnt}")
if cnt > 0:
    cur.execute("SELECT id, portal, url, screenshot_url, html_url, updated_at FROM public.baselines ORDER BY updated_at DESC LIMIT 10")
    rows = cur.fetchall()
    for r in rows:
        print(r)
else:
    print("No baselines found in public.baselines")
cur.close()
conn.close()

