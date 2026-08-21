"""Vercel serverless handler — reuses the main Flask app from root api.py."""
import importlib.util
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location(
    "webtracker_api",
    os.path.join(_ROOT, "api.py"),
)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)

app = _MOD.app
