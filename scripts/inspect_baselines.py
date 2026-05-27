import sqlite3, os, json

DB = os.path.join(os.path.dirname(__file__), "..", "changes.db")

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    # show table schema
    cur.execute("PRAGMA table_info(baselines)")
    cols = cur.fetchall()
    print("baselines schema:")
    for c in cols:
        print(c)
    print()
    # fetch recent baselines dynamically
    cur.execute("SELECT * FROM baselines ORDER BY updated_at DESC LIMIT 20")
    rows = cur.fetchall()
    if not rows:
        print("No baselines found.")
        return
    col_names = [c[1] for c in cols]
    for r in rows:
        print("="*80)
        rec = dict(zip(col_names, r))
        for k,v in rec.items():
            print(f"{k}: {v}")
        # try to find snapshot.html or screenshot files under archive path or raw_html
        # look for any field that looks like a path
        for key in ['archive_path','path','snapshot_path','raw_path','html_path','screenshot_path','screenshot']:
            if key in rec and rec[key]:
                p = os.path.join(os.path.dirname(__file__), "..", rec[key])
                print("exists?", key, os.path.exists(p), p)
    conn.close()

if __name__ == "__main__":
    main()

