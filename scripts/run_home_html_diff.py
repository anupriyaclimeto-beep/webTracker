import sqlite3
import json
import os
import sys
# ensure project root is on sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from diff_engine import html_diff

DB = os.path.join(os.path.dirname(__file__), "..", "changes.db")

def find_two_latest_home_baselines():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT html_path, updated_at FROM baselines
        WHERE url LIKE '%/plastic/home___Home'
        ORDER BY updated_at DESC LIMIT 2
    """)
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def run():
    paths = find_two_latest_home_baselines()
    if len(paths) < 2:
        print("Need two baseline snapshots for home to compare. Found:", len(paths))
        return
    baseline_path = paths[1]  # older
    current_path = paths[0]   # latest
    print("Baseline:", baseline_path)
    print("Current:", current_path)
    with open(current_path, "r", encoding="utf-8") as f:
        current_html = f.read()
    result = html_diff(baseline_path, current_html)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    run()

