# test_supabase.py
import os
import sys
from pathlib import Path

# Load .env variables (makes the secret values available as os.getenv)
from dotenv import load_dotenv

# -------------------------------------------------
# 1️⃣ Locate the .env file (same directory as this script)
script_dir = Path(__file__).parent
env_path = script_dir / ".env"
if not env_path.is_file():
    sys.exit("❌ .env file not found at: " + str(env_path))

load_dotenv(dotenv_path=env_path)   # <-- reads the file into os.environ
# -------------------------------------------------

# 2️⃣ Pull the credentials from the environment
HOST = os.getenv("SUPABASE_HOST")
PORT = os.getenv("SUPABASE_PORT")
DB   = os.getenv("SUPABASE_DB")
USER = os.getenv("SUPABASE_USER")
PWD  = os.getenv("SUPABASE_PASSWORD")

# Quick sanity check – make sure nothing is missing
missing = [k for k, v in
           {"HOST":HOST, "PORT":PORT, "DB":DB, "USER":USER, "PWD":PWD}.items()
           if not v]
if missing:
    sys.exit(f"❌ Missing environment variables: {', '.join(missing)}")

# -------------------------------------------------
# 3️⃣ Build the DSN (Data Source Name) string that psycopg2 expects
#    Note the `sslmode=require` – Supabase requires TLS.
dsn = (
    f"host={HOST} "
    f"port={PORT} "
    f"dbname={DB} "
    f"user={USER} "
    f"password={PWD} "
    f"sslmode=require"
)

# -------------------------------------------------
# 4️⃣ Connect and run a couple of test queries
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    # Open a connection (the driver uses the DSN string)
    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
except Exception as e:
    sys.exit(f"❌ Could not connect to Supabase: {e}")

# Use a context manager so the cursor and connection close cleanly
with conn:
    with conn.cursor() as cur:
        # 4a️⃣ Check PostgreSQL version (just to prove we’re connected)
        cur.execute("SELECT version();")
        version = cur.fetchone()
        print("✅ PostgreSQL version:", version["version"])

        # 4b️⃣ Count rows in the `changes` table (the table used by your app)
        cur.execute("SELECT COUNT(*) AS cnt FROM changes;")
        count = cur.fetchone()
        print(f"✅ Rows in `changes` table: {count['cnt']}")

print("🎉 All done – connection works!")