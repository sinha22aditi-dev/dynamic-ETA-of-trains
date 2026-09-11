@echo off
echo ===================================================
echo Starting DynamicRail ML Prediction Engine (Port 8000)
echo ===================================================
cd /d "%~dp0DynamicRail_Complete_ML"
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
pause
