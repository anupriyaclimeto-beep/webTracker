import sqlite3
import json

conn = sqlite3.connect('webtracker.db')
cur = conn.cursor()
cur.execute("SELECT diff_detail FROM changes WHERE portal='EPR BATTERY' AND diff_type='html' ORDER BY id DESC LIMIT 1")
row = cur.fetchone()
if row:
    data = json.loads(row[0])
    print(json.dumps(data, indent=2))
else:
    print("No rows found")
