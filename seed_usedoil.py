import sqlite3

conn = sqlite3.connect("changes.db")
conn.execute("""
    INSERT OR IGNORE INTO crawl_log
        (portal, started_at, finished_at, pages_visited, status)
    VALUES
        ('EPR USEDOIL', datetime('now'), datetime('now'), 0, 'done')
""")
conn.commit()
conn.close()
print("Done — EPR USEDOIL seeded into crawl_log")