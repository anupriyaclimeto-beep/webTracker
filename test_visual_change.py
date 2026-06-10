#!/usr/bin/env python3
"""
test_visual_change.py

Simulate a visual change by swapping screenshot_url values in Supabase baselines
for the EPR PLASTIC portal, run the crawler for that portal, then check whether
a visual change was detected. Restores original data afterwards.

Usage: python test_visual_change.py
"""
import os
import sys
import time
import json
import requests
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

SUPABASE_HOST = os.getenv("SUPABASE_HOST")
SUPABASE_PORT = os.getenv("SUPABASE_PORT")
SUPABASE_DB   = os.getenv("SUPABASE_DB")
SUPABASE_USER = os.getenv("SUPABASE_USER")
SUPABASE_PWD  = os.getenv("SUPABASE_PASSWORD")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_HOST or not SUPABASE_DB or not (SUPABASE_PWD or SUPABASE_SERVICE_ROLE):
    print("Missing Supabase credentials in .env. Aborting.", file=sys.stderr)
    sys.exit(2)

PASSWORD = SUPABASE_SERVICE_ROLE or SUPABASE_PWD

DSN = {
    "host": SUPABASE_HOST,
    "port": SUPABASE_PORT or 5432,
    "dbname": SUPABASE_DB,
    "user": SUPABASE_USER,
    "password": PASSWORD,
    "sslmode": "require",
}

def get_conn():
    return psycopg2.connect(
        host=DSN["host"], port=DSN["port"], dbname=DSN["dbname"],
        user=DSN["user"], password=DSN["password"], sslmode=DSN["sslmode"],
        cursor_factory=RealDictCursor
    )

def fetch_two_baselines(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, portal, url, screenshot_url FROM public.baselines "
            "WHERE portal=%s AND screenshot_url IS NOT NULL "
            "ORDER BY updated_at DESC LIMIT 20",
            ("EPR PLASTIC",)
        )
        rows = cur.fetchall()
    # pick two with different screenshot_url and different url
    for i in range(len(rows)):
        for j in range(i+1, len(rows)):
            if rows[i]["screenshot_url"] and rows[j]["screenshot_url"] and rows[i]["screenshot_url"] != rows[j]["screenshot_url"] and rows[i]["url"] != rows[j]["url"]:
                return rows[i], rows[j]
    return None, None

def download_img(url, path):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    return len(r.content)

def run_crawler():
    cmd = [sys.executable, "crawler.py", "--once", "--portal", "EPR PLASTIC"]
    print("Running crawler:", " ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    try:
        for line in proc.stdout:
            print(line, end="")
        proc.wait()
        return proc.returncode
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass

def query_visual_changes(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, portal, url, diff_detail, timestamp FROM public.changes "
            "WHERE portal=%s AND diff_type=%s ORDER BY timestamp DESC LIMIT 5",
            ("EPR PLASTIC", "visual")
        )
        return cur.fetchall()

def update_baseline_screenshot(conn, row_id, new_url):
    with conn.cursor() as cur:
        cur.execute("UPDATE public.baselines SET screenshot_url=%s WHERE id=%s", (new_url, row_id))
    conn.commit()

def main():
    report = {
        "row1_id": None, "row1_url": None, "original_screenshot_url": None,
        "swapped_to": None, "change_detected": False, "restored": False
    }
    conn = None
    try:
        conn = get_conn()
        print("Connected to Supabase.")

        r1, r2 = fetch_two_baselines(conn)
        if not r1 or not r2:
            print("Could not find two suitable baselines for EPR PLASTIC with different screenshot_url. Abort.")
            return

        print("Row 1:", r1)
        print("Row 2:", r2)
        report["row1_id"] = r1["id"]
        report["row1_url"] = r1["url"]
        report["original_screenshot_url"] = r1["screenshot_url"]
        report["swapped_to"] = r2["screenshot_url"]

        # Download images
        before_path = "before.png"
        after_path = "after.png"
        print("Downloading before image...")
        size_before = download_img(r1["screenshot_url"], before_path)
        print(f"Saved {before_path} ({size_before} bytes)")
        print("Downloading after image...")
        size_after = download_img(r2["screenshot_url"], after_path)
        print(f"Saved {after_path} ({size_after} bytes)")

        # Swap screenshot_url in DB (row1 <- row2.screenshot_url)
        print(f"Swapping row {r1['id']} screenshot_url -> {r2['screenshot_url']}")
        update_baseline_screenshot(conn, r1["id"], r2["screenshot_url"])
        print("Swap committed.")

        # Run crawler
        rc = run_crawler()
        print("Crawler exited with code", rc)

        # Wait a few seconds to ensure changes persisted
        time.sleep(3)

        # Query visual changes
        changes = query_visual_changes(conn)
        if changes:
            print("Recent visual changes:")
            for c in changes:
                print(c["id"], c["url"], c["timestamp"])
            report["change_detected"] = True
        else:
            print("No visual changes found.")
            report["change_detected"] = False

    except Exception as e:
        print("Error during test:", e, file=sys.stderr)
    finally:
        # Restore original screenshot_url
        try:
            if conn and report["row1_id"] and report["original_screenshot_url"]:
                update_baseline_screenshot(conn, report["row1_id"], report["original_screenshot_url"])
                print("Restored original screenshot_url for row", report["row1_id"])
                report["restored"] = True
        except Exception as e:
            print("Failed to restore original data:", e, file=sys.stderr)
        if conn:
            conn.close()

        # Print final report
        print("\n==========================================")
        print("TEST REPORT - Visual Change Detection")
        print("==========================================")
        print(f"Row 1 ID      : {report.get('row1_id')}")
        print(f"Row 1 URL     : {report.get('row1_url')}")
        print(f"Original URL  : {report.get('original_screenshot_url')}")
        print(f"Swapped To    : {report.get('swapped_to')}")
        print(f"Change Detected: {'YES' if report.get('change_detected') else 'NO'}")
        print(f"Data Restored  : {'YES' if report.get('restored') else 'NO'}")
        print("==========================================")

if __name__ == '__main__':
    main()

