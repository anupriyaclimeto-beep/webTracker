#!/usr/bin/env python3
"""
Query recent crawl_log and changes for EPR PLASTIC and print diff_detail.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import json

BASE = Path(__file__).parent
load_dotenv(dotenv_path=BASE / ".env", override=True)

SUPABASE_HOST = os.getenv("SUPABASE_HOST")
SUPABASE_PORT = os.getenv("SUPABASE_PORT") or "5432"
SUPABASE_DB = os.getenv("SUPABASE_DB")
SUPABASE_USER = os.getenv("SUPABASE_USER")
SUPABASE_PWD = os.getenv("SUPABASE_PASSWORD") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not (SUPABASE_HOST and SUPABASE_DB and SUPABASE_USER and SUPABASE_PWD):
    print("Missing Supabase credentials in .env")
    raise SystemExit(2)

conn = psycopg2.connect(host=SUPABASE_HOST, port=SUPABASE_PORT, dbname=SUPABASE_DB,
                        user=SUPABASE_USER, password=SUPABASE_PWD, sslmode="require",
                        cursor_factory=RealDictCursor)

try:
    with conn.cursor() as cur:
        print("Latest crawl_log entries for EPR PLASTIC:")
        cur.execute("SELECT id, started_at, finished_at, pages_visited, status FROM public.crawl_log WHERE portal=%s ORDER BY started_at DESC LIMIT 5", ("EPR PLASTIC",))
        rows = cur.fetchall()
        for r in rows:
            print(r)
        print("\nRecent visual/html changes (last 60 minutes):")
        cur.execute("""
            SELECT id, portal, url, diff_type, timestamp, diff_detail
            FROM public.changes
            WHERE portal=%s AND timestamp >= NOW() - INTERVAL '60 minutes'
            ORDER BY timestamp DESC LIMIT 50
        """, ("EPR PLASTIC",))
        chs = cur.fetchall()
        if not chs:
            print("No recent changes found.")
        else:
            for c in chs:
                print("ID:", c["id"], "TYPE:", c["diff_type"], "URL:", c["url"], "TS:", c["timestamp"])
                try:
                    dd = c["diff_detail"] if isinstance(c["diff_detail"], dict) else json.loads(c["diff_detail"] or "{}")
                    print("  confidence:", dd.get("confidence"), "is_noise:", dd.get("is_noise"))
                    print("  changed_pixels:", dd.get("changed_pixels"), "change_ratio:", dd.get("change_ratio"))
                    print("  words_changed:", dd.get("words_changed"), "lines_changed:", dd.get("lines_changed"), "meaningful:", dd.get("meaningful_html_change"))
                except Exception as e:
                    print("  Could not parse diff_detail:", e)
                print("-" * 60)
finally:
    conn.close()

