@echo off
echo Starting WebTracker Application...

:: Start the Python backend API in a new window
echo Starting Backend API...
start cmd /k "call venv\Scripts\activate && python api.py"

:: Wait a couple seconds
timeout /t 2 /nobreak >nul

:: Start the React frontend in a new window
echo Starting Frontend UI...
cd frontend
start cmd /k "npm run dev"

echo Both services are starting up! You can close this terminal.
exit
