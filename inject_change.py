# inject_change.py
import psycopg2, requests, os
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("SUPABASE_HOST"),
    port=os.getenv("SUPABASE_PORT"),
    dbname=os.getenv("SUPABASE_DB"),
    user=os.getenv("SUPABASE_USER"),
    password=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_PASSWORD"),
    sslmode="require"
)
cur = conn.cursor()

# SOP page baseline fetch karo
cur.execute("""
    SELECT id, url, html_url 
    FROM baselines 
    WHERE portal = 'EPR PLASTIC' 
    AND url LIKE '%SOP%'
    ORDER BY updated_at DESC 
    LIMIT 1
""")
row = cur.fetchone()
print(f"Found: ID={row[0]} URL={row[1]}")

# Cloudinary se original HTML download karo
original_html = requests.get(row[2]).text
print(f"Downloaded HTML: {len(original_html)} chars")

# Real change inject karo — naya notice add karo table mein
fake_notice = """
<tr>
  <td>1</td>
  <td>NEW CIRCULAR — Extended Deadline for EPR Registration FY 2025-26</td>
  <td>15-06-2026</td>
  <td><a href="#">Download PDF</a></td>
</tr>
"""

# Table ke andar inject karo
if "<tbody>" in original_html:
    modified_html = original_html.replace(
        "<tbody>", 
        f"<tbody>{fake_notice}", 
        1
    )
else:
    # Fallback — body ke end mein add karo
    modified_html = original_html.replace(
        "</body>", 
        f"{fake_notice}</body>"
    )

print("Change injected into HTML")

# Modified HTML Cloudinary pe upload karo
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

result = cloudinary.uploader.upload(
    modified_html.encode(),
    resource_type="raw",
    folder="webtracker",
    format="html"
)

new_html_url = result["secure_url"]
print(f"Uploaded modified HTML: {new_html_url}")

# Baseline update karo new URL se
cur.execute("""
    UPDATE baselines 
    SET html_url = %s 
    WHERE id = %s
""", (new_html_url, row[0]))

conn.commit()
print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ DONE — Baseline updated
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Change injected: New circular notice added to SOP table

Now:
1. Open app.py dashboard
2. Select EPR PLASTIC
3. Click Run
4. Check Changes tab — new circular will show as detected change
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")

cur.close()
conn.close()