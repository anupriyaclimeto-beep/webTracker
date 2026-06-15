import json
import logging
import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from storage import get_conn, USE_SUPABASE, init_db

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

try:
    with open("config.json") as f:
        config = json.load(f)
except FileNotFoundError:
    # Fallback config for Vercel/cloud environments without config.json
    config = {
        "diff": {
            "noise_confidence_threshold": 0.6,
            "visual_change_min_ratio": 0.05,
            "pixel_threshold": 0.05,
            "text_change_min_words": 5,
            "text_line_min_changes": 3,
        },
        "storage": {"db": "database.db"},
        "portals": [],
    }
    logger.warning("config.json not found, using fallback configuration")

# Login credentials from .env
LOGIN_USER = os.getenv("LOGIN_USER", "webtracker@test.com")
LOGIN_PASS = os.getenv("LOGIN_PASS", "12345")

app = Flask(__name__, static_folder="frontend/dist", static_url_path="/")
CORS(app)

# Serve React App
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, "index.html")


def query_db(query, args=()):
    """Query the database using storage.py's connection (Supabase or SQLite)."""
    conn = get_conn()
    try:
        if USE_SUPABASE:
            with conn.cursor() as cur:
                cur.execute(query, args)
                rows = cur.fetchall()
            # psycopg2 RealDictCursor returns RealDictRow, convert to plain dicts
            return [dict(row) for row in rows]
        else:
            import sqlite3
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, args)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()


def _filter_visible_rows(rows):
    """Remove rows that are clearly noise-only or have placeholder summaries."""
    try:
        filtered = []
        # thresholds from config (fallbacks)
        diff_cfg = config.get("diff", {})
        conf_thresh = float(diff_cfg.get("noise_confidence_threshold", 0.6))
        visual_min = float(diff_cfg.get("visual_change_min_ratio", diff_cfg.get("pixel_threshold", 0.05)))
        text_min_words = int(diff_cfg.get("text_change_min_words", 5))
        text_min_lines = int(diff_cfg.get("text_line_min_changes", 3))

        # First pass: find all visible HTML changes and extract their (portal, url, date)
        visible_html_keys = set()
        for r in rows:
            dtype = (r.get("diff_type") or "").lower()
            if dtype == "html":
                try:
                    ai = (r.get("ai_summary") or "") or ""
                    if isinstance(ai, str) and ai.strip():
                        low = ai.lower()
                        if "no description" in low or "no visible" in low or "no changes" in low:
                            continue
                    detail = r.get("diff_detail") or {}
                    if isinstance(detail, str):
                        detail = json.loads(detail or "{}")
                    if not isinstance(detail, dict):
                        detail = {}
                    if bool(detail.get("is_noise")):
                        continue
                    conf = detail.get("confidence")
                    try:
                        conf = float(conf) if conf is not None else None
                    except Exception:
                        conf = None
                    if conf is not None and conf < conf_thresh:
                        continue
                    
                    words = int(detail.get("words_changed") or detail.get("wordsChanged") or 0)
                    lines = int(detail.get("diff_lines") or detail.get("lines_changed") or 0)
                    highlighted = detail.get("highlighted_lines") or []
                    if words >= text_min_words or lines >= text_min_lines or (highlighted and len(highlighted) > 0):
                        ts = r.get("timestamp")
                        date_str = str(ts)[:10] if ts else "" # "YYYY-MM-DD"
                        visible_html_keys.add((r.get("portal"), r.get("url"), date_str))
                except Exception:
                    pass

        for r in rows:
            try:
                ai = (r.get("ai_summary") or "") or ""
                if isinstance(ai, str) and ai.strip():
                    low = ai.lower()
                    if "no description" in low or "no visible" in low or "no changes" in low:
                        continue
                detail = r.get("diff_detail") or {}
                if isinstance(detail, str):
                    try:
                        detail = json.loads(detail or "{}")
                    except Exception:
                        detail = {}
                if not isinstance(detail, dict):
                    detail = {}

                # explicit noise flag
                if bool(detail.get("is_noise")):
                    continue
                # low confidence
                try:
                    conf = detail.get("confidence")
                    conf = float(conf) if conf is not None else None
                except Exception:
                    conf = None
                if conf is not None and conf < conf_thresh:
                    continue

                dtype = (r.get("diff_type") or "").lower()
                ts = r.get("timestamp")
                date_str = str(ts)[:10] if ts else ""
                
                if dtype == "visual":
                    try:
                        pixels = int(detail.get("changed_pixels") or 0)
                    except Exception:
                        pixels = 0
                    try:
                        ratio = float(detail.get("change_ratio") or 0.0)
                    except Exception:
                        ratio = 0.0
                    if pixels == 0 or ratio <= visual_min:
                        continue
                    # Visual change must have accompanying visible HTML change for same portal, URL and date
                    if (r.get("portal"), r.get("url"), date_str) not in visible_html_keys:
                        continue
                elif dtype == "html":
                    if (r.get("portal"), r.get("url"), date_str) not in visible_html_keys:
                        continue
                elif dtype in ("har", "json"):
                    if not detail:
                        continue
                    if dtype == "har":
                        new_ep = detail.get("new_endpoints") or []
                        rem_ep = detail.get("removed_endpoints") or []
                        if not (new_ep or rem_ep):
                            continue

                filtered.append(r)
            except Exception:
                # keep row if unexpected error in checks
                filtered.append(r)
        return filtered
    except Exception:
        return rows


