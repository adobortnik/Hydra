@echo off
echo Starting Simple Media Folder Watcher for The Live House Dashboard
echo --------------------------------------------------------
echo This will monitor the data/media_library/original folder for changes
echo You can now add files and folders directly to this directory
echo The folder will be scanned every 10 seconds for changes
echo.
echo Press Ctrl+C to stop the watcher

python simple_media_watcher.py
