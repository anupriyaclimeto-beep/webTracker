#!/usr/bin/env python3
"""
swap_baseline.py

Swap html_url and screenshot_url between two most recent baselines for EPR PLASTIC.
Saves originals to swap_backup.json before making changes.

Usage:
  python swap_baseline.py
"""
import os
import sys
import json
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

BACKUP_PATH = BASE / "swap_backup.json"

def get_conn():
    return psycopg2.connect(
        host=SUPABASE_HOST, port=SUPABASE_PORT, dbname=SUPABASE_DB,
        user=SUPABASE_USER, password=SUPABASE_PWD, sslmode="require",
        cursor_factory=RealDictCursor
    )

def main():
    if not (SUPABASE_HOST and SUPABASE_DB and SUPABASE_USER and SUPABASE_PWD):
        print("Missing Supabase credentials in .env. Aborting.", file=sys.stderr)
        sys.exit(2)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, portal, url, html_url, screenshot_url FROM public.baselines "
                "WHERE portal=%s AND html_url IS NOT NULL AND screenshot_url IS NOT NULL "
                "ORDER BY updated_at DESC LIMIT 2",
                ("EPR PLASTIC",)
            )
            rows = cur.fetchall()
            if len(rows) < 2:
                print("Could not find two suitable baseline rows for EPR PLASTIC. Aborting.")
                return
            r1, r2 = rows[0], rows[1]

            backup = {"r1": r1, "r2": r2}
            with open(BACKUP_PATH, "w", encoding="utf-8") as f:
                json.dump(backup, f, indent=2, default=str)
            print(f"Saved backup to {BACKUP_PATH}")

            # Perform swap: r1 <- r2, r2 <- r1
            cur.execute(
                "UPDATE public.baselines SET html_url=%s, screenshot_url=%s WHERE id=%s",
                (r2["html_url"], r2["screenshot_url"], r1["id"])
            )
            cur.execute(
                "UPDATE public.baselines SET html_url=%s, screenshot_url=%s WHERE id=%s",
                (r1["html_url"], r1["screenshot_url"], r2["id"])
            )
            conn.commit()
            print("✅ Baselines swapped successfully:")
            print(f" - Row {r1['id']} now points to Row {r2['id']}'s html/screenshot")
            print(f" - Row {r2['id']} now points to Row {r1['id']}'s html/screenshot")
            print("\nNext steps:")
            print("1) Open app.py → select EPR PLASTIC → click Run → check Changes tab")
            print("2) When done, run restore_baseline.py to restore originals")

    except Exception as e:
        print("Error during swap:", e, file=sys.stderr)
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()

