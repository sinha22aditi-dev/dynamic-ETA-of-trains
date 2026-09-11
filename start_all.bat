@echo off
echo ===================================================
echo Starting DynamicRail System (SIH26028 Prototype)
echo ===================================================

echo [1/3] Launching ML Prediction Engine on http://localhost:8000 ...
start "DynamicRail ML Engine" cmd /k "cd /d %~dp0DynamicRail_Complete_ML && python -m uvicorn api:app --host 0.0.0.0 --port 8000"

timeout /t 3 /nobreak >nul

echo [2/3] Launching Backend API Server on http://localhost:8080 ...
start "DynamicRail Backend Server" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8080"

timeout /t 2 /nobreak >nul

echo [3/3] Opening DynamicRail Dashboard in Default Browser ...
start "" "%~dp0frontend.html"

echo ===================================================
echo DynamicRail is now running!
echo - Frontend: frontend.html
echo - Backend:  http://localhost:8080/docs
echo - ML Engine: http://localhost:8000/docs
echo ===================================================
pause
