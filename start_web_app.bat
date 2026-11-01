@echo off
title GitFlow - GitHub Automated Uploader Dashboard
echo ==============================================================
echo    Starting GitFlow Web Dashboard...
echo    Dashboard URL: http://localhost:8000
echo ==============================================================
echo.

:: Launch browser in background after 2 seconds
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:8000"

:: Start Uvicorn web server
python -m uvicorn web_app:app --host 127.0.0.1 --port 8000 --reload
pause

