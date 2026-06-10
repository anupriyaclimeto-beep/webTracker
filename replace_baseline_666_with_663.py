#!/usr/bin/env python3
"""
Replace baseline id 666's html_url and screenshot_url with values from baseline id 663.
Creates a backup file before making changes: swap_backup_666_663.json
"""
import os, sys, json
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

BASE = Path(__file__).parent
load_dotenv(dotenv_path=BASE / ".env", override=True)

SUPABASE_HOST = os.getenv("SUPABASE_HOST")
SUPABASE_PORT = os.getenv("SUPABASE_PORT") or "5432"
SUPABASE_DB = os.getenv("SUPABASE_DB")
SUPABASE_USER = os.getenv("SUPABASE_USER")
SUPABASE_PWD = os.getenv("SUPABASE_PASSWORD") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not (SUPABASE_HOST and SUPABASE_DB and SUPABASE_USER and SUPABASE_PWD):
    print("Missing Supabase credentials in .env", file=sys.stderr)
    sys.exit(2)

DSN = dict(host=SUPABASE_HOST, port=SUPABASE_PORT, dbname=SUPABASE_DB,
           user=SUPABASE_USER, password=SUPABASE_PWD, sslmode="require")

def get_conn():
    return psycopg2.connect(cursor_factory=RealDictCursor, **DSN)

def main():
    id_from = 663
    id_to = 666
    backup_path = BASE / f"swap_backup_{id_to}_from_{id_from}.json"
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT id, portal, url, html_url, screenshot_url FROM public.baselines WHERE id = %s", (id_from,))
            row_from = cur.fetchone()
            cur.execute("SELECT id, portal, url, html_url, screenshot_url FROM public.baselines WHERE id = %s", (id_to,))
            row_to = cur.fetchone()
            if not row_from:
                print(f"Source baseline id {id_from} not found. Aborting.")
                return
            if not row_to:
                print(f"Target baseline id {id_to} not found. Aborting.")
                return
            # Write backup
            backup = {"target_before": row_to, "source": row_from}
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(backup, f, indent=2, default=str)
            print(f"Backup written to {backup_path}")
            # Perform copy: target <- source
            cur.execute("UPDATE public.baselines SET html_url=%s, screenshot_url=%s WHERE id=%s",
                        (row_from["html_url"], row_from["screenshot_url"], id_to))
        conn.commit()
        print(f"✅ Baseline id {id_to} updated to use html/screenshot from id {id_from}")
        print("Now open app.py → select EPR PLASTIC → click Run → check Changes tab")
    except Exception as e:
        print("Error:", e, file=sys.stderr)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()

