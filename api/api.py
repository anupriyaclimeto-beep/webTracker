import json
import logging
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import pg8000
from datetime import datetime, timedelta

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Supabase PostgreSQL credentials
SUPABASE_HOST = os.getenv("SUPABASE_HOST", "").strip()
SUPABASE_PORT = int(os.getenv("SUPABASE_PORT", "5432"))
SUPABASE_DB = os.getenv("SUPABASE_DB", "postgres").strip()
SUPABASE_USER = os.getenv("SUPABASE_USER", "").strip()
SUPABASE_PASSWORD = os.getenv("SUPABASE_PASSWORD", "").strip()

USE_SUPABASE = bool(SUPABASE_HOST and SUPABASE_USER and SUPABASE_PASSWORD)
DEMO_MODE = True  # Show sample data for presentation

# Login credentials
LOGIN_USER = os.getenv("LOGIN_USER", "webtracker@test.com")
LOGIN_PASS = os.getenv("LOGIN_PASS", "12345")

app = Flask(__name__)
CORS(app)

# Sample demo data for presentation
DEMO_PORTALS = [
    {"portal": "EPR PLASTIC", "last_crawl_at": (datetime.now() - timedelta(hours=2)).isoformat(), "last_status": "done", "total_changes": 5},
    {"portal": "EPR EWASTE", "last_crawl_at": (datetime.now() - timedelta(hours=4)).isoformat(), "last_status": "done", "total_changes": 3},
    {"portal": "EPR BATTERY", "last_crawl_at": (datetime.now() - timedelta(days=1)).isoformat(), "last_status": "done", "total_changes": 2},
]

DEMO_CHANGES = [
    {"id": 1, "portal": "EPR PLASTIC", "url": "https://cpcbcetp.nic.in/plastic/", "diff_type": "html", "summary": "Updated plastic waste guidelines", "timestamp": (datetime.now() - timedelta(hours=1)).isoformat()},
    {"id": 2, "portal": "EPR PLASTIC", "url": "https://cpcbcetp.nic.in/plastic/about", "diff_type": "visual", "summary": "Logo changed", "timestamp": (datetime.now() - timedelta(hours=2)).isoformat()},
    {"id": 3, "portal": "EPR EWASTE", "url": "https://cpcbcetp.nic.in/ewaste/", "diff_type": "html", "summary": "New regulatory update", "timestamp": (datetime.now() - timedelta(hours=3)).isoformat()},
]

DEMO_CRAWL_LOG = [
    {"id": 1, "portal": "EPR PLASTIC", "started_at": (datetime.now() - timedelta(hours=2)).isoformat(), "finished_at": (datetime.now() - timedelta(hours=1, minutes=45)).isoformat(), "status": "done", "pages_visited": 11},
    {"id": 2, "portal": "EPR EWASTE", "started_at": (datetime.now() - timedelta(hours=4)).isoformat(), "finished_at": (datetime.now() - timedelta(hours=3, minutes=50)).isoformat(), "status": "done", "pages_visited": 8},
    {"id": 3, "portal": "EPR BATTERY", "started_at": (datetime.now() - timedelta(days=1)).isoformat(), "finished_at": (datetime.now() - timedelta(days=1, hours=1, minutes=15)).isoformat(), "status": "done", "pages_visited": 7},
]

def get_db_connection():
    """Establish connection to Supabase PostgreSQL"""
    if not USE_SUPABASE:
        raise RuntimeError("Database not configured")
    
    try:
        conn = pg8000.connect(
            host=SUPABASE_HOST,
            port=SUPABASE_PORT,
            database=SUPABASE_DB,
            user=SUPABASE_USER,
            password=SUPABASE_PASSWORD,
            ssl_context=True,
            timeout=10
        )
        return conn
    except Exception as e:
        logger.warning("Failed to connect to Supabase: %s (using demo data)", str(e))
        return None

def query_db(sql):
    """Execute query and return results as list of dicts"""
    try:
        conn = get_db_connection()
        if not conn:
            return None  # Signal to use demo data
        cursor = conn.cursor()
        cursor.execute(sql)
        # Get column names from cursor.description
        columns = [desc[0] for desc in cursor.description] if cursor.description else None
        rows = cursor.fetchall()
        conn.close()
        if rows and columns:
            return [dict(zip(columns, row)) for row in rows]
        return []
    except Exception as e:
        logger.warning("Query failed: %s (using demo data)", str(e))
        return None  # Signal to use demo data

@app.route("/")
def index():
    return jsonify({
        "status": "running",
        "mode": "demo" if DEMO_MODE else "live",
        "db": "supabase",
        "endpoints": {
            "login": "/api/login",
            "portals": "/api/portals",
            "changes": "/api/changes",
            "crawl_log": "/api/crawl-log",
            "crawl_status": "/api/crawl/status"
        }
    })

@app.route("/api/login", methods=["POST"])
def api_login():
    try:
        data = request.get_json(force=True) or {}
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()

        if username == LOGIN_USER and password == LOGIN_PASS:
            logger.info("✓ Login successful for %s", username)
            return jsonify({"success": True})
        else:
            logger.warning("✗ Login failed for %s", username)
            return jsonify({"success": False, "error": "Invalid credentials"})
    except Exception as e:
        logger.error("Login error: %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/portals", methods=["GET"])
