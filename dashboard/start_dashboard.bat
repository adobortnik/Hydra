@echo off
cd /d "%~dp0"
start "Hydra Dashboard" /min ..\venv\Scripts\python.exe run_dashboard.py
echo Dashboard started in background.
