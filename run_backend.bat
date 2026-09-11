@echo off
echo ===================================================
echo Starting DynamicRail Backend API Server (Port 8080)
echo ===================================================
cd /d "%~dp0backend"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
pause
