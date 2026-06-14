@echo off
:loop
call venv\Scripts\activate
python api.py
echo.
echo ==================================================
echo Backend API crashed or stopped! Restarting in 3s...
echo ==================================================
timeout /t 3 /nobreak >nul
goto loop
