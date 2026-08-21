"""Seed crawl_log rows for all configured portals so the dashboard shows tracked portals."""
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv()

from storage import USE_SUPABASE, get_conn, init_db


def main():
    init_db()

    with open("config.json", encoding="utf-8") as f:
        portals = json.load(f).get("portals", [])

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for portal in portals:
                name = portal["name"]
                if USE_SUPABASE:
                    cur.execute(
                        "SELECT 1 FROM public.crawl_log WHERE portal = %s LIMIT 1",
                        (name,),
                    )
                else:
                    cur.execute(
                        "SELECT 1 FROM crawl_log WHERE portal = ? LIMIT 1",
                        (name,),
                    )
                if cur.fetchone():
                    continue

                now = datetime.now(timezone.utc)
                if USE_SUPABASE:
                    cur.execute(
                        """
                        INSERT INTO public.crawl_log
                            (portal, started_at, finished_at, status, pages_visited)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (name, now, now, "pending", 0),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO crawl_log
                            (portal, started_at, finished_at, status, pages_visited)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (name, now.isoformat(), now.isoformat(), "pending", 0),
                    )
                print(f"Seeded crawl_log for {name}")
        conn.commit()
    finally:
        conn.close()

    print(f"Done. Seeded up to {len(portals)} portals.")


if __name__ == "__main__":
    main()
