import sqlite3, os, json

DB = os.path.join(os.path.dirname(__file__), "..", "changes.db")

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(changes)")
    cols = cur.fetchall()
    print("changes schema:")
    for c in cols:
        print(c)
    print()
    cur.execute("SELECT id, portal, url, diff_type, diff_detail, timestamp FROM changes WHERE portal='EPR PLASTIC' ORDER BY timestamp DESC LIMIT 10")
    rows = cur.fetchall()
    for r in rows:
        print("----")
        print("id:", r[0], "type:", r[3], "time:", r[5])
        detail = r[4]
        try:
            d = json.loads(detail)
            print("summary:", d.get("summary"))
            print("added_texts:", d.get("added_texts"))
            print("removed_texts:", d.get("removed_texts"))
        except Exception:
            print("raw detail (truncated):", str(detail)[:400])
    conn.close()

if __name__ == "__main__":
    main()

