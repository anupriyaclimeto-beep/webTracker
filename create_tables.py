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
        # Create crawl_log table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.crawl_log (
                id            SERIAL PRIMARY KEY,
                portal        TEXT NOT NULL,
                started_at    TEXT NOT NULL,
                finished_at   TEXT,
                pages_visited INTEGER DEFAULT 0,
                status        TEXT DEFAULT 'running'
            )
        """)
        
        # Create baselines table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.baselines (
                id              SERIAL PRIMARY KEY,
                portal          TEXT NOT NULL,
                url             TEXT NOT NULL,
                html_path       TEXT,
                screenshot_path TEXT,
                har_path        TEXT,
                updated_at      TEXT NOT NULL
            )
        """)
        
        # Create index on baselines
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_baselines_portal_url
            ON public.baselines (portal, url)
        """)
        
    conn.commit()
    conn.close()
    print("Successfully created crawl_log and baselines tables in Supabase.")

if __name__ == "__main__":
    main()
