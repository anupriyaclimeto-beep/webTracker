import sqlite3
import json
import os

DB = os.path.join(os.path.dirname(__file__), "..", "changes.db")

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    print("Latest 10 changes:")
    for row in cur.execute("SELECT id, portal, url, diff_type, timestamp FROM changes ORDER BY timestamp DESC LIMIT 10"):
        print(row)
    print()
    print("Baselines (latest 10):")
    for row in cur.execute("SELECT id, portal, url, html_path, screenshot_path, updated_at FROM baselines ORDER BY updated_at DESC LIMIT 10"):
        print(row)
    conn.close()

    # also print latest crawl log and count of changes in that crawl
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, portal, started_at, finished_at, pages_visited, status FROM crawl_log ORDER BY started_at DESC LIMIT 1")
    row = cur.fetchone()
    if row:
        print()
        print("Latest crawl log:")
        print(row)
        started = row[2]
        finished = row[3] or __import__('datetime').datetime.now().isoformat()
        cur.execute("SELECT COUNT(*) FROM changes WHERE timestamp >= ? AND timestamp <= ?", (started, finished))
        count = cur.fetchone()[0]
        print("Changes recorded for that crawl:", count)
    conn.close()
    # show diff_detail for last 5 changes (truncated)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    print()
    print("Last 5 change details (truncated):")
    for row in cur.execute("SELECT id, diff_type, diff_detail FROM changes ORDER BY timestamp DESC LIMIT 5"):
        cid, dtype, detail = row
        try:
            snippet = detail[:1000]
        except Exception:
            snippet = str(detail)
        print("id=%s type=%s detail_snippet=%s" % (cid, dtype, snippet[:1000]))
    conn.close()

if __name__ == '__main__':
    main()

