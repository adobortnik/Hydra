@echo off
title Hydra Dashboard
cd /d "%~dp0dashboard"

echo.
echo   ========================================
echo        HYDRA DASHBOARD
echo   ========================================
echo.
echo   Starting dashboard with auto-restart...
echo   Browser will open at http://localhost:5055
echo   Close this window to stop the dashboard.
echo.

:: Open browser after a few seconds
start "" cmd /c "timeout /t 6 /nobreak >nul & start http://localhost:5055"

:: Run the watchdog (auto-restarts on crash)
python -u run_dashboard.py

:: If we get here, something went wrong
echo.
echo   Dashboard stopped. Press any key to exit...
pause >nul
