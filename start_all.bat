@echo off
echo Starting WebTracker Backend API with auto-restart...
echo NOTE: Use root api.py (NOT api/api.py). Crawler only works with root api.py.
start cmd /k "run_backend.bat"

echo Starting WebTracker React Frontend...
cd frontend
start cmd /k "npm run dev"

echo Both services started!
