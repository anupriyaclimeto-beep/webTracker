#!/usr/bin/env python3
"""
restore_baseline.py

Restore original baseline html_url and screenshot_url from swap_backup.json.

Usage:
  python restore_baseline.py
"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

BASE = Path(__file__).parent
BACKUP_PATH = BASE / "swap_backup.json"
load_dotenv(dotenv_path=BASE / ".env", override=True)

SUPABASE_HOST = os.getenv("SUPABASE_HOST")
SUPABASE_PORT = os.getenv("SUPABASE_PORT") or "5432"
SUPABASE_DB = os.getenv("SUPABASE_DB")
SUPABASE_USER = os.getenv("SUPABASE_USER")
SUPABASE_PWD = os.getenv("SUPABASE_PASSWORD") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

def get_conn():
    return psycopg2.connect(
        host=SUPABASE_HOST, port=SUPABASE_PORT, dbname=SUPABASE_DB,
        user=SUPABASE_USER, password=SUPABASE_PWD, sslmode="require",
        cursor_factory=RealDictCursor
    )

def main():
    if not BACKUP_PATH.exists():
        print(f"No backup file found at {BACKUP_PATH}. Nothing to restore.")
        return

    try:
        with open(BACKUP_PATH, "r", encoding="utf-8") as f:
            backup = json.load(f)
    except Exception as e:
        print("Failed to read backup file:", e, file=sys.stderr)
        return

    r1 = backup.get("r1")
    r2 = backup.get("r2")
    if not r1 or not r2:
        print("Backup file missing expected data (r1/r2). Aborting.", file=sys.stderr)
        return

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.baselines SET html_url=%s, screenshot_url=%s WHERE id=%s",
                (r1["html_url"], r1["screenshot_url"], r1["id"])
            )
            cur.execute(
                "UPDATE public.baselines SET html_url=%s, screenshot_url=%s WHERE id=%s",
                (r2["html_url"], r2["screenshot_url"], r2["id"])
            )
        conn.commit()
        # remove backup file
        try:
            BACKUP_PATH.unlink()
            print(f"✅ Restored originals and removed backup {BACKUP_PATH}")
        except Exception:
            print("✅ Restored originals (but failed to delete backup file).")

    except Exception as e:
        print("Error during restore:", e, file=sys.stderr)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()

