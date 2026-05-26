import json
import logging
from flask import Flask, jsonify, request
from storage import get_all_changes, init_db
import sqlite3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)

DB_PATH = config["storage"]["db"]

app = Flask(__name__)


def query_db(query, args=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(query, args)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.route("/")
def index():
    return jsonify({
        "status": "running",
        "endpoints": [
            "/changes",
            "/portals",
            "/diffs",
            "/crawl-log",
            "/changes/<portal>",
            "/diffs/<portal>"
        ]
    })


@app.route("/changes", methods=["GET"])
def get_changes():
    try:
        rows = query_db("SELECT * FROM changes ORDER BY timestamp DESC")
        logger.info("GET /changes — returned %s records", len(rows))
        return jsonify({
            "count": len(rows),
            "changes": rows
        })
    except Exception as e:
        logger.error("GET /changes error — %s", str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/changes/<portal>", methods=["GET"])
def get_changes_by_portal(portal):
    try:
        rows = query_db(
            "SELECT * FROM changes WHERE portal=? ORDER BY timestamp DESC",
            (portal,)
        )
        logger.info("GET /changes/%s — returned %s records", portal, len(rows))
        return jsonify({
            "portal": portal,
            "count": len(rows),
            "changes": rows
        })
    except Exception as e:
        logger.error("GET /changes/%s error — %s", portal, str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/portals", methods=["GET"])
def get_portals():
    try:
        portals = config.get("portals", [])
        rows = query_db(
            "SELECT portal, COUNT(*) as total_changes, MAX(timestamp) as last_change FROM changes GROUP BY portal"
        )
        stats = {r["portal"]: r for r in rows}
        result = []
        for p in portals:
            name = p["name"]
            result.append({
                "name": name,
                "url": p["url"],
                "auth": p["auth"],
                "total_changes": stats.get(name, {}).get("total_changes", 0),
                "last_change": stats.get(name, {}).get("last_change", None)
            })
        logger.info("GET /portals — returned %s portals", len(result))
        return jsonify({
            "count": len(result),
            "portals": result
        })
    except Exception as e:
        logger.error("GET /portals error — %s", str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/diffs", methods=["GET"])
def get_diffs():
    try:
        diff_type = request.args.get("type")
        if diff_type:
            rows = query_db(
                "SELECT * FROM changes WHERE diff_type=? ORDER BY timestamp DESC",
                (diff_type,)
            )
        else:
            rows = query_db(
                "SELECT * FROM changes ORDER BY timestamp DESC"
            )
        for row in rows:
            try:
                row["diff_detail"] = json.loads(row["diff_detail"])
            except Exception:
                pass
        logger.info("GET /diffs — returned %s records", len(rows))
        return jsonify({
            "count": len(rows),
            "diffs": rows
        })
    except Exception as e:
        logger.error("GET /diffs error — %s", str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/diffs/<portal>", methods=["GET"])
def get_diffs_by_portal(portal):
    try:
        rows = query_db(
            "SELECT * FROM changes WHERE portal=? ORDER BY timestamp DESC",
            (portal,)
        )
        for row in rows:
            try:
                row["diff_detail"] = json.loads(row["diff_detail"])
            except Exception:
                pass
        logger.info("GET /diffs/%s — returned %s records", portal, len(rows))
        return jsonify({
            "portal": portal,
            "count": len(rows),
            "diffs": rows
        })
    except Exception as e:
        logger.error("GET /diffs/%s error — %s", portal, str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/crawl-log", methods=["GET"])
def get_crawl_log():
    try:
        rows = query_db(
            "SELECT * FROM crawl_log ORDER BY started_at DESC"
        )
        logger.info("GET /crawl-log — returned %s records", len(rows))
        return jsonify({
            "count": len(rows),
            "crawl_log": rows
        })
    except Exception as e:
        logger.error("GET /crawl-log error — %s", str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    init_db()
    print("\nFlask REST API starting...")
    print("Available endpoints:")
    print("  http://localhost:5000/")
    print("  http://localhost:5000/changes")
    print("  http://localhost:5000/portals")
    print("  http://localhost:5000/diffs")
    print("  http://localhost:5000/crawl-log")
    print("  http://localhost:5000/changes/<portal>")
    print("  http://localhost:5000/diffs/<portal>\n")
    app.run(debug=True, port=5000)