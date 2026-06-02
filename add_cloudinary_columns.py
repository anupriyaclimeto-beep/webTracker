import storage
import sys

def fix_schema():
    conn = storage.get_conn()
    cur = conn.cursor()
    statements = [
        "ALTER TABLE public.changes ADD COLUMN IF NOT EXISTS screenshot_url TEXT",
        "ALTER TABLE public.changes ADD COLUMN IF NOT EXISTS html_url TEXT",
    ]
    for stmt in statements:
        try:
            cur.execute(stmt)
            print(f"OK: {stmt}")
        except Exception as e:
            print(f"Error: {stmt} -> {e}", file=sys.stderr)
    conn.commit()

    # Verify columns
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='changes' AND table_schema='public' ORDER BY ordinal_position"
    )
    cols = [r[0] for r in cur.fetchall()]
    print(f"\nAll columns in public.changes: {cols}")
    cur.close()
    conn.close()

if __name__ == "__main__":
    fix_schema()
