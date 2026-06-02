"""Add trailing slash to CPCB NIC baseline/change URLs (one-time fix)."""
import json
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crawler_cpcb_nic import normalize_url

PORTAL = "CPCB NIC"


def main():
    db = json.load(open(os.path.join(os.path.dirname(__file__), "..", "config.json")))["storage"]["db"]
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    updated = 0
    for table in ("baselines", "changes"):
        cur.execute(f"SELECT id, url FROM {table} WHERE portal=?", (PORTAL,))
        for row_id, url in cur.fetchall():
            new_url = normalize_url(url)
            if new_url != url:
                cur.execute(f"UPDATE {table} SET url=? WHERE id=?", (new_url, row_id))
                updated += 1
    conn.commit()
    conn.close()
    print(f"Updated {updated} row(s) to trailing-slash URLs for {PORTAL}")


if __name__ == "__main__":
    main()
