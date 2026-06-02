import storage
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    if not storage.USE_SUPABASE:
        print("Not using supabase")
        return
        
    conn = storage.get_conn()
    with conn.cursor() as cur:
        # Add columns
        cur.execute("""
            ALTER TABLE public.baselines 
            ADD COLUMN IF NOT EXISTS screenshot_url TEXT,
            ADD COLUMN IF NOT EXISTS html_url TEXT
        """)
        
    conn.commit()
    conn.close()
    print("Successfully added url columns to baselines table.")

if __name__ == "__main__":
    main()
