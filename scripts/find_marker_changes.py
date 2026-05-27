import sqlite3, os, json

DB = os.path.join(os.path.dirname(__file__), "..", "changes.db")

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    patterns = ["BASELINE_TEST_BTN", "BASELINE_TEST_TEXT", "MANUAL_TEST_BTN", "MANUAL_TEST_P", "MANUAL_EDIT_MARKER"]
    found = False
    for p in patterns:
        cur.execute("SELECT id, portal, url, diff_type, diff_detail, timestamp FROM changes WHERE diff_detail LIKE ? ORDER BY timestamp DESC", ('%'+p+'%',))
        rows = cur.fetchall()
        if rows:
            found = True
            print("Matches for pattern: %s" % p)
            for r in rows:
                cid, portal, url, dtype, detail, ts = r
                print('-' * 60)
                print(f'id={cid} portal={portal} url={url} type={dtype} timestamp={ts}')
                try:
                    dd = json.loads(detail)
                    print(json.dumps(dd, indent=2)[:4000])
                except Exception:
                    print(str(detail)[:4000])
            print()
    if not found:
        print('No changes found containing markers in diff_detail.')
    conn.close()

if __name__ == "__main__":
    main()

