import json
import logging
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import requests

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Supabase REST API config
SUPABASE_HOST = os.getenv("SUPABASE_HOST", "").replace("db.", "").replace(".postgres.supabase.co", "")
SUPABASE_URL = f"https://{SUPABASE_HOST}.supabase.co" if SUPABASE_HOST else ""
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_API_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

# Login credentials
LOGIN_USER = os.getenv("LOGIN_USER", "webtracker@test.com")
LOGIN_PASS = os.getenv("LOGIN_PASS", "12345")

app = Flask(__name__)
CORS(app)

def query_supabase(table, select="*", order_by=None, limit=None):
    """Query Supabase REST API (lightweight, no psycopg2)"""
    if not USE_SUPABASE:
        logger.warning("Supabase not configured")
        return []
    
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    params = {"select": select}
    if order_by:
        params["order"] = order_by
    if limit:
        params["limit"] = limit
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json() if response.text else []
    except Exception as e:
        logger.error("Supabase query failed: %s", str(e))
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
        portals = query_supabase("crawl_log", select="portal,started_at,status", order_by="portal,started_at.desc")
        
        # Group by portal (get latest)
        portal_stats = {}
        for record in portals:
            p = record.get("portal")
            if p and p not in portal_stats:
                portal_stats[p] = {
                    "portal": p,
                    "last_crawl_at": record.get("started_at"),
                    "last_status": record.get("status")
                }
        
        result = list(portal_stats.values())
        logger.info("GET /api/portals — returned %s portals", len(result))
        return jsonify({
            "count": len(result),
            "portals": result
        })
    except Exception as e:
        logger.error("GET /api/portals error — %s", str(e))
        return jsonify({"error": str(e)}), 500

@app.route("/api/changes", methods=["GET"])
def get_changes():
    try:
        changes = query_supabase("changes", select="*", order_by="timestamp.desc", limit=100)
        logger.info("GET /api/changes — returned %s records", len(changes))
        return jsonify({
            "count": len(changes),
            "changes": changes
        })
    except Exception as e:
        logger.error("GET /api/changes error — %s", str(e))
        return jsonify({"error": str(e)}), 500

@app.route("/api/crawl-log", methods=["GET"])
def get_crawl_log():
    try:
        logs = query_supabase("crawl_log", select="*", order_by="started_at.desc", limit=50)
        logger.info("GET /api/crawl-log — returned %s records", len(logs))
        return jsonify({
            "count": len(logs),
            "crawl_log": logs
        })
    except Exception as e:
        logger.error("GET /api/crawl-log error — %s", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    logger.info("Flask API starting...")
    logger.info("Database: %s", "Supabase REST API" if USE_SUPABASE else "Not configured")
    app.run(debug=True, port=5000)
