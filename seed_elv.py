import sqlite3, json

db = json.load(open('config.json'))['storage']['db']

conn = sqlite3.connect(db)

conn.execute("""
INSERT INTO crawl_log
(portal, started_at, finished_at, pages_visited, status)
VALUES ('EPR ELV', datetime('now'), datetime('now'), 0, 'pending')
""")

conn.commit()
conn.close()

print("EPR ELV added")