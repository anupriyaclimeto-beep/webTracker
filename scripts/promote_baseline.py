import sqlite3, os
from datetime import datetime

DB = os.path.join(os.path.dirname(__file__), "..", "changes.db")

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    # baseline id inserted earlier for manual snapshot
    bid = 131
    # set updated_at to just after the latest baseline 130 (2026-05-27T10:21:27)
    # so it becomes the 'previous' snapshot when UI selects the two most recent baselines.
    new_ts = "2026-05-27T10:22:00.000000"
    cur.execute("UPDATE baselines SET updated_at=? WHERE id=?", (new_ts, bid))
    conn.commit()
    print(f"Updated baseline id={bid} updated_at={new_ts}")
    conn.close()

if __name__ == "__main__":
    main()