def get_portals():
    try:
        # Use a subquery to get the latest crawl per portal, then join for status
        rows = query_db("""
            SELECT
                cl.portal        AS name,
                cl.started_at    AS last_crawl_at,
                cl.status        AS last_status,
                COALESCE(ch.cnt, 0) AS total_changes
            FROM (
                SELECT DISTINCT ON (portal) portal, started_at, status
                FROM crawl_log
                ORDER BY portal, started_at DESC
            ) cl
            LEFT JOIN (
                SELECT portal, COUNT(*) AS cnt FROM changes GROUP BY portal
            ) ch ON ch.portal = cl.portal
            ORDER BY cl.portal
        """)
        
        # If database fails, use demo data
        if rows is None:
            rows = DEMO_PORTALS
            logger.info("✓ Using DEMO portals: %d records", len(rows))
        else:
            # Convert datetime objects to ISO strings for JSON serialization
            for row in rows:
                if isinstance(row.get('last_crawl_at'), datetime):
                    row['last_crawl_at'] = row['last_crawl_at'].isoformat()
            logger.info("✓ DB portals: %d records", len(rows) if rows else 0)
        
        return jsonify({
            "count": len(rows) if rows else 0,
            "portals": rows if rows else []
        })
    except Exception as e:
        logger.error("GET /api/portals error: %s", str(e))
        # Fallback to demo
        return jsonify({
            "count": len(DEMO_PORTALS),
            "portals": DEMO_PORTALS
        })

@app.route("/api/changes", methods=["GET"])
@app.route("/api/changes/<portal>", methods=["GET"])
def get_changes(portal=None):
    try:
        if portal:
            rows = query_db(f"SELECT * FROM changes WHERE portal = '{portal}' ORDER BY timestamp DESC LIMIT 100")
        else:
            rows = query_db("SELECT * FROM changes ORDER BY timestamp DESC LIMIT 100")
        
        # If database fails, use demo data
        if rows is None:
            rows = DEMO_CHANGES
            logger.info("✓ Using DEMO changes: %d records", len(rows))
        else:
            # Convert datetime objects to ISO strings for JSON serialization
            for row in rows:
                for key in ['timestamp']:
                    if isinstance(row.get(key), datetime):
                        row[key] = row[key].isoformat()
                # Parse diff_detail from JSON string if needed
                if isinstance(row.get('diff_detail'), str):
                    try:
                        row['diff_detail'] = json.loads(row['diff_detail'])
                    except (json.JSONDecodeError, TypeError):
                        pass
            logger.info("✓ DB changes: %d records", len(rows) if rows else 0)
        
        return jsonify({
            "count": len(rows) if rows else 0,
            "changes": rows if rows else []
        })
    except Exception as e:
        logger.error("GET /api/changes error: %s", str(e))
        # Fallback to demo
        return jsonify({
            "count": len(DEMO_CHANGES),
            "changes": DEMO_CHANGES
        })

@app.route("/api/crawl-log", methods=["GET"])
def get_crawl_log():
    try:
        rows = query_db("SELECT * FROM crawl_log ORDER BY started_at DESC LIMIT 50")
        
        # If database fails, use demo data
        if rows is None:
            rows = DEMO_CRAWL_LOG
            logger.info("✓ Using DEMO crawl log: %d records", len(rows))
        else:
            # Convert datetime objects to ISO strings for JSON serialization
            for row in rows:
                for key in ['started_at', 'finished_at']:
                    if isinstance(row.get(key), datetime):
                        row[key] = row[key].isoformat()
            logger.info("✓ DB crawl log: %d records", len(rows) if rows else 0)
        
        return jsonify({
            "count": len(rows) if rows else 0,
            "crawl_log": rows if rows else []
        })
    except Exception as e:
        logger.error("GET /api/crawl-log error: %s", str(e))
        # Fallback to demo
        return jsonify({
            "count": len(DEMO_CRAWL_LOG),
            "crawl_log": DEMO_CRAWL_LOG
        })

@app.route("/api/crawl/status", methods=["GET"])
def crawl_status():
    """Get crawler status"""
    try:
        rows = query_db("SELECT * FROM crawl_log WHERE status='running' ORDER BY started_at DESC LIMIT 1")
        
        if rows is None:
            # Demo mode - show stopped
            return jsonify({
                "running": False,
                "status": "demo_stopped",
                "logs": "Demo mode - crawler control requires local deployment"
            })
        
        running = len(rows) > 0 if rows else False
        return jsonify({
            "running": running,
            "status": "running" if running else "stopped",
            "logs": "Crawler status available"
        })
    except Exception as e:
        logger.error("GET /api/crawl/status error: %s", str(e))
        return jsonify({"running": False, "status": "error", "error": str(e)})

@app.route("/api/crawl/start", methods=["POST"])
def crawl_start():
    """Start crawler endpoint"""
    return jsonify({"success": True, "message": "Crawler control requires local deployment"})

@app.route("/api/crawl/stop", methods=["POST"])
def crawl_stop():
    """Stop crawler endpoint"""
    return jsonify({"success": True, "message": "Crawler control requires local deployment"})

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Flask API Starting...")
    logger.info("Mode: %s", "DEMO (fallback data)" if DEMO_MODE else "LIVE DATABASE")
    logger.info("Database: %s", "Supabase PostgreSQL" if USE_SUPABASE else "NOT CONFIGURED")
    logger.info("=" * 60)
    port = int(os.getenv("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
