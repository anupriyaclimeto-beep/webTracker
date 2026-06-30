"""Validate Climeto JWT on Flask API routes (same secret as api.climeto.in)."""

import os

import jwt
from flask import jsonify, request

REQUIRED_TYPE = "webtracker"


def _normalize_user_type(value):
    return (
        str(value or "")
        .lower()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
        .strip()
    )


def get_climeto_jwt_secret():
    return os.getenv("CLIMETO_JWT_SECRET") or os.getenv("JWT_SECRET") or None


def is_climeto_auth_enabled():
    return os.getenv("CLIMETO_AUTH_ENABLED", "true").lower() != "false"


def verify_request():
    """Return None if OK, or a Flask response tuple on auth failure."""
    if not is_climeto_auth_enabled():
        return None

    secret = get_climeto_jwt_secret()
    if not secret:
        return None

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "AUTH_REQUIRED",
                    "message": "Authentication token required",
                }
            ),
            401,
        )

    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "INVALID_TOKEN",
                    "message": "Invalid or expired authentication token",
                }
            ),
            401,
        )

    if _normalize_user_type(payload.get("user_type")) != REQUIRED_TYPE:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "WEB_TRACKER_REQUIRED",
                    "message": "WEB_TRACKER access required",
                }
            ),
            403,
        )

    request.climeto_user = {
        "id": payload.get("id"),
        "email": payload.get("email"),
        "user_type": payload.get("user_type"),
    }
    return None

def register_climeto_auth(app):
    @app.before_request
    def _climeto_auth_guard():
        if request.method == "OPTIONS":
            return None

        path = request.path or ""
        if not path.startswith("/api/"):
            return None
        if path == "/api/login":
            return None

        return verify_request()
