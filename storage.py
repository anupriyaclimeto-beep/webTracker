import sqlite3
import os
import shutil
import json
import logging
import time
import functools
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Cloudinary imports (optional – may not be available on serverless platforms)
try:
    import cloudinary
    import cloudinary.uploader
    import cloudinary.api
    HAS_CLOUDINARY = True
except ImportError:
    HAS_CLOUDINARY = False
    logger = logging.getLogger(__name__)
    logger.warning("Cloudinary not available – image uploads disabled")

# Load environment variables
BASE_DIR = Path(__file__).parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

# Supabase connection details (optional – will be used if ALL are present)
SUPABASE_HOST = os.getenv("SUPABASE_HOST")
SUPABASE_PORT = os.getenv("SUPABASE_PORT")
SUPABASE_DB   = os.getenv("SUPABASE_DB")
SUPABASE_USER = os.getenv("SUPABASE_USER")
SUPABASE_PWD  = os.getenv("SUPABASE_PASSWORD")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Cloudinary credentials (optional)
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY    = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

USE_CLOUDINARY = HAS_CLOUDINARY and all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET])

if USE_CLOUDINARY:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True,
    )
USE_LOCAL_DB = os.getenv("USE_LOCAL_DB", "").lower() in ("1", "true", "yes")

USE_SUPABASE = (not USE_LOCAL_DB) and all([
    SUPABASE_HOST,
    SUPABASE_PORT,
    SUPABASE_DB,
    SUPABASE_USER,
    SUPABASE_PWD or SUPABASE_SERVICE_ROLE,
])

if USE_SUPABASE:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    # Build DSN string for psycopg2 (SSL required by Supabase)
    _DSN = (
        f"host={SUPABASE_HOST} "
        f"port={SUPABASE_PORT} "
        f"dbname={SUPABASE_DB} "
        f"user={SUPABASE_USER} "
        f"password={SUPABASE_SERVICE_ROLE or SUPABASE_PWD} "
        f"sslmode=require "
        f"connect_timeout=10"
    )

def get_conn():
    """
    Return a fresh database connection.
    - If Supabase is configured: connect to PostgreSQL (required for cloud deployments)
    - If NOT configured on cloud (Vercel, Streamlit Cloud, etc.): raise error
    - If NOT configured locally: fall back to SQLite for development
    """
    if USE_SUPABASE:
        try:
            return psycopg2.connect(_DSN, cursor_factory=RealDictCursor)
        except Exception as e:
            logger.error("Supabase connection failed: %s", e)
            # Do NOT silently fall back to SQLite — require Supabase when configured.
            raise
    else:
        # USE_SUPABASE is False
        if IS_CLOUD:
            # On Vercel, Streamlit Cloud, or other cloud environments:
            # SQLite cannot work because the filesystem is ephemeral and read-only.
            # The user MUST configure Supabase for cloud deployments.
            raise RuntimeError(
                "SQLite is not supported on cloud deployments (Vercel, Streamlit Cloud, etc.) "
                "because the filesystem is ephemeral and not writable for database files. "
                "Please configure Supabase by setting these environment variables: "
                "SUPABASE_HOST, SUPABASE_PORT, SUPABASE_DB, SUPABASE_USER, "
                "SUPABASE_PASSWORD (or SUPABASE_SERVICE_ROLE_KEY)"
            )
        else:
            # For local non-cloud development, use SQLite
            return sqlite3.connect(DB_PATH)


