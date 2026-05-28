import sqlite3, json

with open("config.json") as f:
    db = json.load(f)["storage"]["db"]

conn = sqlite3.connect(db)
for table in ("crawl_log", "changes", "baselines"):
    cur = conn.execute(f"DELETE FROM {table} WHERE portal='my-portal'")
    print(f"  {table}: {cur.rowcount} row(s) deleted")
conn.commit()
conn.close()
print("Done — my-portal removed. Refresh the dashboard.")