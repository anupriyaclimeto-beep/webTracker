import sqlite3
import os
import shutil
import json
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)

DB_PATH = config["storage"]["db"]
ARCHIVE_DIR = config["storage"]["archive_dir"]


def init_db():
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS changes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            portal      TEXT NOT NULL,
            url         TEXT NOT NULL,
            diff_type   TEXT NOT NULL,
            diff_detail TEXT,
            timestamp   TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS baselines (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            portal          TEXT NOT NULL,
            url             TEXT NOT NULL,
            html_path       TEXT,
            screenshot_path TEXT,
            har_path        TEXT,
            updated_at      TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_baselines_portal_url
        ON baselines (portal, url)
    """)

    cursor.execute("""
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

    # ── Migration: drop UNIQUE constraint if the DB was created by an older
    #    version of this file.  We do this by checking the table's SQL
    #    definition; if it contains "UNIQUE", we rebuild the table without it.
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
                updated_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_baselines_portal_url
                ON baselines (portal, url);
            INSERT INTO baselines SELECT * FROM baselines_old;
            DROP TABLE baselines_old;
        """)
        conn.commit()
        logger.info("Migration complete.")

    conn.close()
    logger.info("Database initialised at %s", DB_PATH)


def save_diff(portal, url, diff_type, diff_detail):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO changes (portal, url, diff_type, diff_detail, timestamp) VALUES (?, ?, ?, ?, ?)",
        (portal, url, diff_type, json.dumps(diff_detail), timestamp)
    )
    conn.commit()
    conn.close()
    logger.info("Diff saved — portal=%s url=%s type=%s", portal, url, diff_type)


def get_baseline(portal, url):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT html_path, screenshot_path, har_path
           FROM baselines
           WHERE portal=? AND url=?
           ORDER BY updated_at DESC
           LIMIT 1""",
        (portal, url)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "html_path":       row[0],
            "screenshot_path": row[1],
            "har_path":        row[2],
        }
    return None


def update_baseline(portal, url, html_path, screenshot_path, har_path):
    """
    Always insert a new baseline row so we keep a full history.
    get_baseline() retrieves the most recent row via ORDER BY updated_at DESC,
    so diffing always compares against the previous snapshot.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    updated_at = datetime.now().isoformat()
    cursor.execute(
        """INSERT INTO baselines
               (portal, url, html_path, screenshot_path, har_path, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (portal, url, html_path, screenshot_path, har_path, updated_at)
    )
    conn.commit()
    conn.close()
    logger.info("Baseline updated — portal=%s url=%s", portal, url)


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
        logger.error("Error during snapshot cleanup — %s", e)


def archive_artefacts(portal, url, screenshot_bytes, html_content, har_data):
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_url   = (
        url.replace("https://", "").replace("http://", "")
           .replace("/", "_").replace(":", "_")
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

    logger.info("Artefacts archived to %s", folder)
    cleanup_old_snapshots(url_folder, keep=2)
    return screenshot_path, html_path, har_path


def start_crawl_log(portal):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    started_at = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO crawl_log (portal, started_at, status) VALUES (?, ?, 'running')",
        (portal, started_at)
    )
    crawl_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return crawl_id


def finish_crawl_log(crawl_id, pages_visited, status="done"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    finished_at = datetime.now().isoformat()
    cursor.execute(
        "UPDATE crawl_log SET finished_at=?, pages_visited=?, status=? WHERE id=?",
        (finished_at, pages_visited, status, crawl_id)
    )
    conn.commit()
    conn.close()
    logger.info(
        "Crawl log finished — id=%s pages=%s status=%s",
        crawl_id, pages_visited, status
    )


def get_all_changes():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM changes ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows


def clear_baselines_for_portal(portal):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM baselines WHERE portal=?", (portal,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    logger.info("Cleared %s old baselines for portal: %s", deleted, portal)


def purge_old_records(keep_days):
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM changes WHERE timestamp < ?", (cutoff,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    logger.info("Purged %s records older than %s days", deleted, keep_days)


if __name__ == "__main__":
    init_db()
    print("storage.py is working — database and tables created successfully.")