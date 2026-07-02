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
:: Prefer Python 3.13 explicitly; fall back to plain `python` if py launcher not present.
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3.13 -u run_dashboard.py
) else (
    python -u run_dashboard.py
)

:: If we get here, something went wrong
echo.
echo   Dashboard stopped. Press any key to exit...
pause >nul
