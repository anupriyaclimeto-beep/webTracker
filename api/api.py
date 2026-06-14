import json
import logging
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import pg8000.native

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Supabase PostgreSQL credentials
SUPABASE_HOST = os.getenv("SUPABASE_HOST", "").strip()
SUPABASE_PORT = int(os.getenv("SUPABASE_PORT", "6543"))
SUPABASE_DB = os.getenv("SUPABASE_DB", "postgres").strip()
SUPABASE_USER = os.getenv("SUPABASE_USER", "").strip()
SUPABASE_PASSWORD = os.getenv("SUPABASE_PASSWORD", "").strip()

USE_SUPABASE = bool(SUPABASE_HOST and SUPABASE_USER and SUPABASE_PASSWORD)

# Login credentials
LOGIN_USER = os.getenv("LOGIN_USER", "webtracker@test.com")
LOGIN_PASS = os.getenv("LOGIN_PASS", "12345")

app = Flask(__name__)
CORS(app)

def get_db_connection():
    """Establish connection to Supabase PostgreSQL"""
    if not USE_SUPABASE:
        logger.error("Supabase credentials not configured")
        raise RuntimeError("Database not configured")
    
    try:
        conn = pg8000.native.connect(
            host=SUPABASE_HOST,
            port=SUPABASE_PORT,
            database=SUPABASE_DB,
            user=SUPABASE_USER,
            password=SUPABASE_PASSWORD,
            ssl_context=True
        )
        return conn
    except Exception as e:
        logger.error("Failed to connect to Supabase: %s", str(e))
        raise

def query_db(sql):
    """Execute query and return results as list of dicts"""
    try:
        conn = get_db_connection()
        result = conn.run(sql)
        conn.close()
        return result if result else []
    except Exception as e:
        logger.error("Query failed: %s - SQL: %s", str(e), sql)
        return []

@app.route("/")
def index():
    return jsonify({
        "status": "running",
        "db": "supabase" if USE_SUPABASE else "not_configured",
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
        sql = """
        SELECT DISTINCT 
            cl.portal,
            MAX(cl.started_at) as last_crawl_at,
            (SELECT status FROM crawl_log WHERE portal = cl.portal ORDER BY started_at DESC LIMIT 1) as last_status,
            (SELECT COUNT(*) FROM changes WHERE portal = cl.portal) as total_changes
        FROM crawl_log cl
        GROUP BY cl.portal
        ORDER BY cl.portal
        """
        rows = query_db(sql)
        logger.info("✓ Portals: %d records", len(rows) if rows else 0)
        return jsonify({
            "count": len(rows) if rows else 0,
            "portals": rows if rows else []
        })
    except Exception as e:
        logger.error("GET /api/portals error: %s", str(e))
        return jsonify({"error": str(e), "portals": []}), 500

@app.route("/api/changes", methods=["GET"])
def get_changes():
    try:
        sql = "SELECT * FROM changes ORDER BY timestamp DESC LIMIT 100"
        rows = query_db(sql)
        logger.info("✓ Changes: %d records", len(rows) if rows else 0)
        return jsonify({
            "count": len(rows) if rows else 0,
            "changes": rows if rows else []
        })
    except Exception as e:
        logger.error("GET /api/changes error: %s", str(e))
        return jsonify({"error": str(e), "changes": []}), 500

@app.route("/api/crawl-log", methods=["GET"])
def get_crawl_log():
    try:
        sql = "SELECT * FROM crawl_log ORDER BY started_at DESC LIMIT 50"
        rows = query_db(sql)
        logger.info("✓ Crawl log: %d records", len(rows) if rows else 0)
        return jsonify({
            "count": len(rows) if rows else 0,
            "crawl_log": rows if rows else []
        })
    except Exception as e:
        logger.error("GET /api/crawl-log error: %s", str(e))
        return jsonify({"error": str(e), "crawl_log": []}), 500

@app.route("/api/crawl/status", methods=["GET"])
def crawl_status():
    """Get crawler status"""
    try:
        sql = "SELECT * FROM crawl_log WHERE status='running' ORDER BY started_at DESC LIMIT 1"
        rows = query_db(sql)
        running = len(rows) > 0 if rows else False
        return jsonify({
            "running": running,
            "status": "running" if running else "stopped",
            "logs": "Crawler status available"
        })
    except Exception as e:
        logger.error("GET /api/crawl/status error: %s", str(e))
        return jsonify({"running": False, "status": "error", "error": str(e)}), 500

@app.route("/api/crawl/start", methods=["POST"])
def crawl_start():
    """Start crawler endpoint (demo - local crawler only)"""
    return jsonify({"success": True, "message": "Crawler control via API requires local deployment"})

@app.route("/api/crawl/stop", methods=["POST"])
def crawl_stop():
    """Stop crawler endpoint (demo - local crawler only)"""
    return jsonify({"success": True, "message": "Crawler control via API requires local deployment"})

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Flask API Starting...")
    logger.info("Database: %s", "Supabase PostgreSQL" if USE_SUPABASE else "NOT CONFIGURED")
    if USE_SUPABASE:
        logger.info("Host: %s", SUPABASE_HOST)
        logger.info("Database: %s", SUPABASE_DB)
        logger.info("User: %s", SUPABASE_USER)
    logger.info("=" * 60)
    app.run(debug=True, port=5000)
