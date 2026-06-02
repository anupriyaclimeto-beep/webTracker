#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Migrate the local SQLite 'changes.db' file into a Supabase PostgreSQL
database (the same schema used by the WebTracker app).

Requirements (install with pip):
    - python-dotenv
    - psycopg2-binary

The script reads connection details from a .env file placed in the same
directory:

    SUPABASE_HOST=aws-1-ap-northeast-1.pooler.supabase.com
    SUPABASE_PORT=6543
    SUPABASE_DB=postgres
    SUPABASE_USER=postgres.cvxhmlzesrwcrknpltpo
    SUPABASE_PASSWORD=Climeto@123
    # optional – if you have a service‑role key you can use it instead
    SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

"""

import os
import sys
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# -------------------------------------------------
# 1️⃣ Load environment variables
BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"

if not ENV_PATH.is_file():
    sys.exit(f"❌ .env file not found at {ENV_PATH}")

load_dotenv(dotenv_path=ENV_PATH)

# Pick service‑role key if it exists, otherwise fall back to the anon key
SUPABASE_URL = os.getenv("SUPABASE_HOST")
SUPABASE_PORT = os.getenv("SUPABASE_PORT")
SUPABASE_DB   = os.getenv("SUPABASE_DB")
SUPABASE_USER = os.getenv("SUPABASE_USER")
SUPABASE_PWD  = os.getenv("SUPABASE_PASSWORD")
SERVICE_ROLE  = os.getenv("SUPABASE_SERVICE_ROLE_KEY")   # optional

if not all([SUPABASE_URL, SUPABASE_PORT, SUPABASE_DB,
            SUPABASE_USER, SUPABASE_PWD]):
    sys.exit("❌ Missing one or more required Supabase env vars.")

# -------------------------------------------------
# 2️⃣ Build DSN for psycopg2 (PostgreSQL)
#    sslmode=require is mandatory for Supabase
DSN = (
    f"host={SUPABASE_URL} "
    f"port={SUPABASE_PORT} "
    f"dbname={SUPABASE_DB} "
    f"user={SUPABASE_USER} "
    f"password={SUPABASE_PWD} "
    f"sslmode=require"
)

# -------------------------------------------------
# 3️⃣ Helper: create the target table if it does not exist
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.changes (
    id            BIGSERIAL PRIMARY KEY,
    portal        TEXT NOT NULL,
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT now(),
    diff          TEXT,
    ai_summary    TEXT,
    screenshot_url TEXT
);
"""

# -------------------------------------------------
# 4️⃣ Connect to SQLite (source)
SQLITE_PATH = BASE_DIR / "changes.db"
if not SQLITE_PATH.is_file():
    sys.exit(f"❌ SQLite file not found at {SQLITE_PATH}")

sqlite_conn = sqlite3.connect(SQLITE_PATH)
sqlite_conn.row_factory = sqlite3.Row  # makes rows behave like dicts
sqlite_cur = sqlite_conn.cursor()

# Pull *all* rows from the SQLite table (adjust column names if they differ)
sqlite_cur.execute("SELECT * FROM changes;")
sqlite_rows = sqlite_cur.fetchall()
print(f"🔎 Found {len(sqlite_rows)} rows in local SQLite 'changes' table.")

# -------------------------------------------------
# 5️⃣ Connect to Supabase (PostgreSQL) and migrate
with psycopg2.connect(DSN, cursor_factory=RealDictCursor) as pg_conn:
    with pg_conn.cursor() as pg_cur:
        # 5a️⃣ Ensure the target table exists
        pg_cur.execute(CREATE_TABLE_SQL)
        pg_conn.commit()
        print("✅ Ensured `public.changes` table exists in Supabase.")

        # 5b️⃣ Upsert each row.
        #      We use the SQLite row's primary key (`id`) for conflict handling.
        upsert_sql = """
        INSERT INTO public.changes
            (id, portal, timestamp, diff, ai_summary, screenshot_url)
        VALUES
            (%(id)s, %(portal)s, %(timestamp)s, %(diff)s, %(ai_summary)s, %(screenshot_url)s)
        ON CONFLICT (id) DO UPDATE SET
            portal        = EXCLUDED.portal,
            timestamp     = EXCLUDED.timestamp,
            diff          = EXCLUDED.diff,
            ai_summary    = EXCLUDED.ai_summary,
            screenshot_url = EXCLUDED.screenshot_url;
        """

        migrated = 0
        for row in sqlite_rows:
            # Convert the SQLite Row to a plain dict and adjust column names if needed
            row_dict = dict(row)

            # SQLite stores timestamps as TEXT (ISO‑8601). psycopg2 will accept that format.
            # Ensure keys exist for every target column (use None for missing ones).
            row_dict = {
                "id":            row_dict.get("id"),
                "portal":        row_dict.get("portal"),
                "timestamp":     row_dict.get("timestamp"),
                "diff":          row_dict.get("diff"),
                "ai_summary":    row_dict.get("ai_summary"),
                "screenshot_url":row_dict.get("screenshot_url")
            }

            pg_cur.execute(upsert_sql, row_dict)
            migrated += 1

            # Optionally print progress every 100 rows
            if migrated % 100 == 0:
                print(f"   … migrated {migrated} rows ...")

        pg_conn.commit()
        print(f"🚀 Migration finished – {migrated} rows upserted into Supabase.")

# -------------------------------------------------
# 6️⃣ Clean‑up
sqlite_conn.close()
print("✅ All connections closed. You can now run the WebTracker app against Supabase.")