#!/usr/bin/env python3
"""
test_detect_change.py - Streamlit test app to swap baselines and verify visual/html detection.

Run with:
    streamlit run test_detect_change.py

It will:
 - Connect to Supabase using .env
 - Pick two baselines for EPR PLASTIC
 - Swap their html_url and screenshot_url
 - Run crawler for EPR PLASTIC
 - Query changes and display results in a mini Streamlit UI
 - Restore original baselines (auto + via button)
"""
import os
import sys
import json
import time
import tempfile
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
import streamlit as st

BASE_DIR = Path(__file__).parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

SUPABASE_HOST = os.getenv("SUPABASE_HOST")
SUPABASE_PORT = os.getenv("SUPABASE_PORT") or "5432"
SUPABASE_DB = os.getenv("SUPABASE_DB")
SUPABASE_USER = os.getenv("SUPABASE_USER")
SUPABASE_PWD = os.getenv("SUPABASE_PASSWORD") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not (SUPABASE_HOST and SUPABASE_DB and SUPABASE_USER and SUPABASE_PWD):
    raise RuntimeError("Missing Supabase credentials in .env")

DSN = dict(host=SUPABASE_HOST, port=SUPABASE_PORT, dbname=SUPABASE_DB,
           user=SUPABASE_USER, password=SUPABASE_PWD, sslmode="require")

def get_conn():
    return psycopg2.connect(cursor_factory=RealDictCursor, **DSN)

def fetch_two_baselines(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, portal, url, html_url, screenshot_url FROM public.baselines "
            "WHERE portal=%s AND html_url IS NOT NULL AND screenshot_url IS NOT NULL "
            "ORDER BY updated_at DESC LIMIT 10",
            ("EPR PLASTIC",)
        )
        rows = cur.fetchall()
    # pick two distinct rows with different urls/urls
    for i in range(len(rows)):
        for j in range(i+1, len(rows)):
            if rows[i]["screenshot_url"] != rows[j]["screenshot_url"] and rows[i]["html_url"] != rows[j]["html_url"] and rows[i]["url"] != rows[j]["url"]:
                return rows[i], rows[j]
    return None, None

def download(url, path):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    return len(r.content)

def swap_baselines(conn, r1, r2):
    with conn.cursor() as cur:
        cur.execute("UPDATE public.baselines SET html_url=%s, screenshot_url=%s WHERE id=%s",
                    (r2["html_url"], r2["screenshot_url"], r1["id"]))
        cur.execute("UPDATE public.baselines SET html_url=%s, screenshot_url=%s WHERE id=%s",
                    (r1["html_url"], r1["screenshot_url"], r2["id"]))
    conn.commit()

def restore_baselines(conn, orig1, orig2):
    with conn.cursor() as cur:
        cur.execute("UPDATE public.baselines SET html_url=%s, screenshot_url=%s WHERE id=%s",
                    (orig1["html_url"], orig1["screenshot_url"], orig1["id"]))
        cur.execute("UPDATE public.baselines SET html_url=%s, screenshot_url=%s WHERE id=%s",
                    (orig2["html_url"], orig2["screenshot_url"], orig2["id"]))
    conn.commit()

def run_crawler_live():
    cmd = [sys.executable, "crawler.py", "--once", "--portal", "EPR PLASTIC"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    return proc

def query_recent_changes(conn, minutes=10):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, portal, url, diff_type, diff_detail, timestamp, screenshot_url, html_url "
            "FROM public.changes "
            "WHERE portal=%s AND timestamp >= NOW() - INTERVAL %s MINUTE "
            "ORDER BY timestamp DESC LIMIT 20",
            ("EPR PLASTIC", minutes)
        )
        return cur.fetchall()

st.set_page_config(page_title="Test - Visual Change Detection", layout="wide")
st.markdown("<style>body{background:#080b10;color:#e2e8f0;font-family:IBM Plex Sans, sans-serif;}</style>", unsafe_allow_html=True)
st.title("🧪 Visual Change Detection Test")

conn = None
orig1 = orig2 = None
row1 = row2 = None

try:
    conn = get_conn()
    row1, row2 = fetch_two_baselines(conn)
    if not row1 or not row2:
        st.error("Could not find two suitable baselines for EPR PLASTIC with html_url and screenshot_url.")
        st.stop()

    st.subheader("Selected baselines")
    st.write("Row 1:", dict(row1))
    st.write("Row 2:", dict(row2))

    if "orig_backup" not in st.session_state:
        st.session_state.orig_backup = {"r1": dict(row1), "r2": dict(row2)}

    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶ Run test (swap → crawl → detect)"):
            # perform swap, run crawler, check changes, restore
            orig1 = dict(row1); orig2 = dict(row2)
            try:
                swap_baselines(conn, row1, row2)
                st.success("✅ Baselines swapped successfully")

                # run crawler and stream output
                proc = run_crawler_live()
                log_area = st.empty()
                for line in proc.stdout:
                    log_area.text(line.rstrip())
                proc.wait()
                st.success("✅ Crawler finished")

                time.sleep(3)
                changes = query_recent_changes(conn, minutes=10)
                detected = len(changes) > 0
                if detected:
                    st.success(f"✅ PASS — {len(changes)} change(s) detected")
                else:
                    st.error("❌ FAIL — No changes detected")

                # Show changes in UI
                for c in changes:
                    with st.expander(f"{c['diff_type'].upper()} — {c['url']} — {str(c['timestamp'])[:19]}", expanded=False):
                        try:
                            detail = c["diff_detail"] if isinstance(c["diff_detail"], dict) else json.loads(c["diff_detail"] or "{}")
                        except Exception:
                            detail = {}
                        # Show images: before = original r1 screenshot, after = current baseline screenshot for url (fetch from baselines)
                        before_img = None
                        after_img = None
                        try:
                            before_img = requests.get(orig1["screenshot_url"], timeout=20).content
                        except Exception:
                            before_img = None
                        try:
                            # fetch current baseline screenshot for this url (latest)
                            with conn.cursor() as cur:
                                cur.execute("SELECT screenshot_url FROM public.baselines WHERE url=%s ORDER BY updated_at DESC LIMIT 1", (c["url"],))
                                r = cur.fetchone()
                                after_url = r["screenshot_url"] if r else c.get("screenshot_url")
                            after_img = requests.get(after_url, timeout=20).content if after_url else None
                        except Exception:
                            after_img = None
                        cols = st.columns([1,1])
                        with cols[0]:
                            st.markdown("**Before**")
                            if before_img:
                                st.image(before_img, use_column_width=True)
                            else:
                                st.info("No before image")
                        with cols[1]:
                            st.markdown("**After**")
                            if after_img:
                                st.image(after_img, use_column_width=True)
                            else:
                                st.info("No after image")
                        st.markdown("**Diff detail:**")
                        st.json(detail)

            finally:
                try:
                    restore_baselines(conn, orig1, orig2)
                    st.success("✅ Baselines restored to original state")
                except Exception as e:
                    st.error(f"Failed to restore baselines: {e}")

    with col2:
        if st.button("↺ Restore original baselines now"):
            try:
                b = st.session_state.get("orig_backup")
                if b:
                    restore_baselines(conn, b["r1"], b["r2"])
                    st.success("✅ Restored from session backup")
                else:
                    st.info("No backup in session_state")
            except Exception as e:
                st.error(f"Restore failed: {e}")

    st.markdown("---")
    st.write("Manual checks:")
    st.write("- Use the Changes tab in main app to cross-check")
    st.write("- This test restores original data automatically after run")

except Exception as e:
    st.error(f"Fatal error: {e}")
finally:
    if conn:
        conn.close()
