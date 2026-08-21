"""Production entry point for Gunicorn/Render (loads root api.py reliably)."""
import importlib.util
import logging
import os

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location(
    "webtracker_api",
    os.path.join(_ROOT, "api.py"),
)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)

app = _MOD.app

try:
    _MOD.init_db()
    logger.info("PostgreSQL/SQLite tables ensured on startup")
except Exception as exc:
    logger.warning("init_db on startup failed: %s", exc)
