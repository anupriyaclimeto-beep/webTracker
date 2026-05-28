import sqlite3, os, datetime

DB = os.path.join(os.path.dirname(__file__), "..", "changes.db")
portal = "EPR PLASTIC"
url = "https://eprplastic.cpcb.gov.in/#/plastic/home___Home"
html_path = r"archive\\my-portal\\eprplastic.cpcb.gov.in_#_plastic_home\\20260525_124632\\snapshot.html"
screenshot_path = r"archive\\my-portal\\eprplastic.cpcb.gov.in_#_plastic_home\\20260525_124632\\screenshot.png"
har_path = None

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    # normalize backslashes for storage (existing rows use backslashes)
    html = html_path
    ss = screenshot_path if os.path.exists(os.path.join(os.path.dirname(__file__), "..", screenshot_path)) else None
    # check for existing identical html_path
    cur.execute("SELECT id, updated_at FROM baselines WHERE html_path = ?", (html,))
    r = cur.fetchone()
    if r:
        print("A baseline with this html_path already exists: id=%s updated_at=%s" % (r[0], r[1]))
        conn.close()
        return
    updated_at = datetime.datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO baselines (portal, url, html_path, screenshot_path, har_path, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (portal, url, html, ss, har_path, updated_at)
    )
    conn.commit()
    new_id = cur.lastrowid
    print("Inserted baseline id=%s updated_at=%s html_path=%s screenshot_exists=%s" % (new_id, updated_at, html, bool(ss)))
    conn.close()

if __name__ == "__main__":
    main()

