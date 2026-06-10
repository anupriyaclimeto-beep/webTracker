import os, json
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

SUPABASE_HOST = os.getenv("SUPABASE_HOST")
SUPABASE_PORT = os.getenv("SUPABASE_PORT") or "5432"
SUPABASE_DB = os.getenv("SUPABASE_DB")
SUPABASE_USER = os.getenv("SUPABASE_USER")
SUPABASE_PWD = os.getenv("SUPABASE_PASSWORD") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

VISUAL_MIN = float(os.getenv("VISUAL_MIN_RATIO") or 0.05)
TEXT_MIN_WORDS = int(os.getenv("TEXT_MIN_WORDS") or 5)
TEXT_MIN_LINES = int(os.getenv("TEXT_MIN_LINES") or 3)
CONF_THRESHOLD = float(os.getenv("NOISE_CONF_THRESHOLD") or 0.6)

def get_conn():
    return psycopg2.connect(
        host=SUPABASE_HOST, port=SUPABASE_PORT, dbname=SUPABASE_DB,
        user=SUPABASE_USER, password=SUPABASE_PWD, sslmode="require",
        cursor_factory=RealDictCursor
    )

def is_trivial(detail):
    if not detail:
        return True
    if detail.get("is_noise"):
        return True
    conf = detail.get("confidence")
    try:
        if conf is not None and float(conf) < CONF_THRESHOLD:
            return True
    except Exception:
        pass
    dtype = detail.get("diff_type")
    if dtype == "visual" or ("changed_pixels" in detail or "change_ratio" in detail):
        try:
            pixels = int(detail.get("changed_pixels") or 0)
            ratio = float(detail.get("change_ratio") or 0.0)
        except Exception:
            pixels = 0; ratio = 0.0
        if pixels == 0 or ratio <= VISUAL_MIN:
            return True
        return False
    # html heuristics
    try:
        words = int(detail.get("words_changed") or 0)
        lines = int(detail.get("diff_lines") or 0)
    except Exception:
        words = 0; lines = 0
    meaningful = bool(detail.get("meaningful_html_change"))
    highlighted = detail.get("highlighted_lines") or []
    if words >= TEXT_MIN_WORDS or lines >= TEXT_MIN_LINES or meaningful or (highlighted and len(highlighted) > 0):
        return False
    return True

def main(portal_name="EPR PLASTIC"):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, diff_detail FROM public.changes WHERE portal=%s", (portal_name,))
    rows = cur.fetchall()
    to_hide = []
    for r in rows:
        cid = r["id"]
        detail = r["diff_detail"] or {}
        if isinstance(detail, str):
            try:
                detail = json.loads(detail or "{}")
            except Exception:
                detail = {}
        if is_trivial(detail):
            to_hide.append(cid)
    if not to_hide:
        print("No trivial/noisy changes found to hide.")
    else:
        inserted = 0
        for hid in to_hide:
            try:
                cur.execute("INSERT INTO public.hidden_changes (change_id, hidden_at) VALUES (%s, NOW()) ON CONFLICT (change_id) DO NOTHING", (hid,))
                inserted += 1
            except Exception:
                pass
        conn.commit()
        print(f"Hid {inserted} trivial/noisy change(s) from UI for portal '{portal_name}'.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()

