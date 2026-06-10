# show_diff.py
import psycopg2, os, json
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
cur.execute("SELECT id, diff_detail FROM changes WHERE id = 1000")
row = cur.fetchone()
detail = json.loads(row[1])
print(json.dumps(detail, indent=2))