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
SUPABASE_HOST = os.getenv("SUPABASE_HOST", "")
SUPABASE_PORT = int(os.getenv("SUPABASE_PORT", "6543"))
SUPABASE_DB = os.getenv("SUPABASE_DB", "postgres")
SUPABASE_USER = os.getenv("SUPABASE_USER", "")
SUPABASE_PASSWORD = os.getenv("SUPABASE_PASSWORD", "")

USE_SUPABASE = all([SUPABASE_HOST, SUPABASE_USER, SUPABASE_PASSWORD])

# Login credentials
LOGIN_USER = os.getenv("LOGIN_USER", "webtracker@test.com")
LOGIN_PASS = os.getenv("LOGIN_PASS", "12345")

app = Flask(__name__)
CORS(app)

def query_db(sql, params=None):
    """Query Supabase PostgreSQL using pg8000 (lightweight, pure Python)"""
    if not USE_SUPABASE:
        logger.warning("Supabase not configured")
        return []
    
    try:
        conn = pg8000.native.connect(
            host=SUPABASE_HOST,
            port=SUPABASE_PORT,
            database=SUPABASE_DB,
            user=SUPABASE_USER,
            password=SUPABASE_PASSWORD,
            ssl_context=True
        )
        cursor = conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        
        # Convert tuples to dicts
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        result = [dict(zip(columns, row)) for row in rows]
        return result
    except Exception as e:
        logger.error("Database query failed: %s", str(e))
        return []

@app.route("/")
def index():
    return jsonify({
        "status": "running",
        "db": "supabase" if USE_SUPABASE else "none",
        "endpoints": [
            "/api/login",
            "/api/changes",
            "/api/portals",
            "/api/crawl-log"
        ]
    })

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

@app.route("/api/portals", methods=["GET"])
def get_portals():
    try:
        rows = query_db("SELECT DISTINCT portal, MAX(started_at) as last_crawl_at, status as last_status FROM crawl_log GROUP BY portal ORDER BY portal")
        logger.info("GET /api/portals — returned %s portals", len(rows))
        return jsonify({
            "count": len(rows),
            "portals": rows
        })
    except Exception as e:
        logger.error("GET /api/portals error — %s", str(e))
        return jsonify({"error": str(e)}), 500

@app.route("/api/changes", methods=["GET"])
def get_changes():
    try:
        rows = query_db("SELECT * FROM changes ORDER BY timestamp DESC LIMIT 100")
        logger.info("GET /api/changes — returned %s records", len(rows))
        return jsonify({
            "count": len(rows),
            "changes": rows
        })
    except Exception as e:
        logger.error("GET /api/changes error — %s", str(e))
        return jsonify({"error": str(e)}), 500

@app.route("/api/crawl-log", methods=["GET"])
def get_crawl_log():
    try:
        rows = query_db("SELECT * FROM crawl_log ORDER BY started_at DESC LIMIT 50")
        logger.info("GET /api/crawl-log — returned %s records", len(rows))
        return jsonify({
            "count": len(rows),
            "crawl_log": rows
        })
    except Exception as e:
        logger.error("GET /api/crawl-log error — %s", str(e))
        return jsonify({"error": str(e)}), 500

@app.route("/api/crawl/status", methods=["GET"])
def crawl_status():
    """Get crawler status"""
    try:
        rows = query_db("SELECT * FROM crawl_log WHERE status='running' ORDER BY started_at DESC LIMIT 1")
        running = len(rows) > 0
        logs = "No recent crawl logs"
        if rows:
            logs = f"Last crawl: {rows[0].get('portal')} - Status: {rows[0].get('status')}"
        return jsonify({
            "running": running,
            "logs": logs
        })
    except Exception as e:
        logger.error("GET /api/crawl/status error — %s", str(e))
        return jsonify({"running": False, "logs": f"Error: {str(e)}"}), 500

@app.route("/api/crawl/start", methods=["POST"])
def crawl_start():
    """Start crawler - for demo, just return success"""
    try:
        return jsonify({"success": True, "message": "Crawler started"})
    except Exception as e:
        logger.error("POST /api/crawl/start error — %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/crawl/stop", methods=["POST"])
def crawl_stop():
    """Stop crawler - for demo, just return success"""
    try:
        return jsonify({"success": True, "message": "Crawler stopped"})
    except Exception as e:
        logger.error("POST /api/crawl/stop error — %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    logger.info("Flask API starting...")
    logger.info("Database: %s", "Supabase PostgreSQL" if USE_SUPABASE else "Not configured")
    app.run(debug=True, port=5000)
