import os
import json
from dotenv import load_dotenv

load_dotenv()
from storage import get_conn, USE_SUPABASE

def remove_structural_noise():
    if not USE_SUPABASE:
        print("Supabase is not configured.")
        return
        
    conn = get_conn()
    rows_to_delete = []
    
    with conn.cursor() as cur:
        # Fetch all recent HTML changes
        cur.execute("""
            SELECT id, diff_detail
            FROM public.changes
            WHERE diff_type = 'html'
            ORDER BY id DESC
        """)
        rows = cur.fetchall()
        
        for row in rows:
            change_id = row['id']
            diff_detail_json = row['diff_detail']
            
            try:
                if isinstance(diff_detail_json, dict):
                    diff_detail = diff_detail_json
                elif isinstance(diff_detail_json, str) and diff_detail_json:
                    diff_detail = json.loads(diff_detail_json)
                else:
                    continue
            except json.JSONDecodeError:
                continue
                
            added_texts = diff_detail.get('added_texts', []) or []
            removed_texts = diff_detail.get('removed_texts', []) or []
            
            # Use the same logic as the new diff_engine to determine if it's structural
            added_strings = [x.get("text", "") if isinstance(x, dict) else x for x in added_texts if x]
            removed_strings = [x.get("text", "") if isinstance(x, dict) else x for x in removed_texts if x]
            
            # Since older diff_detail might have stored strings instead of dicts for added_texts
            # let's normalize everything to string
            added_strings = [str(s).strip() for s in added_strings]
            removed_strings = [str(s).strip() for s in removed_strings]
            
            added_unique = [a for a in added_strings if a and a not in removed_strings]
            removed_unique = [r for r in removed_strings if r and r not in added_strings]
            
            # If there's no unique added or removed text, this is a purely structural change
            if len(added_unique) == 0 and len(removed_unique) == 0:
                # Let's double check it didn't have words_changed > 0 or meaningful lines
                # But wait, if added_texts and removed_texts are identical, it's noise.
                rows_to_delete.append(change_id)
                print(f"Found noise change: ID {change_id}")
                
        if rows_to_delete:
            print(f"Deleting {len(rows_to_delete)} noise changes...")
            # Delete in chunks or all at once
            format_strings = ','.join(['%s'] * len(rows_to_delete))
            cur.execute(f"DELETE FROM public.changes WHERE id IN ({format_strings})", tuple(rows_to_delete))
            conn.commit()
            print("Deletion complete.")
        else:
            print("No structural noise changes found.")

if __name__ == "__main__":
    remove_structural_noise()
