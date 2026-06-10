#!/usr/bin/env python3
"""
unhide_change.py

Usage: python scripts/unhide_change.py <change_id>

Removes a change id from public.hidden_changes (UI-only) and updates the
diff_detail JSON to mark is_noise=false and set a higher confidence so the
change will be visible in the Streamlit UI.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

BASE = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=BASE / ".env", override=True)

SUPABASE_HOST = os.getenv("SUPABASE_HOST")
SUPABASE_PORT = os.getenv("SUPABASE_PORT") or "5432"
SUPABASE_DB   = os.getenv("SUPABASE_DB")
SUPABASE_USER = os.getenv("SUPABASE_USER")
SUPABASE_PWD  = os.getenv("SUPABASE_PASSWORD") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not (SUPABASE_HOST and SUPABASE_DB and SUPABASE_USER and SUPABASE_PWD):
    print("Missing Supabase credentials in .env. Aborting.", file=sys.stderr)
    sys.exit(2)

CHANGE_ID = None
if len(sys.argv) > 1:
    try:
        CHANGE_ID = int(sys.argv[1])
    except Exception:
        print("Invalid change id", sys.argv[1], file=sys.stderr)
        sys.exit(2)
else:
    print("Usage: python scripts/unhide_change.py <change_id>", file=sys.stderr)
    sys.exit(2)

DSN = {
    "host": SUPABASE_HOST,
    "port": SUPABASE_PORT,
    "dbname": SUPABASE_DB,
    "user": SUPABASE_USER,
    "password": SUPABASE_PWD,
}

def get_conn():
    return psycopg2.connect(
        host=DSN["host"], port=DSN["port"], dbname=DSN["dbname"],
        user=DSN["user"], password=DSN["password"], sslmode="require",
        cursor_factory=RealDictCursor
    )

def main():
    hid = False
    updated = False
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            # Delete from hidden_changes if present
            cur.execute("DELETE FROM public.hidden_changes WHERE change_id = %s RETURNING change_id", (CHANGE_ID,))
            res = cur.fetchone()
            if res:
                hid = True
            # Update diff_detail JSONB: set is_noise=false and boost confidence
            cur.execute("""
                UPDATE public.changes
                SET diff_detail = jsonb_set(
                    COALESCE(diff_detail, '{}'::jsonb),
                    '{is_noise}', 'false'::jsonb,
                    true
                )::jsonb
                WHERE id = %s
                RETURNING id
            """, (CHANGE_ID,))
            if cur.fetchone():
                # Also set confidence
                cur.execute("""
                    UPDATE public.changes
                    SET diff_detail = jsonb_set(diff_detail, '{confidence}', to_jsonb(0.9::numeric), true)
                    WHERE id = %s
                """, (CHANGE_ID,))
                updated = True
        conn.commit()
        conn.close()
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        sys.exit(2)

    print(f"Hidden row removed: {'yes' if hid else 'no'}")
    print(f"diff_detail updated: {'yes' if updated else 'no'}")

if __name__ == "__main__":
    main()