@app.route("/")
def index():
    return jsonify({
        "status": "running",
        "db": "supabase" if USE_SUPABASE else "sqlite",
        "endpoints": [
            "/api/login",
            "/api/changes",
            "/api/portals",
            "/api/diffs",
            "/api/crawl-log",
            "/api/changes/<portal>",
            "/api/diffs/<portal>"
        ]
    })


# ── LOGIN ─────────────────────────────────────────────────────────────────────

@app.route("/api/login", methods=["POST"])
def api_login():
    try:
        data = request.get_json(force=True)
        username = data.get("username", "")
        password = data.get("password", "")

        if username == LOGIN_USER and password == LOGIN_PASS:
            logger.info("POST /api/login — success for %s", username)
            return jsonify({"success": True})
        else:
            logger.warning("POST /api/login — failed for %s", username)
            return jsonify({"success": False, "error": "Invalid credentials"})
    except Exception as e:
        logger.error("POST /api/login error — %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 500


# ── CHANGES ───────────────────────────────────────────────────────────────────

@app.route("/api/changes", methods=["GET"])
def get_changes():
    try:
        if USE_SUPABASE:
            rows = query_db("SELECT * FROM public.changes WHERE ai_summary IS NULL OR (ai_summary != 'No changes' AND ai_summary != 'No description generated for this change.') ORDER BY timestamp DESC")
        else:
            rows = query_db("SELECT * FROM changes WHERE ai_summary IS NULL OR (ai_summary != 'No changes' AND ai_summary != 'No description generated for this change.') ORDER BY timestamp DESC")
        rows = _filter_visible_rows(rows)
        logger.info("GET /api/changes — returned %s visible records (raw=%s)", len(rows), "unknown")
        return jsonify({
            "count": len(rows),
            "changes": rows
        })
    except Exception as e:
        logger.error("GET /api/changes error — %s", str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/api/changes/<portal>", methods=["GET"])
def get_changes_by_portal(portal):
    try:
        if USE_SUPABASE:
            rows = query_db(
                "SELECT * FROM public.changes WHERE portal=%s AND (ai_summary IS NULL OR (ai_summary != 'No changes' AND ai_summary != 'No description generated for this change.')) ORDER BY timestamp DESC",
                (portal,)
            )
        else:
            rows = query_db(
                "SELECT * FROM changes WHERE portal=? AND (ai_summary IS NULL OR (ai_summary != 'No changes' AND ai_summary != 'No description generated for this change.')) ORDER BY timestamp DESC",
                (portal,)
            )
        rows = _filter_visible_rows(rows)
        logger.info("GET /api/changes/%s — returned %s visible records (raw=%s)", portal, len(rows), "unknown")
        return jsonify({
            "portal": portal,
            "count": len(rows),
            "changes": rows
        })
    except Exception as e:
        logger.error("GET /api/changes/%s error — %s", portal, str(e))
        return jsonify({"error": str(e)}), 500


# ── PORTALS ───────────────────────────────────────────────────────────────────

@app.route("/api/portals", methods=["GET"])
def get_portals():
    try:
        portals = config.get("portals", [])
        if USE_SUPABASE:
            all_changes = query_db(
                "SELECT portal, url, diff_type, diff_detail, ai_summary, timestamp FROM public.changes WHERE ai_summary IS NULL OR (ai_summary != 'No changes' AND ai_summary != 'No description generated for this change.')"
            )
            crawl_rows = query_db(
                "SELECT DISTINCT ON (portal) portal, started_at, status FROM public.crawl_log ORDER BY portal, started_at DESC"
            )
        else:
            all_changes = query_db(
                "SELECT portal, url, diff_type, diff_detail, ai_summary, timestamp FROM changes WHERE ai_summary IS NULL OR (ai_summary != 'No changes' AND ai_summary != 'No description generated for this change.')"
            )
            crawl_rows = query_db(
                "SELECT portal, started_at, status FROM crawl_log ORDER BY started_at DESC"
            )
            
        # Filter changes using the Python helper
        filtered_changes = _filter_visible_rows(all_changes)
        
        # Aggregate stats in Python
        stats = {}
        for ch in filtered_changes:
            p = ch["portal"]
            if p not in stats:
                stats[p] = {"total_changes": 0, "last_change": None}
            stats[p]["total_changes"] += 1
            ts = ch["timestamp"]
            if ts:
                ts_str = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
                if not stats[p]["last_change"] or ts_str > stats[p]["last_change"]:
                    stats[p]["last_change"] = ts_str

        # Build crawl status lookup (latest crawl per portal)
        crawl_stats = {}
        for cr in crawl_rows:
            p = cr["portal"]
            if p not in crawl_stats:
                crawl_stats[p] = cr
        
        result = []
        for p in portals:
            name = p["name"]
            crawl_info = crawl_stats.get(name, {})
            last_crawl = crawl_info.get("started_at")
            # Convert datetime objects to ISO string if needed
            if last_crawl and hasattr(last_crawl, 'isoformat'):
                last_crawl = last_crawl.isoformat()
            result.append({
                "name": name,
                "url": p["url"],
                "auth": p["auth"],
                "total_changes": stats.get(name, {}).get("total_changes", 0),
                "last_change": stats.get(name, {}).get("last_change", None),
                "last_crawl_at": last_crawl,
                "last_status": crawl_info.get("status", None)
            })
        logger.info("GET /api/portals — returned %s portals", len(result))
        return jsonify({
            "count": len(result),
            "portals": result
        })
    except Exception as e:
        logger.error("GET /api/portals error — %s", str(e))
        return jsonify({"error": str(e)}), 500


# ── DIFFS ─────────────────────────────────────────────────────────────────────

@app.route("/api/diffs", methods=["GET"])
def get_diffs():
    try:
        diff_type = request.args.get("type")
        if USE_SUPABASE:
            if diff_type:
                rows = query_db(
                    "SELECT * FROM public.changes WHERE diff_type=%s AND (ai_summary IS NULL OR (ai_summary != 'No changes' AND ai_summary != 'No description generated for this change.')) ORDER BY timestamp DESC",
                    (diff_type,)
                )
            else:
                rows = query_db(
                    "SELECT * FROM public.changes WHERE ai_summary IS NULL OR (ai_summary != 'No changes' AND ai_summary != 'No description generated for this change.') ORDER BY timestamp DESC"
                )
        else:
            if diff_type:
                rows = query_db(
                    "SELECT * FROM changes WHERE diff_type=? AND (ai_summary IS NULL OR (ai_summary != 'No changes' AND ai_summary != 'No description generated for this change.')) ORDER BY timestamp DESC",
                    (diff_type,)
                )
            else:
                rows = query_db(
                    "SELECT * FROM changes WHERE ai_summary IS NULL OR (ai_summary != 'No changes' AND ai_summary != 'No description generated for this change.') ORDER BY timestamp DESC"
                )
        for row in rows:
            if isinstance(row.get("diff_detail"), str):
                try:
                    row["diff_detail"] = json.loads(row["diff_detail"])
                except Exception:
                    pass
        logger.info("GET /api/diffs — returned %s records", len(rows))
        return jsonify({
            "count": len(rows),
            "diffs": rows
        })
    except Exception as e:
        logger.error("GET /api/diffs error — %s", str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/api/diffs/<portal>", methods=["GET"])
def get_diffs_by_portal(portal):
    try:
        if USE_SUPABASE:
            rows = query_db(
                "SELECT * FROM public.changes WHERE portal=%s AND (ai_summary IS NULL OR (ai_summary != 'No changes' AND ai_summary != 'No description generated for this change.')) ORDER BY timestamp DESC",
                (portal,)
            )
        else:
            rows = query_db(
                "SELECT * FROM changes WHERE portal=? AND (ai_summary IS NULL OR (ai_summary != 'No changes' AND ai_summary != 'No description generated for this change.')) ORDER BY timestamp DESC",
                (portal,)
            )
        for row in rows:
            if isinstance(row.get("diff_detail"), str):
                try:
                    row["diff_detail"] = json.loads(row["diff_detail"])
                except Exception:
                    pass
        logger.info("GET /api/diffs/%s — returned %s records", portal, len(rows))
        return jsonify({
            "portal": portal,
            "count": len(rows),
            "diffs": rows
        })
    except Exception as e:
        logger.error("GET /api/diffs/%s error — %s", portal, str(e))
        return jsonify({"error": str(e)}), 500


# ── CRAWL LOG ─────────────────────────────────────────────────────────────────

@app.route("/api/crawl-log", methods=["GET"])
def get_crawl_log():
    try:
        if USE_SUPABASE:
            rows = query_db(
                "SELECT * FROM public.crawl_log ORDER BY started_at DESC"
            )
        else:
            rows = query_db(
                "SELECT * FROM crawl_log ORDER BY started_at DESC"
            )
        logger.info("GET /api/crawl-log — returned %s records", len(rows))
        return jsonify({
            "count": len(rows),
            "crawl_log": rows
        })
    except Exception as e:
        logger.error("GET /api/crawl-log error — %s", str(e))
        return jsonify({"error": str(e)}), 500


# ── CRAWLER CONTROL ─────────────────────────────────────────────────────────────

import subprocess
import threading
import sys

_BASE_APP_DIR = os.path.dirname(os.path.abspath(__file__)) or "."
PID_FILE = os.path.join(_BASE_APP_DIR, ".crawler.pid")
LOG_FILE = os.path.join(_BASE_APP_DIR, ".crawler.log")
LOGIN_FLAG = os.path.join(_BASE_APP_DIR, ".login_needed")

def tee_output(pipe, log_file, is_stderr=False):
    try:
        with open(log_file, "a", encoding="utf-8", errors="replace") as f:
            for line in iter(pipe.readline, ""):
                f.write(line)
                f.flush()
    except Exception as e:
        print(f"Error in logging tee: {e}")

def check_process_running(pid):
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}"], stderr=subprocess.DEVNULL, text=True)
            return str(pid) in out
        else:
            proc = subprocess.run(["ps", "-p", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return proc.returncode == 0
    except Exception:
        return False

@app.route("/api/crawl/status", methods=["GET"])
def crawl_status():
    try:
        # Check running state from DB
        if USE_SUPABASE:
            rows = query_db("SELECT id, portal, started_at, pages_visited FROM public.crawl_log WHERE status='running' AND CAST(started_at AS timestamp) >= NOW() - INTERVAL '15 minutes' ORDER BY started_at DESC LIMIT 1")
        else:
            rows = query_db("SELECT id, portal, started_at, pages_visited FROM crawl_log WHERE status='running' AND started_at >= datetime('now','-15 minutes') ORDER BY started_at DESC LIMIT 1")
        
        running = False
        db_status = "stopped"
        
        if rows:
            if os.path.exists(PID_FILE):
                try:
                    with open(PID_FILE, "r") as f:
                        pid = int(f.read().strip())
                    running = check_process_running(pid)
                    if running:
                        db_status = "running"
                        if os.path.exists(LOGIN_FLAG):
                            db_status = "slow" # Using 'slow' as a proxy for 'waiting for manual login' in UI
                    else:
                        os.remove(PID_FILE)
                except Exception:
                    pass

        # Read logs
        logs = "No log file yet."
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            logs = "".join(lines[-60:]) if lines else "Log is empty."

        return jsonify({
            "running": running,
            "db_status": db_status,
            "logs": logs
        })
    except Exception as e:
        logger.error("GET /api/crawl/status error — %s", str(e))
        return jsonify({"error": str(e)}), 500

@app.route("/api/crawl/start", methods=["POST"])
def crawl_start():
    try:
        data = request.get_json(force=True) if request.is_json else {}
        portal = data.get("portal")
        if portal == "All Portals":
            portal = None

        cmd = [sys.executable, "crawler.py", "--once"]
        if portal:
            cmd.extend(["--portal", portal])

        # Reset log file
        try:
            if os.path.exists(LOG_FILE):
                os.remove(LOG_FILE)
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass

        env = os.environ.copy()
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_BASE_APP_DIR,
            env=env
        )
        
        t1 = threading.Thread(target=tee_output, args=(proc.stdout, LOG_FILE, False), daemon=True)
        t2 = threading.Thread(target=tee_output, args=(proc.stderr, LOG_FILE, True), daemon=True)
        t1.start()
        t2.start()
        
        with open(PID_FILE, "w") as f: 
            f.write(str(proc.pid))
            
        return jsonify({"success": True, "pid": proc.pid})
    except Exception as e:
        logger.error("POST /api/crawl/start error — %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/crawl/stop", methods=["POST"])
def crawl_stop():
    killed = False
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE) as f: 
                pid = int(f.read().strip())
            if sys.platform == "win32":
                subprocess.call(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                import signal
                os.kill(pid, signal.SIGTERM)
            os.remove(PID_FILE)
            killed = True
            
        if os.path.exists(LOGIN_FLAG):
            os.remove(LOGIN_FLAG)
            
        if USE_SUPABASE:
            query_db("UPDATE public.crawl_log SET status='stopped', finished_at=NOW() WHERE status='running'")
        else:
            query_db("UPDATE crawl_log SET status='stopped', finished_at=datetime('now') WHERE status='running'")
            
        return jsonify({"success": True, "killed": killed})
    except Exception as e:
        logger.error("POST /api/crawl/stop error — %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    init_db()
    print("\nFlask REST API starting...")
    print(f"Database: {'Supabase (PostgreSQL)' if USE_SUPABASE else 'SQLite'}")
    print("Available endpoints:")
    print("  http://localhost:5000/")
    print("  http://localhost:5000/api/login       (POST)")
    print("  http://localhost:5000/api/changes")
    print("  http://localhost:5000/api/portals")
    print("  http://localhost:5000/api/diffs")
    print("  http://localhost:5000/api/crawl-log")
    print("  http://localhost:5000/api/changes/<portal>")
    print("  http://localhost:5000/api/diffs/<portal>")
    print("  http://localhost:5000/api/crawl/status")
    print("  http://localhost:5000/api/crawl/start (POST)")
    print("  http://localhost:5000/api/crawl/stop  (POST)\n")
    app.run(debug=True, port=5000)