# debug_compare.py
import psycopg2, os, requests
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

# Baseline HTML fetch karo
cur.execute("""
    SELECT id, html_url 
    FROM baselines 
    WHERE portal = 'EPR PLASTIC' 
    AND url LIKE '%SOP%'
    ORDER BY updated_at DESC LIMIT 1
""")
row = cur.fetchone()
baseline_html = requests.get(row[1]).text

# Check injected text
print(f"Baseline size: {len(baseline_html)} chars")
print(f"Injected text present: {'Extended Deadline for EPR' in baseline_html}")

# Simple diff check
from difflib import unified_diff
import re

def strip_noise(html):
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    html = re.sub(r'\s+', ' ', html)
    return html.strip()

# Fetch fresh page
import subprocess, sys
print("\nFetching fresh page from website...")

# Manual fetch using requests to compare
try:
    fresh = requests.get(
        "https://eprplastic.cpcb.gov.in/#/plastic/home__DROPDOWN_SOP",
        timeout=10
    ).text
    print(f"Fresh page size: {len(fresh)} chars")
    
    b = strip_noise(baseline_html)
    f = strip_noise(fresh)
    
    diff = list(unified_diff(b.split(), f.split(), lineterm=''))
    print(f"Diff lines: {len(diff)}")
    if diff:
        print("First 10 diff lines:")
        for line in diff[:10]:
            print(line)
    else:
        print("❌ No diff found after stripping")
except Exception as e:
    print(f"Error: {e}")

# Check what crawler last logged
cur.execute("""
    SELECT id, portal, started_at, finished_at, pages_visited, status
    FROM crawl_log
    WHERE portal = 'EPR PLASTIC'
    ORDER BY started_at DESC LIMIT 3
""")
logs = cur.fetchall()
print("\n=== LAST CRAWL LOGS ===")
for l in logs:
    print(f"ID={l[0]} | Pages={l[4]} | Status={l[5]} | Started={l[2]}")