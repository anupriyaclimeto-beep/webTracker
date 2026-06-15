import os
import json
import requests
from io import BytesIO
from PIL import Image, ImageChops, ImageFilter
from dotenv import load_dotenv

load_dotenv()
from storage import get_conn, upload_to_cloudinary, USE_SUPABASE

def generate_diff_image_from_urls(baseline_url, current_url):
    print(f"Downloading baseline: {baseline_url}")
    b_resp = requests.get(baseline_url)
    print(f"Downloading current: {current_url}")
    c_resp = requests.get(current_url)
    
    if b_resp.status_code != 200 or c_resp.status_code != 200:
        return None
        
    baseline_img = Image.open(BytesIO(b_resp.content)).convert("RGB")
    current_img  = Image.open(BytesIO(c_resp.content)).convert("RGB")

    if baseline_img.size != current_img.size:
        current_img = current_img.resize(baseline_img.size, Image.LANCZOS)

    w, h = baseline_img.size
    diff_img    = ImageChops.difference(baseline_img, current_img)
    diff_arr    = diff_img.load()
    mask        = Image.new("L", (w, h), 0)

    for y in range(h):
        for x in range(w):
            r, g, b = diff_arr[x, y]
            if r > 15 or g > 15 or b > 15:
                mask.putpixel((x, y), 255)

    mask = mask.filter(ImageFilter.MaxFilter(11))
    
    diff_layer = Image.new("RGBA", (w, h), (255, 0, 100, 0))
    for y in range(h):
        for x in range(w):
            if mask.getpixel((x, y)) > 0:
                diff_layer.putpixel((x, y), (255, 0, 100, 120))

    highlighted = current_img.copy().convert("RGBA")
    highlighted.alpha_composite(diff_layer)
    
    out = BytesIO()
    highlighted.convert("RGB").save(out, format="PNG")
    return out.getvalue()

def update_old_changes():
    conn = get_conn()
    if not USE_SUPABASE:
        return
        
    with conn.cursor() as cur:
        # Find recent HTML changes without diff_image_url
        cur.execute("""
            SELECT id, portal, url, screenshot_url, diff_detail
            FROM public.changes
            WHERE diff_type = 'html'
            ORDER BY id DESC LIMIT 10
        """)
        rows = cur.fetchall()
        
        for row in rows:
            change_id = row['id']
            portal = row['portal']
            url = row['url']
            current_url = row['screenshot_url']
            diff_detail_json = row['diff_detail']
            try:
                if isinstance(diff_detail_json, dict):
                    diff_detail = diff_detail_json
                elif isinstance(diff_detail_json, str) and diff_detail_json:
                    diff_detail = json.loads(diff_detail_json)
                else:
                    continue
            except json.JSONDecodeError:
                print(f"Failed to parse json for change {change_id}")
                continue
            
            if "diff_image_url" in diff_detail:
                continue
                
            print(f"Processing change {change_id} for {portal}...")
            
            # Need to find the baseline screenshot for this portal BEFORE this change
            cur.execute("""
                SELECT screenshot_url FROM public.changes
                WHERE portal = %s AND url = %s AND id < %s
                ORDER BY id DESC LIMIT 1
            """, (portal, url, change_id))
            prev_row = cur.fetchone()
            
            baseline_url = prev_row['screenshot_url'] if prev_row else None
            if not baseline_url:
                # Get baseline from baselines table
                cur.execute("""
                    SELECT screenshot_url FROM public.baselines
                    WHERE portal = %s AND url = %s
                """, (portal, url))
                b_row = cur.fetchone()
                baseline_url = b_row['screenshot_url'] if b_row else None
                
            if not baseline_url or not current_url:
                print("Missing URLs")
                continue
                
            diff_bytes = generate_diff_image_from_urls(baseline_url, current_url)
            if not diff_bytes:
                print("Failed to generate diff image")
                continue
                
            path = f"archive/temp_diff_{change_id}.png"
            os.makedirs("archive", exist_ok=True)
            with open(path, "wb") as f:
                f.write(diff_bytes)
                
            uploaded_url = upload_to_cloudinary(path, resource_type="image")
            if uploaded_url:
                diff_detail["diff_image_url"] = uploaded_url
                cur.execute("""
                    UPDATE public.changes
                    SET diff_detail = %s
                    WHERE id = %s
                """, (json.dumps(diff_detail), change_id))
                conn.commit()
                print(f"Updated change {change_id} with diff_image_url: {uploaded_url}")

if __name__ == "__main__":
    update_old_changes()