def _supabase_retry(max_retries=3, delay=2):
    """Decorator that retries a function on SSL / connection errors.

    Catches psycopg2.OperationalError and psycopg2.InterfaceError (which
    include "SSL connection has been closed unexpectedly"), waits briefly,
    then retries with a fresh connection.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not USE_SUPABASE:
                return func(*args, **kwargs)
            last_err = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    err_msg = str(e).lower()
                    is_conn_err = (
                        "ssl connection" in err_msg
                        or ("connection" in err_msg and "closed" in err_msg)
                        or "server closed the connection" in err_msg
                        or "could not connect" in err_msg
                        or "connection reset" in err_msg
                    )
                    # Also catch psycopg2 specific errors if available
                    try:
                        import psycopg2
                        is_conn_err = is_conn_err or isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError))
                    except ImportError:
                        pass
                    if not is_conn_err:
                        raise  # Not a connection error, re-raise immediately
                    last_err = e
                    if attempt < max_retries:
                        wait = delay * attempt
                        logger.warning(
                            "DB connection error in %s (attempt %d/%d): %s — retrying in %ds",
                            func.__name__, attempt, max_retries, e, wait
                        )
                        time.sleep(wait)
                    else:
                        logger.error(
                            "DB connection error in %s failed after %d attempts: %s",
                            func.__name__, max_retries, e
                        )
            raise last_err
        return wrapper
    return decorator

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Detect if we are running on a cloud environment (Streamlit Cloud, Vercel, etc.)
IS_CLOUD = (
    os.getenv("STREAMLIT_SHARING_MODE") is not None or  # Streamlit Cloud
    os.path.exists("/mount/src") or  # Streamlit Cloud (alternative check)
    os.getenv("VERCEL") is not None or  # Vercel
    os.getenv("VERCEL_ENV") is not None  # Vercel
)

# Load configuration
try:
    with open("config.json") as f:
        config = json.load(f)
except FileNotFoundError:
    logger.warning("config.json not found, using minimal fallback configuration")
    config = {
        "storage": {"db": "database.db"},
        "portals": [],
        "diff": {}
    }

# SQLite‑only paths (used only when USE_SUPABASE is False)
DB_PATH     = config.get("storage", {}).get("db", "database.db")
if IS_CLOUD:
    ARCHIVE_DIR = "/tmp/webtracker_archive"
else:
    ARCHIVE_DIR = config.get("storage", {}).get("archive_dir", "archive")



# ======================================================================
# Cloudinary helper
# ======================================================================

def upload_to_cloudinary(local_path, resource_type="image"):
    """Upload a local file to Cloudinary and return the secure URL.
    Returns None if Cloudinary is not configured or upload fails.
    """
    if not USE_CLOUDINARY:
        return None
    try:
        result = cloudinary.uploader.upload(
            local_path,
            resource_type=resource_type,
            folder="webtracker",
        )
        url = result.get("secure_url")
        logger.info("Cloudinary upload OK: %s -> %s", local_path, url)
        return url
    except Exception:
        # Log full exception for debugging in CI/workflow logs
        logger.exception("Cloudinary upload FAILED for %s", local_path)
        return None


# ======================================================================
# Database initialisation
# ======================================================================

def init_db():
    """
    Initialise storage.
    • If Supabase is detected, the tables already exist (created during migration),
      so this function only logs a message.
    • If SQLite is used (local dev) we run the original schema‑creation logic.
    """
    if USE_SUPABASE:
        logger.info("Supabase detected - ensuring required tables exist in remote DB.")
        import psycopg2
        for attempt in range(2):
            try:
                conn = get_conn()
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.changes (
                            id BIGSERIAL PRIMARY KEY,
                            portal TEXT NOT NULL,
                            url TEXT NOT NULL,
                            diff_type TEXT NOT NULL,
                            diff_detail JSONB,
                            ai_summary TEXT,
                            screenshot_url TEXT,
                            html_url TEXT,
                            timestamp TIMESTAMPTZ NOT NULL
                        )
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.baselines (
                            id BIGSERIAL PRIMARY KEY,
                            portal TEXT NOT NULL,
                            url TEXT NOT NULL,
                            html_path TEXT,
                            screenshot_path TEXT,
                            har_path TEXT,
                            screenshot_url TEXT,
                            html_url TEXT,
                            updated_at TIMESTAMPTZ NOT NULL
                        )
                    """)
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_baselines_portal_url ON public.baselines (portal, url)
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.crawl_log (
                            id BIGSERIAL PRIMARY KEY,
                            portal TEXT NOT NULL,
                            started_at TIMESTAMPTZ NOT NULL,
                            finished_at TIMESTAMPTZ,
                            pages_visited INTEGER DEFAULT 0,
                            status TEXT DEFAULT 'running'
                        )
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.hidden_changes (
                            change_id BIGINT PRIMARY KEY,
                            hidden_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                    """)
                conn.commit()
                try:
                    conn.close()
                except Exception:
                    pass
                logger.info("Supabase tables ensured.")
                return
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                logger.warning(f"Connection dropped during init_db, retrying... ({e})")
                try:
                    conn.close()
                except Exception:
                    pass
                if attempt == 1:
                    logger.error("Failed to ensure Supabase tables after retry.")
                    return


    # ----- SQLite initialisation (unchanged) -----
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""\
        CREATE TABLE IF NOT EXISTS changes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            portal       TEXT NOT NULL,
            url          TEXT NOT NULL,
            diff_type    TEXT NOT NULL,
            diff_detail  TEXT,
            ai_summary   TEXT,
            screenshot_url TEXT,
            html_url     TEXT,
            timestamp    TEXT NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(changes)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if "ai_summary" not in existing_cols:
        cursor.execute("ALTER TABLE changes ADD COLUMN ai_summary TEXT")
        logger.info("Migrated changes table - added ai_summary column")
    if "screenshot_url" not in existing_cols:
        cursor.execute("ALTER TABLE changes ADD COLUMN screenshot_url TEXT")
        logger.info("Migrated changes table - added screenshot_url column")
    if "html_url" not in existing_cols:
        cursor.execute("ALTER TABLE changes ADD COLUMN html_url TEXT")
        logger.info("Migrated changes table - added html_url column")

    cursor.execute("""\
        CREATE TABLE IF NOT EXISTS baselines (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            portal          TEXT NOT NULL,
            url             TEXT NOT NULL,
            html_path       TEXT,
            screenshot_path TEXT,
            har_path        TEXT,
            screenshot_url  TEXT,
            html_url        TEXT,
            updated_at      TEXT NOT NULL
        )
    """)

    cursor.execute("""\
        CREATE INDEX IF NOT EXISTS idx_baselines_portal_url
        ON baselines (portal, url)
    """)

    cursor.execute("PRAGMA table_info(baselines)")
    existing_b_cols = {row[1] for row in cursor.fetchall()}
    if "screenshot_url" not in existing_b_cols:
        cursor.execute("ALTER TABLE baselines ADD COLUMN screenshot_url TEXT")
        logger.info("Migrated baselines table - added screenshot_url column")
    if "html_url" not in existing_b_cols:
        cursor.execute("ALTER TABLE baselines ADD COLUMN html_url TEXT")
        logger.info("Migrated baselines table - added html_url column")

    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='baselines'"
    )
    row = cursor.fetchone()
    if row and "UNIQUE" in (row[0] or "").upper():
        logger.info("Migrating baselines table — removing stale UNIQUE constraint …")
        conn.executescript("""
            ALTER TABLE baselines RENAME TO baselines_old;
            CREATE TABLE baselines (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                portal          TEXT NOT NULL,
                url             TEXT NOT NULL,
                html_path       TEXT,
                screenshot_path TEXT,
                har_path        TEXT,
                screenshot_url  TEXT,
                html_url        TEXT,
                updated_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_baselines_portal_url
                ON baselines (portal, url);
            INSERT INTO baselines (id, portal, url, html_path, screenshot_path, har_path, updated_at)
                SELECT id, portal, url, html_path, screenshot_path, har_path, updated_at FROM baselines_old;
            DROP TABLE baselines_old;
        """)
        conn.commit()
        logger.info("Baselines migration complete.")

    cursor.execute("""\
        CREATE TABLE IF NOT EXISTS crawl_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            portal        TEXT NOT NULL,
            started_at    TEXT NOT NULL,
            finished_at   TEXT,
            pages_visited INTEGER DEFAULT 0,
            status        TEXT DEFAULT 'running'
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialised at %s", DB_PATH)


# ======================================================================
# Data access functions
# ======================================================================

@_supabase_retry()
def save_diff(portal, url, diff_type, diff_detail, ai_summary=None, screenshot_url=None, html_url=None):
    """Persist a diff record, now also storing Cloudinary URLs if provided.
    Works with both SQLite and Supabase.
    """
    timestamp = datetime.now().isoformat()
    if USE_SUPABASE:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.changes
                    (portal, url, diff_type, diff_detail, ai_summary, screenshot_url, html_url, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (portal, url, diff_type, json.dumps(diff_detail), ai_summary, screenshot_url, html_url, timestamp),
            )
            conn.commit()
        conn.close()
    else:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO changes
               (portal, url, diff_type, diff_detail, ai_summary, screenshot_url, html_url, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (portal, url, diff_type, json.dumps(diff_detail), ai_summary, screenshot_url, html_url, timestamp),
        )
        conn.commit()
        conn.close()
    logger.info("Diff saved — portal=%s url=%s type=%s", portal, url, diff_type)


@_supabase_retry()
def get_baseline(portal, url):
    conn = get_conn()
    if USE_SUPABASE:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT html_path, screenshot_path, har_path, screenshot_url, html_url
                FROM public.baselines
                WHERE portal=%s AND url=%s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (portal, url),
            )
            row = cur.fetchone()
    else:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT html_path, screenshot_path, har_path, screenshot_url, html_url
               FROM baselines
               WHERE portal=? AND url=?
               ORDER BY updated_at DESC
               LIMIT 1""",
            (portal, url),
        )
        row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "html_path":       row["html_path"] if USE_SUPABASE else row[0],
            "screenshot_path": row["screenshot_path"] if USE_SUPABASE else row[1],
            "har_path":        row["har_path"] if USE_SUPABASE else row[2],
            "screenshot_url":  row["screenshot_url"] if USE_SUPABASE else row[3],
            "html_url":        row["html_url"] if USE_SUPABASE else row[4],
        }
    return None


@_supabase_retry()
def update_baseline(portal, url, html_path, screenshot_path, har_path, screenshot_url=None, html_url=None):
    """
    Always insert a new baseline row to keep full history.
    Includes Cloudinary URLs if available.
    """
    updated_at = datetime.now().isoformat()
    conn = get_conn()
    if USE_SUPABASE:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.baselines
                    (portal, url, html_path, screenshot_path, har_path, updated_at, screenshot_url, html_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (portal, url, html_path, screenshot_path, har_path, updated_at, screenshot_url, html_url),
            )
            conn.commit()
    else:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO baselines
               (portal, url, html_path, screenshot_path, har_path, updated_at, screenshot_url, html_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (portal, url, html_path, screenshot_path, har_path, updated_at, screenshot_url, html_url),
        )
        conn.commit()
    conn.close()
    logger.info("Baseline updated - portal=%s url=%s", portal, url)


def cleanup_old_snapshots(url_folder, keep=2):
    """Delete all but the `keep` most recent timestamp folders for a URL."""
    try:
        if not os.path.isdir(url_folder):
            return
        entries = sorted([
            e for e in os.listdir(url_folder)
            if os.path.isdir(os.path.join(url_folder, e))
        ])
        for folder_name in entries[:-keep]:
            full_path = os.path.join(url_folder, folder_name)
            shutil.rmtree(full_path, ignore_errors=True)
            logger.info("Deleted old snapshot folder: %s", full_path)
    except Exception as e:
        logger.error("Error during snapshot cleanup - %s", e)


def archive_artefacts(portal, url, screenshot_bytes, html_content, har_data):
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_url   = (
        url.replace("https://", "")
           .replace("http://", "")
           .replace("/", "_")
           .replace(":", "_")
    )
    url_folder = os.path.join(ARCHIVE_DIR, portal, safe_url)
    folder     = os.path.join(url_folder, timestamp)
    os.makedirs(folder, exist_ok=True)

    screenshot_path = os.path.join(folder, "screenshot.png")
    html_path       = os.path.join(folder, "snapshot.html")
    har_path        = os.path.join(folder, "network.har")

    if screenshot_bytes:
        with open(screenshot_path, "wb") as f:
            f.write(screenshot_bytes)
    if html_content:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
    if har_data:
        with open(har_path, "w", encoding="utf-8") as f:
            json.dump(har_data, f, indent=2)

    # Upload to Cloudinary (image for screenshot, raw for html)
    screenshot_url = upload_to_cloudinary(screenshot_path, resource_type="image")
    html_url       = upload_to_cloudinary(html_path, resource_type="raw")

    logger.info("Artefacts archived to %s", folder)
    cleanup_old_snapshots(url_folder, keep=2)
    return screenshot_path, html_path, har_path, screenshot_url, html_url


@_supabase_retry()
def start_crawl_log(portal):
    started_at = datetime.now().isoformat()
    conn = get_conn()
    if USE_SUPABASE:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.crawl_log (portal, started_at, status) VALUES (%s, %s, 'running') RETURNING id",
                (portal, started_at)
            )
            row = cur.fetchone()
            crawl_id = row['id'] if isinstance(row, dict) else row[0]
            conn.commit()
    else:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO crawl_log (portal, started_at, status) VALUES (?, ?, 'running')",
            (portal, started_at)
        )
        crawl_id = cursor.lastrowid
        conn.commit()
    conn.close()
    return crawl_id


@_supabase_retry()
def finish_crawl_log(crawl_id, pages_visited, status="done"):
    finished_at = datetime.now().isoformat()
    conn = get_conn()
    if USE_SUPABASE:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.crawl_log SET finished_at=%s, pages_visited=%s, status=%s WHERE id=%s",
                (finished_at, pages_visited, status, crawl_id)
            )
            conn.commit()
    else:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE crawl_log SET finished_at=?, pages_visited=?, status=? WHERE id=?",
            (finished_at, pages_visited, status, crawl_id)
        )
        conn.commit()
    conn.close()
    logger.info(
        "Crawl log finished - id=%s pages=%s status=%s",
        crawl_id, pages_visited, status
    )


@_supabase_retry()
def update_crawl_progress(crawl_id, pages_visited):
    """Update pages_visited for a running crawl immediately."""
    try:
        conn = get_conn()
        if USE_SUPABASE:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.crawl_log SET pages_visited=%s WHERE id=%s",
                    (pages_visited, crawl_id)
                )
                conn.commit()
            conn.close()
        else:
            cur = conn.cursor()
            cur.execute("UPDATE crawl_log SET pages_visited=? WHERE id=?", (pages_visited, crawl_id))
            conn.commit()
            conn.close()
        logger.info("Updated crawl progress - id=%s pages=%s", crawl_id, pages_visited)
    except Exception as e:
        logger.warning("Failed to update crawl progress: %s", e)


@_supabase_retry()
def get_all_changes():
    """Return all change records ordered by newest first (includes Cloudinary URLs)."""
    conn = get_conn()
    if USE_SUPABASE:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM public.changes ORDER BY timestamp DESC")
            rows = cur.fetchall()
    else:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM changes ORDER BY timestamp DESC")
        rows = cursor.fetchall()
    conn.close()
    return rows

@_supabase_retry()
def clear_baselines_for_portal(portal):
    conn = get_conn()
    if USE_SUPABASE:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.baselines WHERE portal=%s", (portal,))
            deleted = cur.rowcount
            conn.commit()
    else:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM baselines WHERE portal=?", (portal,))
        deleted = cursor.rowcount
        conn.commit()
    conn.close()
    logger.info("Cleared %s old baselines for portal: %s", deleted, portal)


@_supabase_retry()
def purge_old_records(keep_days):
    """
    Delete records older than *keep_days* days.
    Works for both back‑ends.
    """
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
    conn = get_conn()
    if USE_SUPABASE:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.changes WHERE timestamp < %s", (cutoff,))
            deleted = cur.rowcount
            conn.commit()
    else:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM changes WHERE timestamp < ?", (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
    conn.close()
    logger.info("Purged %s records older than %s days", deleted, keep_days)


if __name__ == "__main__":
    init_db()
    print("storage.py is working - database and tables created successfully.")