# In the terminal, run:
python -c "
import sqlite3
conn = sqlite3.connect('changes.db')
conn.execute(\"\"\"
    UPDATE baselines 
    SET html_path = 'archive/my-portal/eprplastic.cpcb.gov.in_%23_epr_pibo-declaration-procurement___PW_Procurement/20260526_151958/snapshot.html'
    WHERE portal = 'my-portal' 
    AND url LIKE '%PW_Procurement%'
\"\"\")
print('Rows updated:', conn.total_changes)
conn.commit()
conn.close()
"