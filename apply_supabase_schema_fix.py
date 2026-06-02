import storage
import sys

def apply_schema_fix():
    conn = storage.get_conn()
    cur = conn.cursor()
    # Ensure required columns exist with correct types
    statements = [
        "ALTER TABLE public.changes ADD COLUMN IF NOT EXISTS portal TEXT",
        "ALTER TABLE public.changes ADD COLUMN IF NOT EXISTS url TEXT",
        "ALTER TABLE public.changes ADD COLUMN IF NOT EXISTS diff_type TEXT",
        "ALTER TABLE public.changes ADD COLUMN IF NOT EXISTS diff_detail JSONB",
        "ALTER TABLE public.changes ADD COLUMN IF NOT EXISTS ai_summary TEXT",
        "ALTER TABLE public.changes ADD COLUMN IF NOT EXISTS timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()",
        "ALTER TABLE public.changes ADD COLUMN IF NOT EXISTS id BIGSERIAL PRIMARY KEY"
    ]
    for stmt in statements:
        try:
            cur.execute(stmt)
        except Exception as e:
            print(f"Error executing: {stmt}\n{e}", file=sys.stderr)
    conn.commit()
    cur.close()
    conn.close()
    print("Schema fix applied (or already up-to-date).")

if __name__ == "__main__":
    apply_schema_fix()
