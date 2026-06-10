# test_fake_change.py
import sqlite3

conn = sqlite3.connect("changes.db")

# Swap html_url and screenshot_url between id 449 and 453
conn.execute("""
    UPDATE baselines
    SET 
        html_url = 'https://res.cloudinary.com/day3dgjd9/raw/upload/v1780996878/webtracker/pzv3cbs57tph2qrlxx1a.html',
        screenshot_url = 'https://res.cloudinary.com/day3dgjd9/image/upload/v1780996877/webtracker/jdvxwqvlg5tqqxqxzhbj.png'
    WHERE id = 449
""")

conn.execute("""
    UPDATE baselines
    SET 
        html_url = 'https://res.cloudinary.com/day3dgjd9/raw/upload/v1780996813/webtracker/z7rybeglxlljd0rtljfc.html',
        screenshot_url = 'https://res.cloudinary.com/day3dgjd9/image/upload/v1780996811/webtracker/zhalcrmsfqouuj6jlec8.png'
    WHERE id = 453
""")

conn.commit()
conn.close()
print("Swapped — now run crawler")