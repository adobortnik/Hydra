@echo off
cd /d "%~dp0"
start "Hydra Dashboard" /min python run_dashboard.py
echo Dashboard started in background.
